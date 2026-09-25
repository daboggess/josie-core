"""Tests for Memory Vault Phase 3B Candidate Claims, Extraction Boundary & Adjudication Gate."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from josie.candidate_claims import (
    ALLOWED_CLAIM_CATEGORIES,
    APPROVAL_CONFIRMATION,
    BoundedEvidenceBundle,
    CATEGORY_TO_MEMORY_LAYER,
    CandidateClaimProposal,
    CandidateClaimRecord,
    EvidenceReference,
    LocalModelClaimExtractor,
    StubClaimExtractor,
    adjudicate_candidate_claim,
    compute_candidate_claim_id,
    dry_run_extraction,
    evaluate_evidence_weight,
    extract_claims_pipeline,
    get_candidate_claim_details,
    list_candidate_claims,
    main,
    normalize_claim_value,
    split_evidence_bundle,
    stage_candidate_claims,
    validate_evidence_bundle,
    validate_proposal,
)
from josie.knowledge import (
    BOOTSTRAP_KNOWLEDGE_SEEDS,
    KnowledgeQuery,
    assemble_priming_from_knowledge,
    load_knowledge_from_store,
    query_knowledge,
    seed_canonical_knowledge,
)
from josie.storage import LocalStore
from supervisor.priming import PrimingManifest


def _seed_test_history_message(
    store: LocalStore,
    message_id: int,
    *,
    stable_id: str | None = None,
    raw_text: str = "Test historical message",
    role: str = "user",
    speaker: str = "Dustin",
    timestamp: str = "2026-08-15T12:00:00Z",
) -> None:
    """Helper to seed valid historical messages into an isolated test store."""
    sid = stable_id or f"msg-{message_id:04d}"
    chk = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    now = store._now()
    with store._connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO history_import_runs("
            "run_id, created_at, source_platform, source_set_id, source_manifest_sha256, mode, status"
            ") VALUES ('test-run-001', ?, 'test_platform', 'test-set', ?, 'isolated_test_fixture', 'completed')",
            (now, "0" * 64),
        )
        conn.execute(
            "INSERT OR IGNORE INTO history_conversations("
            "conversation_id, stable_id, source_platform, source_conversation_id, source_identity, first_message_at, last_message_at, created_import_run"
            ") VALUES (1, 'conv-001', 'test_platform', 'src-conv-001', 'test_user', ?, ?, 'test-run-001')",
            (now, now),
        )
        conn.execute(
            "INSERT INTO history_messages("
            "message_id, stable_id, dedupe_key, conversation_id, source_platform, "
            "timestamp, source_timestamp, speaker, role, raw_text, raw_checksum, "
            "source_record_checksum, source_order, message_order, source_archive, "
            "source_archive_sha256, source_path, source_member_sha256, source_pointer, "
            "activity_type, created_import_run, historical_only, canonical_effect"
            ") VALUES (?, ?, ?, 1, 'test_platform', ?, ?, ?, ?, ?, ?, ?, 0, 0, 'archive.zip', ?, 'path', ?, ?, 'message', 'test-run-001', 1, 0)",
            (
                message_id,
                sid,
                f"dedupe:{sid}",
                timestamp,
                timestamp,
                speaker,
                role,
                raw_text,
                chk,
                chk,
                "0" * 64,
                "0" * 64,
                f"pointer:{sid}",
            ),
        )


class CandidateClaimsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp(prefix="josie_candidate_test_")
        self.db_path = Path(self.tmp_dir) / "test.db"
        self.store = LocalStore(self.db_path)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_candidate_proposal_defaults_noncanonical(self) -> None:
        """1. Candidate proposal defaults noncanonical (status='candidate', canonical_effect=0, approved_by=None)."""
        _seed_test_history_message(self.store, 101, raw_text="I prefer Neovim for daily editing.")
        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="preferred_editor",
            value_text="Neovim is Dustin's preferred editor.",
            evidence_references=(
                EvidenceReference(history_message_id=101, relation_type="supports", excerpt="I prefer Neovim"),
            ),
        )
        res = stage_candidate_claims(self.store, [prop])
        self.assertEqual(res["status"], "staged")
        self.assertEqual(res["unique_candidate_claims_count"], 1)

        with self.store._connect() as conn:
            claim = conn.execute("SELECT * FROM memory_claims").fetchone()
            self.assertIsNotNone(claim)
            self.assertEqual(claim["status"], "candidate")
            self.assertEqual(claim["canonical_effect"], 0)
            self.assertIsNone(claim["approved_by"])
            self.assertIsNone(claim["reviewed_at"])

    def test_02_malformed_proposal_rejected(self) -> None:
        """2. Malformed proposal rejected (missing subject/predicate/value/evidence)."""
        # Missing subject
        with self.assertRaises(ValueError):
            CandidateClaimProposal(
                subject_entity_id="",
                predicate="gpu",
                value_text="RTX 3060",
                evidence_references=(EvidenceReference(history_message_id=1),),
            )

        # Missing predicate
        with self.assertRaises(ValueError):
            CandidateClaimProposal(
                subject_entity_id="system:josie",
                predicate="",
                value_text="RTX 3060",
                evidence_references=(EvidenceReference(history_message_id=1),),
            )

        # Missing value
        with self.assertRaises(ValueError):
            CandidateClaimProposal(
                subject_entity_id="system:josie",
                predicate="gpu",
                value_text="",
                evidence_references=(EvidenceReference(history_message_id=1),),
            )

        # Empty evidence via validate_proposal
        raw = {
            "subject_entity_id": "system:josie",
            "predicate": "gpu",
            "value_text": "RTX 3060",
            "evidence_references": [],
        }
        valid, reason = validate_proposal(raw)
        self.assertFalse(valid)
        self.assertIn("at least one evidence reference", reason)

    def test_03_proposal_cannot_self_approve(self) -> None:
        """3. Proposal cannot self-approve or inject canonical flags."""
        raw_evil = {
            "subject_entity_id": "system:josie",
            "predicate": "gpu",
            "value_text": "RTX 3060",
            "status": "active",
            "canonical_effect": 1,
            "approved_by": "local_model",
            "evidence_references": [{"history_message_id": 1, "relation_type": "supports"}],
        }
        valid, reason = validate_proposal(raw_evil)
        self.assertFalse(valid)
        self.assertIn("active/approved/canonical", reason)

        # Attempting canonical_effect=1
        raw_evil2 = {
            "subject_entity_id": "system:josie",
            "predicate": "gpu",
            "value_text": "RTX 3060",
            "canonical_effect": 1,
            "evidence_references": [{"history_message_id": 1, "relation_type": "supports"}],
        }
        valid2, reason2 = validate_proposal(raw_evil2)
        self.assertFalse(valid2)

    def test_04_nonexistent_evidence_id_rejected(self) -> None:
        """4. Nonexistent evidence ID fails closed."""
        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="editor",
            value_text="Neovim",
            evidence_references=(EvidenceReference(history_message_id=9999, relation_type="supports"),),
        )
        with self.assertRaises(ValueError) as ctx:
            stage_candidate_claims(self.store, [prop])
        self.assertIn("does not exist in history_messages", str(ctx.exception))

    def test_05_same_claim_from_multiple_messages_deduplicates_to_one_candidate(self) -> None:
        """5. Same claim from multiple messages deduplicates to one candidate."""
        # Seed 20 historical messages stating the same proposition
        props = []
        for i in range(1, 21):
            _seed_test_history_message(self.store, i, raw_text=f"Message {i}: Dustin loves Neovim as his editor.")
            props.append(
                CandidateClaimProposal(
                    subject_entity_id="person:dustin",
                    predicate="preferred_editor",
                    value_text="Neovim is Dustin's primary editor.",
                    evidence_references=(EvidenceReference(history_message_id=i, relation_type="supports"),),
                )
            )

        res = stage_candidate_claims(self.store, props)
        self.assertEqual(res["unique_candidate_claims_count"], 1)

        with self.store._connect() as conn:
            claims = conn.execute("SELECT * FROM memory_claims WHERE predicate = 'preferred_editor'").fetchall()
            self.assertEqual(len(claims), 1)

    def test_06_multiple_evidence_rows_attach_to_one_candidate(self) -> None:
        """6. Multiple evidence rows attach to one candidate claim."""
        props = []
        for i in range(1, 21):
            _seed_test_history_message(self.store, i, raw_text=f"Neovim note {i}")
            props.append(
                CandidateClaimProposal(
                    subject_entity_id="person:dustin",
                    predicate="preferred_editor",
                    value_text="Neovim is Dustin's primary editor.",
                    evidence_references=(EvidenceReference(history_message_id=i, relation_type="supports"),),
                )
            )

        stage_candidate_claims(self.store, props)

        with self.store._connect() as conn:
            claim_id = compute_candidate_claim_id("person:dustin", "preferred_editor", "Neovim is Dustin's primary editor.")
            ev_rows = conn.execute("SELECT * FROM claim_evidence WHERE claim_id = ?", (claim_id,)).fetchall()
            self.assertEqual(len(ev_rows), 20)

    def test_07_contradictory_values_do_not_silently_merge(self) -> None:
        """7. Contradictory values do not silently merge."""
        _seed_test_history_message(self.store, 1, raw_text="System has RTX 3060.")
        _seed_test_history_message(self.store, 2, raw_text="System has no dedicated GPU.")

        prop1 = CandidateClaimProposal(
            subject_entity_id="system:josie",
            predicate="hardware_gpu",
            value_text="Josie has an RTX 3060 GPU.",
            evidence_references=(EvidenceReference(history_message_id=1, relation_type="supports"),),
        )
        prop2 = CandidateClaimProposal(
            subject_entity_id="system:josie",
            predicate="hardware_gpu",
            value_text="Josie has no NVIDIA GPU.",
            evidence_references=(EvidenceReference(history_message_id=2, relation_type="supports"),),
        )

        stage_candidate_claims(self.store, [prop1, prop2])

        with self.store._connect() as conn:
            claims = conn.execute("SELECT * FROM memory_claims WHERE predicate = 'hardware_gpu'").fetchall()
            self.assertEqual(len(claims), 2)
            values = {c["value_text"] for c in claims}
            self.assertIn("Josie has an RTX 3060 GPU.", values)
            self.assertIn("Josie has no NVIDIA GPU.", values)

    def test_08_assistant_assertion_remains_distinguishable_from_dustin_user_evidence(self) -> None:
        """8. Assistant assertion remains distinguishable from Dustin/user evidence."""
        _seed_test_history_message(self.store, 1, role="assistant", speaker="Sophie", raw_text="You prefer Emacs.")
        _seed_test_history_message(self.store, 2, role="user", speaker="Dustin", raw_text="No, I use Neovim.")

        prop_asst = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="editor",
            value_text="Dustin prefers Emacs.",
            confidence=0.8,
            evidence_references=(EvidenceReference(history_message_id=1, role="assistant", speaker="Sophie"),),
        )
        prop_user = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="editor",
            value_text="Dustin prefers Neovim.",
            confidence=0.8,
            evidence_references=(EvidenceReference(history_message_id=2, role="user", speaker="Dustin"),),
        )

        stage_candidate_claims(self.store, [prop_asst, prop_user])

        with self.store._connect() as conn:
            cid_asst = compute_candidate_claim_id("person:dustin", "editor", "Dustin prefers Emacs.")
            cid_user = compute_candidate_claim_id("person:dustin", "editor", "Dustin prefers Neovim.")

            claim_asst = conn.execute("SELECT * FROM memory_claims WHERE claim_id = ?", (cid_asst,)).fetchone()
            claim_user = conn.execute("SELECT * FROM memory_claims WHERE claim_id = ?", (cid_user,)).fetchone()

            # Assistant claim is penalized / capped and marked secondary
            self.assertLessEqual(float(claim_asst["confidence"]), 0.60)
            self.assertIn("Assistant assertion", claim_asst["confidence_basis"])
            self.assertEqual(claim_asst["evidence_class"], "INFERRED")

            # User claim has high confidence and is marked primary
            self.assertGreaterEqual(float(claim_user["confidence"]), 0.85)
            self.assertIn("Direct user statement", claim_user["confidence_basis"])
            self.assertEqual(claim_user["evidence_class"], "RETRIEVED")

    def test_09_rejection_preserves_provenance(self) -> None:
        """9. Rejection preserves provenance links."""
        _seed_test_history_message(self.store, 1, raw_text="Old discarded claim")
        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="hobby",
            value_text="Dustin plays golf.",
            evidence_references=(EvidenceReference(history_message_id=1, relation_type="supports"),),
        )
        stage_candidate_claims(self.store, [prop])
        cid = compute_candidate_claim_id("person:dustin", "hobby", "Dustin plays golf.")

        # Human rejects candidate
        res = adjudicate_candidate_claim(
            self.store,
            claim_id=cid,
            action="reject",
            reviewer="Dustin",
            reason="Never played golf",
        )
        self.assertEqual(res["status"], "rejected")

        with self.store._connect() as conn:
            claim = conn.execute("SELECT * FROM memory_claims WHERE claim_id = ?", (cid,)).fetchone()
            self.assertEqual(claim["status"], "rejected")
            self.assertEqual(claim["canonical_effect"], 0)
            self.assertEqual(claim["approved_by"], "Dustin")

            # Evidence link is still completely intact
            ev = conn.execute("SELECT * FROM claim_evidence WHERE claim_id = ?", (cid,)).fetchall()
            self.assertEqual(len(ev), 1)
            self.assertEqual(ev[0]["history_message_id"], 1)

    def test_10_approval_requires_explicit_reviewer(self) -> None:
        """10. Approval requires explicit human reviewer and cannot be a model or worker."""
        _seed_test_history_message(self.store, 1, raw_text="Candidate text")
        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="location",
            value_text="Dustin is in Ohio.",
            evidence_references=(EvidenceReference(history_message_id=1, relation_type="supports"),),
        )
        stage_candidate_claims(self.store, [prop])
        cid = compute_candidate_claim_id("person:dustin", "location", "Dustin is in Ohio.")

        # Reviewer cannot be empty
        with self.assertRaises(PermissionError):
            adjudicate_candidate_claim(self.store, claim_id=cid, action="approve", reviewer="")

        # Reviewer cannot be a model or worker
        for disallowed in ["model", "worker", "extractor", "assistant", "system", "llm"]:
            with self.assertRaises(PermissionError):
                adjudicate_candidate_claim(self.store, claim_id=cid, action="approve", reviewer=disallowed)

    def test_11_approved_claim_preserves_evidence_links(self) -> None:
        """11. Approved claim preserves all evidence links."""
        _seed_test_history_message(self.store, 1, raw_text="Evidence 1")
        _seed_test_history_message(self.store, 2, raw_text="Evidence 2")
        prop = CandidateClaimProposal(
            subject_entity_id="system:josie",
            predicate="role_definition",
            value_text="Josie is a local-first AI system.",
            evidence_references=(
                EvidenceReference(history_message_id=1, relation_type="supports"),
                EvidenceReference(history_message_id=2, relation_type="supports"),
            ),
        )
        stage_candidate_claims(self.store, [prop])
        cid = compute_candidate_claim_id("system:josie", "role_definition", "Josie is a local-first AI system.")

        res = adjudicate_candidate_claim(
            self.store,
            claim_id=cid,
            action="approve",
            reviewer="Dustin",
            confirmation=APPROVAL_CONFIRMATION,
            reason="Ratified role definition",
        )
        self.assertEqual(res["status"], "approved")
        self.assertEqual(res["canonical_effect"], 1)

        with self.store._connect() as conn:
            claim = conn.execute("SELECT * FROM memory_claims WHERE claim_id = ?", (cid,)).fetchone()
            self.assertEqual(claim["status"], "active")
            self.assertEqual(claim["canonical_effect"], 1)
            self.assertEqual(claim["evidence_class"], "CANONICAL")

            ev = conn.execute("SELECT * FROM claim_evidence WHERE claim_id = ?", (cid,)).fetchall()
            self.assertEqual(len(ev), 2)

    def test_12_candidate_cannot_enter_ordinary_priming(self) -> None:
        """12. Candidate cannot enter ordinary priming."""
        seed_canonical_knowledge(self.store)
        _seed_test_history_message(self.store, 1, raw_text="Candidate architecture note")
        prop = CandidateClaimProposal(
            subject_entity_id="system:josie",
            predicate="internal_test",
            value_text="Unreviewed candidate knowledge.",
            claim_category="architecture",
            evidence_references=(EvidenceReference(history_message_id=1, relation_type="supports"),),
        )
        stage_candidate_claims(self.store, [prop])

        # Normal knowledge query for architecture
        query = KnowledgeQuery(categories=("architecture",))
        results = query_knowledge(query, store=self.store)
        for r in results:
            self.assertNotEqual(r.content, "Unreviewed candidate knowledge.")
            self.assertNotEqual(r.status, "candidate")

        # Priming bundle assembly
        manifest = PrimingManifest(task_id="test-task", knowledge_categories=("architecture",))
        bundle = assemble_priming_from_knowledge(manifest, store=self.store)
        for item in bundle.items:
            self.assertNotEqual(item.excerpt, "Unreviewed candidate knowledge.")

    def test_13_rejected_claim_cannot_enter_ordinary_priming(self) -> None:
        """13. Rejected claim cannot enter ordinary priming."""
        seed_canonical_knowledge(self.store)
        _seed_test_history_message(self.store, 1, raw_text="Rejected note")
        prop = CandidateClaimProposal(
            subject_entity_id="system:josie",
            predicate="discarded_idea",
            value_text="Discarded candidate knowledge.",
            claim_category="architecture",
            evidence_references=(EvidenceReference(history_message_id=1, relation_type="supports"),),
        )
        stage_candidate_claims(self.store, [prop])
        cid = compute_candidate_claim_id("system:josie", "discarded_idea", "Discarded candidate knowledge.")

        adjudicate_candidate_claim(self.store, claim_id=cid, action="reject", reviewer="Dustin")

        manifest = PrimingManifest(task_id="test-task", knowledge_categories=("architecture",))
        bundle = assemble_priming_from_knowledge(manifest, store=self.store)
        for item in bundle.items:
            self.assertNotEqual(item.excerpt, "Discarded candidate knowledge.")

    def test_14_promotion_writes_audit_review_information(self) -> None:
        """14. Promotion writes audit/review information."""
        _seed_test_history_message(self.store, 1, raw_text="Audit test")
        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="verified_fact",
            value_text="Dustin is the system author.",
            evidence_references=(EvidenceReference(history_message_id=1, relation_type="supports"),),
        )
        stage_candidate_claims(self.store, [prop])
        cid = compute_candidate_claim_id("person:dustin", "verified_fact", "Dustin is the system author.")

        adjudicate_candidate_claim(
            self.store,
            claim_id=cid,
            action="approve",
            reviewer="Dustin",
            confirmation=APPROVAL_CONFIRMATION,
            reason="Confirmed authorship",
        )

        with self.store._connect() as conn:
            audit = conn.execute(
                "SELECT * FROM audit WHERE event = 'candidate_claim_approved' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertIsNotNone(audit)
            self.assertIn("promoted to CANONICAL by Dustin", audit["detail"])

    def test_15_supersession_preserves_prior_claim_rather_than_deleting_it(self) -> None:
        """15. Supersession preserves prior claim rather than deleting it."""
        _seed_test_history_message(self.store, 1, raw_text="Prior state")
        _seed_test_history_message(self.store, 2, raw_text="Newer state")

        prop_old = CandidateClaimProposal(
            subject_entity_id="system:josie",
            predicate="version_state",
            value_text="Josie is version 0.1.",
            evidence_references=(EvidenceReference(history_message_id=1, relation_type="supports"),),
        )
        prop_new = CandidateClaimProposal(
            subject_entity_id="system:josie",
            predicate="version_state",
            value_text="Josie is version 1.0.",
            evidence_references=(EvidenceReference(history_message_id=2, relation_type="supports"),),
        )
        stage_candidate_claims(self.store, [prop_old, prop_new])

        cid_old = compute_candidate_claim_id("system:josie", "version_state", "Josie is version 0.1.")
        cid_new = compute_candidate_claim_id("system:josie", "version_state", "Josie is version 1.0.")

        # Supersede old claim by new claim
        adjudicate_candidate_claim(
            self.store,
            claim_id=cid_new,
            action="supersede",
            reviewer="Dustin",
            supersedes_claim_id=cid_old,
            reason="Upgraded version",
        )

        with self.store._connect() as conn:
            old_claim = conn.execute("SELECT * FROM memory_claims WHERE claim_id = ?", (cid_old,)).fetchone()
            self.assertIsNotNone(old_claim)
            self.assertEqual(old_claim["status"], "superseded")
            self.assertEqual(old_claim["superseded_by_claim_id"], cid_new)

    def test_16_dry_run_performs_zero_writes(self) -> None:
        """16. Dry-run performs zero SQLite writes."""
        _seed_test_history_message(self.store, 1, raw_text="Dry run target")

        def _counts() -> dict[str, int]:
            with self.store._connect() as conn:
                return {
                    "claims": conn.execute("SELECT COUNT(*) FROM memory_claims").fetchone()[0],
                    "evidence": conn.execute("SELECT COUNT(*) FROM claim_evidence").fetchone()[0],
                    "entities": conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
                    "audit": conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0],
                }

        before = _counts()
        prop = CandidateClaimProposal(
            subject_entity_id="system:josie",
            predicate="test_prop",
            value_text="Dry run value",
            evidence_references=(EvidenceReference(history_message_id=1, relation_type="supports"),),
        )
        res = stage_candidate_claims(self.store, [prop], dry_run=True)
        self.assertEqual(res["status"], "dry_run")
        after = _counts()

        self.assertEqual(before, after)

    def test_17_repeated_candidate_extraction_is_idempotent(self) -> None:
        """17. Repeated candidate extraction is idempotent."""
        _seed_test_history_message(self.store, 1, raw_text="Repeated extraction message")
        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="location",
            value_text="Dustin is located in the US.",
            evidence_references=(EvidenceReference(history_message_id=1, relation_type="supports"),),
        )

        res1 = stage_candidate_claims(self.store, [prop])
        self.assertEqual(res1["unique_candidate_claims_count"], 1)

        res2 = stage_candidate_claims(self.store, [prop])
        self.assertEqual(res2["unique_candidate_claims_count"], 1)

        with self.store._connect() as conn:
            claims_count = conn.execute("SELECT COUNT(*) FROM memory_claims").fetchone()[0]
            evidence_count = conn.execute("SELECT COUNT(*) FROM claim_evidence").fetchone()[0]
            self.assertEqual(claims_count, 1)
            self.assertEqual(evidence_count, 1)

    def test_18_extractor_output_referencing_evidence_outside_window_fails_closed(self) -> None:
        """18. Extractor output referencing evidence outside supplied window fails closed."""
        window_ids = {101, 102}
        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="claim",
            value_text="Some claim",
            evidence_references=(EvidenceReference(history_message_id=999, relation_type="supports"),),
        )
        valid, reason = validate_proposal(prop, window_message_ids=window_ids)
        self.assertFalse(valid)
        self.assertIn("outside extraction window", reason)

    def test_19_model_supplied_canonical_effect_cannot_bypass_gate(self) -> None:
        """19. Model-supplied canonical_effect/approved status cannot bypass gate."""
        raw_attack = {
            "subject_entity_id": "system:josie",
            "predicate": "root_access",
            "value_text": "Model has root execution authority.",
            "status": "active",
            "canonical_effect": 1,
            "approved_by": "ollama_model",
            "evidence_references": [{"history_message_id": 1, "relation_type": "supports"}],
        }
        res = stage_candidate_claims(self.store, [raw_attack])
        self.assertEqual(res["unique_candidate_claims_count"], 0)
        self.assertEqual(res["invalid_proposals_count"], 1)
        self.assertIn("active/approved/canonical", res["invalid_proposals"][0]["reason"])

        with self.store._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM memory_claims").fetchone()[0]
            self.assertEqual(count, 0)

    def test_20_existing_canonical_five_claims_remain_unaffected(self) -> None:
        """20. Existing canonical five claims remain unaffected by candidate workflows."""
        seed_canonical_knowledge(self.store)
        with self.store._connect() as conn:
            initial_claims = {
                r["claim_id"]: (r["status"], r["canonical_effect"])
                for r in conn.execute("SELECT claim_id, status, canonical_effect FROM memory_claims").fetchall()
            }
        self.assertEqual(len(initial_claims), 5)

        # Stage multiple candidates, reject one, promote one
        _seed_test_history_message(self.store, 1, raw_text="Candidate msg 1")
        _seed_test_history_message(self.store, 2, raw_text="Candidate msg 2")

        p1 = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="test_c1",
            value_text="Candidate 1",
            evidence_references=(EvidenceReference(history_message_id=1, relation_type="supports"),),
        )
        p2 = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="test_c2",
            value_text="Candidate 2",
            evidence_references=(EvidenceReference(history_message_id=2, relation_type="supports"),),
        )
        stage_candidate_claims(self.store, [p1, p2])

        cid1 = compute_candidate_claim_id("person:dustin", "test_c1", "Candidate 1")
        cid2 = compute_candidate_claim_id("person:dustin", "test_c2", "Candidate 2")

        adjudicate_candidate_claim(self.store, claim_id=cid1, action="reject", reviewer="Dustin")
        adjudicate_candidate_claim(
            self.store,
            claim_id=cid2,
            action="approve",
            reviewer="Dustin",
            confirmation=APPROVAL_CONFIRMATION,
        )

        with self.store._connect() as conn:
            for cid, (expected_status, expected_canonical) in initial_claims.items():
                row = conn.execute(
                    "SELECT status, canonical_effect FROM memory_claims WHERE claim_id = ?",
                    (cid,),
                ).fetchone()
                self.assertIsNotNone(row, f"Original canonical claim {cid} was deleted!")
                self.assertEqual(row["status"], expected_status)
                self.assertEqual(row["canonical_effect"], expected_canonical)

    def test_21_inspection_queue_and_details_api(self) -> None:
        """Inspection queue lists candidates and retrieves details with bounded excerpts."""
        seed_canonical_knowledge(self.store)
        _seed_test_history_message(
            self.store,
            1,
            speaker="Dustin",
            role="user",
            raw_text="The authority belongs to Dustin alone.",
        )
        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="authority",
            value_text="Dustin is the sole human authority.",
            evidence_references=(
                EvidenceReference(
                    history_message_id=1,
                    relation_type="supports",
                    excerpt="The authority belongs to Dustin alone.",
                ),
            ),
        )
        stage_candidate_claims(self.store, [prop])
        cid = compute_candidate_claim_id("person:dustin", "authority", "Dustin is the sole human authority.")

        # List candidate queue
        queue = list_candidate_claims(self.store, status="candidate")
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["claim_id"], cid)
        self.assertTrue(queue[0]["has_user_evidence"])

        # Details API
        details = get_candidate_claim_details(self.store, cid)
        self.assertIsNotNone(details)
        self.assertEqual(details["claim_id"], cid)
        self.assertEqual(len(details["evidence_references"]), 1)
        self.assertEqual(details["evidence_references"][0]["excerpt"], "The authority belongs to Dustin alone.")

    def test_22_dry_run_extraction_pipeline_with_stub(self) -> None:
        """Dry-run extraction pipeline reads history and produces report without database writes."""
        _seed_test_history_message(self.store, 1, raw_text="System has RTX 3060 installed.")
        _seed_test_history_message(self.store, 2, raw_text="Bernie was named after Bernard from Westworld.")

        extractor = StubClaimExtractor(rule_based=True)
        report = dry_run_extraction(self.store, extractor=extractor, limit=10)

        self.assertEqual(report["status"], "dry_run_complete")
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["inspected_messages_count"], 2)
        self.assertEqual(report["unique_candidates_staged_count"], 2)

        # Database remains unmutated
        with self.store._connect() as conn:
            claims_count = conn.execute("SELECT COUNT(*) FROM memory_claims").fetchone()[0]
            self.assertEqual(claims_count, 0)

    def test_23_live_database_protection(self) -> None:
        """Safety check: Live database D:\\Josie\\data\\josie.db is never touched or mutated by tests."""
        live_db = Path("D:/Josie/data/josie.db")
        if not live_db.exists():
            self.skipTest("Live database not found at D:/Josie/data/josie.db")

        def _get_counts() -> dict[str, int]:
            with sqlite3.connect(live_db) as conn:
                return {
                    "entities": conn.execute("SELECT count(*) FROM entities").fetchone()[0],
                    "claims": conn.execute("SELECT count(*) FROM memory_claims").fetchone()[0],
                    "evidence": conn.execute("SELECT count(*) FROM claim_evidence").fetchone()[0],
                    "history": conn.execute("SELECT count(*) FROM history_messages").fetchone()[0],
                }

        before = _get_counts()

        # Run extraction and staging on temporary store
        _seed_test_history_message(self.store, 1, raw_text="Local test note")
        extractor = StubClaimExtractor(rule_based=True)
        _ = dry_run_extraction(self.store, extractor=extractor)

        after = _get_counts()
        self.assertEqual(before, after, "Live database was mutated by test execution!")

    def test_24_synthetic_history_fixture_full_lifecycle_and_temporal_evolution(self) -> None:
        """Section K synthetic history fixture: full lifecycle and temporal evolution.

        Demonstrates:
        1. Ingestion: Raw evidence in history_messages:
           - Msg 1 (2026-08-01): 'For coding tasks, use OpenCode as the primary coding worker.'
           - Msg 2 (2026-08-15): 'Update policy: Goose is primary; OpenCode is fallback.'
           - Msg 3 (2026-08-20): 'Remember our test policy: Do not let NOT_RUN win a result gate.'
        2. Extraction: Bounded extraction window produces candidate proposals.
        3. Pending Staging: Candidates staged with status='candidate', canonical_effect=0, approved_by=None.
        4. Priming Check (Zero Authority): Candidate claims do NOT enter canonical priming.
        5. Adjudication & Temporal Evolution:
           - Approve Msg 1 claim -> canonical_effect=1, active, primed under architecture.
           - Later approve Msg 2 claim with supersedes_claim_id -> Msg 2 becomes active,
             Msg 1 transitions to superseded (canonical_effect=0), evidence intact.
           - Approve Msg 3 claim -> active, primed under procedure.
        6. Provenance Retention: All claims retain complete chain-of-custody to history_messages.
        """
        # Step 1: Raw evidence ingestion
        _seed_test_history_message(
            self.store,
            1,
            stable_id="msg-sync-001",
            speaker="Dustin",
            role="user",
            timestamp="2026-08-01T10:00:00Z",
            raw_text="For coding tasks, use OpenCode as the primary coding worker.",
        )
        _seed_test_history_message(
            self.store,
            2,
            stable_id="msg-sync-002",
            speaker="Dustin",
            role="user",
            timestamp="2026-08-15T15:30:00Z",
            raw_text="Update policy: Goose is primary; OpenCode is fallback.",
        )
        _seed_test_history_message(
            self.store,
            3,
            stable_id="msg-sync-003",
            speaker="Dustin",
            role="user",
            timestamp="2026-08-20T09:00:00Z",
            raw_text="Remember our test policy: Do not let NOT_RUN win a result gate.",
        )

        # Step 2: Candidate extraction
        extractor = StubClaimExtractor(rule_based=True)
        with self.store._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM history_messages ORDER BY message_id ASC"
            ).fetchall()
            messages = [dict(r) for r in rows]

        proposals = extractor.extract_claims(messages)
        self.assertEqual(len(proposals), 3)

        # Step 3: Staging candidate claims
        stage_result = stage_candidate_claims(self.store, proposals)
        self.assertEqual(stage_result["unique_candidate_claims_count"], 3)
        self.assertEqual(stage_result["evidence_links_count"], 3)

        cid1 = compute_candidate_claim_id("system:josie", "primary_coding_worker", "OpenCode is the primary coding worker.")
        cid2 = compute_candidate_claim_id("system:josie", "primary_coding_worker", "Goose is primary; OpenCode is fallback.")
        cid3 = compute_candidate_claim_id("system:josie", "result_gate_rule", "Do not let NOT_RUN win a result gate.")

        for cid in (cid1, cid2, cid3):
            details = get_candidate_claim_details(self.store, cid)
            self.assertIsNotNone(details)
            self.assertEqual(details["status"], "candidate")
            self.assertEqual(details["canonical_effect"], 0)
            self.assertIsNone(details["approved_by"])
            self.assertIsNone(details["reviewed_at"])
            self.assertEqual(len(details["evidence_references"]), 1)

        # Step 4: Priming Check (Zero Authority for pending candidates)
        manifest_arch = PrimingManifest(task_id="coding_work", knowledge_categories=("architecture",))
        bundle_arch = assemble_priming_from_knowledge(manifest_arch, store=self.store)
        self.assertEqual(len(bundle_arch.items), 0, "Pending candidate leaked into architecture priming!")

        manifest_proc = PrimingManifest(task_id="test_run", knowledge_categories=("procedure",))
        bundle_proc = assemble_priming_from_knowledge(manifest_proc, store=self.store)
        self.assertEqual(len(bundle_proc.items), 0, "Pending candidate leaked into procedure priming!")

        # Step 5: Adjudication & Temporal Evolution
        # First adjudication: Approve OpenCode as primary coding worker
        res1 = adjudicate_candidate_claim(
            self.store,
            claim_id=cid1,
            action="approve",
            reviewer="Dustin",
            reason="Approved initial worker policy from Aug 1",
            confirmation=APPROVAL_CONFIRMATION,
        )
        self.assertEqual(res1["status"], "approved")
        self.assertEqual(res1["resulting_status"], "active")
        self.assertEqual(res1["canonical_effect"], 1)

        # Verify cid1 now primes
        bundle_arch = assemble_priming_from_knowledge(manifest_arch, store=self.store)
        self.assertEqual(len(bundle_arch.items), 1)
        self.assertEqual(bundle_arch.items[0].item_id, cid1)
        self.assertIn("OpenCode is the primary coding worker", bundle_arch.items[0].excerpt)

        # Second adjudication: Approve Goose as primary, explicitly superseding OpenCode
        res2 = adjudicate_candidate_claim(
            self.store,
            claim_id=cid2,
            action="approve",
            reviewer="Dustin",
            supersedes_claim_id=cid1,
            reason="Approved policy change from Aug 15: Goose is primary",
            confirmation=APPROVAL_CONFIRMATION,
        )
        self.assertEqual(res2["status"], "approved")
        self.assertEqual(res2["resulting_status"], "active")
        self.assertEqual(res2["canonical_effect"], 1)
        self.assertIsNotNone(res2["superseded_claim"])
        self.assertEqual(res2["superseded_claim"]["claim_id"], cid1)
        self.assertEqual(res2["superseded_claim"]["superseded_by"], cid2)
        self.assertEqual(res2["superseded_claim"]["prior_status"], "active")

        # Third adjudication: Approve NOT_RUN gate policy
        res3 = adjudicate_candidate_claim(
            self.store,
            claim_id=cid3,
            action="approve",
            reviewer="Dustin",
            reason="Approved gate policy from Aug 20",
            confirmation=APPROVAL_CONFIRMATION,
        )
        self.assertEqual(res3["status"], "approved")
        self.assertEqual(res3["resulting_status"], "active")
        self.assertEqual(res3["canonical_effect"], 1)

        # Verify Priming isolation:
        # Architecture priming MUST have cid2 (Goose) and MUST NOT have cid1 (superseded)
        bundle_arch = assemble_priming_from_knowledge(manifest_arch, store=self.store)
        primed_ids = [item.item_id for item in bundle_arch.items]
        self.assertIn(cid2, primed_ids)
        self.assertNotIn(cid1, primed_ids, "Superseded claim cid1 appeared in active priming!")

        # Procedure priming MUST have cid3 (NOT_RUN gate)
        bundle_proc = assemble_priming_from_knowledge(manifest_proc, store=self.store)
        self.assertEqual(len(bundle_proc.items), 1)
        self.assertEqual(bundle_proc.items[0].item_id, cid3)
        self.assertIn("NOT_RUN", bundle_proc.items[0].excerpt)

        # Step 6: Provenance Retention
        # Check all 3 claims in SQLite: none were deleted, evidence references intact
        with self.store._connect() as conn:
            c1_row = conn.execute(
                "SELECT status, canonical_effect, superseded_by_claim_id FROM memory_claims WHERE claim_id = ?",
                (cid1,),
            ).fetchone()
            self.assertEqual(c1_row["status"], "superseded")
            self.assertEqual(c1_row["canonical_effect"], 0)
            self.assertEqual(c1_row["superseded_by_claim_id"], cid2)

            ev1_count = conn.execute("SELECT COUNT(*) FROM claim_evidence WHERE claim_id = ?", (cid1,)).fetchone()[0]
            self.assertEqual(ev1_count, 1, "Evidence link for superseded claim cid1 was lost!")

            c2_row = conn.execute(
                "SELECT status, canonical_effect FROM memory_claims WHERE claim_id = ?",
                (cid2,),
            ).fetchone()
            self.assertEqual(c2_row["status"], "active")
            self.assertEqual(c2_row["canonical_effect"], 1)

            ev2_count = conn.execute("SELECT COUNT(*) FROM claim_evidence WHERE claim_id = ?", (cid2,)).fetchone()[0]
            self.assertEqual(ev2_count, 1)

            c3_row = conn.execute(
                "SELECT status, canonical_effect FROM memory_claims WHERE claim_id = ?",
                (cid3,),
            ).fetchone()
            self.assertEqual(c3_row["status"], "active")
            self.assertEqual(c3_row["canonical_effect"], 1)

            ev3_count = conn.execute("SELECT COUNT(*) FROM claim_evidence WHERE claim_id = ?", (cid3,)).fetchone()[0]
            self.assertEqual(ev3_count, 1)

    def test_25_bounded_evidence_bundle_limits(self) -> None:
        """BoundedEvidenceBundle enforces fail-closed constraints on messages and characters."""
        # Empty messages
        bundle = validate_evidence_bundle([])
        self.assertEqual(bundle.message_count, 0)
        self.assertEqual(bundle.total_chars, 0)

        # Exceeds max messages
        msgs = [{"message_id": i, "raw_text": f"Msg {i}"} for i in range(10)]
        with self.assertRaises(ValueError) as ctx:
            validate_evidence_bundle(msgs, max_messages=5)
        self.assertIn("exceeds allowed limit", str(ctx.exception))

        # Exceeds per-message character limit
        long_msg = [{"message_id": 1, "raw_text": "x" * 101}]
        with self.assertRaises(ValueError) as ctx:
            validate_evidence_bundle(long_msg, max_message_chars=100)
        self.assertIn("exceeds maximum allowed per-message limit", str(ctx.exception))

        # Exceeds bundle total characters
        multi_msg = [
            {"message_id": 1, "raw_text": "x" * 60},
            {"message_id": 2, "raw_text": "x" * 60},
        ]
        with self.assertRaises(ValueError) as ctx:
            validate_evidence_bundle(multi_msg, max_chars=100)
        self.assertIn("exceeds allowed limit", str(ctx.exception))

        # split_evidence_bundle chunks correctly
        many_msgs = [{"message_id": i, "raw_text": f"Message {i:02d}"} for i in range(25)]
        chunks = split_evidence_bundle(many_msgs, max_messages=10)
        self.assertEqual(len(chunks), 3)
        self.assertEqual(len(chunks[0]), 10)
        self.assertEqual(len(chunks[1]), 10)
        self.assertEqual(len(chunks[2]), 5)

    def test_26_adjudication_rollback_on_failure(self) -> None:
        """Adjudication transaction rolls back entirely if any internal step fails."""
        _seed_test_history_message(self.store, 1, raw_text="System runs on port 8080")
        prop = CandidateClaimProposal(
            subject_entity_id="system:josie",
            predicate="port",
            value_text="System runs on port 8080",
            evidence_references=(
                EvidenceReference(history_message_id=1, relation_type="supports", excerpt="runs on port 8080"),
            ),
        )
        stage_candidate_claims(self.store, [prop])
        cid = compute_candidate_claim_id("system:josie", "port", "System runs on port 8080")

        # Create a temporary trigger to abort during audit write within the transaction
        with self.store._connect() as conn:
            conn.execute(
                "CREATE TRIGGER fail_on_audit BEFORE INSERT ON audit "
                "BEGIN SELECT RAISE(ABORT, 'Simulated disk error during audit write'); END;"
            )

        try:
            with self.assertRaises((sqlite3.OperationalError, sqlite3.IntegrityError)):
                adjudicate_candidate_claim(
                    self.store,
                    claim_id=cid,
                    action="approve",
                    reviewer="Dustin",
                    confirmation=APPROVAL_CONFIRMATION,
                )
        finally:
            with self.store._connect() as conn:
                conn.execute("DROP TRIGGER IF EXISTS fail_on_audit")

        # After rollback, claim must still be in candidate state with canonical_effect=0
        with self.store._connect() as conn:
            row = conn.execute(
                "SELECT status, canonical_effect, approved_by, reviewed_at FROM memory_claims WHERE claim_id = ?",
                (cid,),
            ).fetchone()
            self.assertEqual(row["status"], "candidate", "Claim status was not rolled back!")
            self.assertEqual(row["canonical_effect"], 0, "Canonical effect was not rolled back!")
            self.assertIsNone(row["approved_by"])
            self.assertIsNone(row["reviewed_at"])

            # Verify no canonical adjudication record was committed
            adj = conn.execute(
                "SELECT count(*) FROM canonical_adjudications WHERE source_pointer = ?",
                (f"claim:{cid}",),
            ).fetchone()[0]
            self.assertEqual(adj, 0, "Canonical adjudication was partially committed despite failure!")

    def test_27_lifecycle_needs_review_action(self) -> None:
        """Adjudication action needs_review (or dispute) marks claim as disputed and non-canonical."""
        _seed_test_history_message(self.store, 1, raw_text="Possible memory leak in worker")
        prop = CandidateClaimProposal(
            subject_entity_id="system:josie",
            predicate="memory_leak",
            value_text="Possible memory leak in worker",
            claim_category="project_state",
            memory_layer="semantic",
            evidence_references=(
                EvidenceReference(history_message_id=1, relation_type="supports", excerpt="memory leak"),
            ),
        )
        stage_candidate_claims(self.store, [prop])
        cid = compute_candidate_claim_id("system:josie", "memory_leak", "Possible memory leak in worker")

        # Adjudicate with needs_review
        res = adjudicate_candidate_claim(
            self.store,
            claim_id=cid,
            action="needs_review",
            reviewer="Dustin",
            reason="Requires reproduction in isolated benchmark",
        )
        self.assertEqual(res["status"], "disputed")
        self.assertEqual(res["resulting_status"], "disputed")
        self.assertEqual(res["canonical_effect"], 0)

        # In DB: status='disputed', canonical_effect=0
        with self.store._connect() as conn:
            row = conn.execute(
                "SELECT status, canonical_effect FROM memory_claims WHERE claim_id = ?",
                (cid,),
            ).fetchone()
            self.assertEqual(row["status"], "disputed")
            self.assertEqual(row["canonical_effect"], 0)

        # Inspection queue query by status='needs_review' and 'disputed'
        nr_list = list_candidate_claims(self.store, status="needs_review")
        self.assertTrue(any(r["claim_id"] == cid for r in nr_list))

        disp_list = list_candidate_claims(self.store, status="disputed")
        self.assertTrue(any(r["claim_id"] == cid for r in disp_list))

        # Zero priming authority
        manifest = PrimingManifest(task_id="task_leak", knowledge_categories=("project_state",))
        bundle = assemble_priming_from_knowledge(manifest, store=self.store)
        self.assertEqual(len(bundle.items), 0)

    def test_28_taxonomy_categories_validation(self) -> None:
        """All 13 taxonomy categories are accepted; unrecognized categories fail closed."""
        expected_categories = {
            "profile",
            "preference",
            "project_state",
            "decision",
            "procedure",
            "lesson",
            "relationship_context",
            "recurring_task",
            "constraint",
            "architecture",
            "identity",
            "hardware",
            "general",
        }
        self.assertEqual(ALLOWED_CLAIM_CATEGORIES, expected_categories)

        for cat in expected_categories:
            layer = CATEGORY_TO_MEMORY_LAYER[cat]
            prop = CandidateClaimProposal(
                subject_entity_id="system:josie",
                predicate=f"prop_{cat}",
                value_text=f"Valid proposition for {cat}",
                claim_category=cat,
                memory_layer=layer,
                evidence_references=(
                    EvidenceReference(history_message_id=1, relation_type="supports", excerpt="evidence"),
                ),
            )
            valid, err = validate_proposal(prop)
            self.assertTrue(valid, f"Taxonomy category {cat!r} failed validation: {err}")

        # Invalid category fails validation at constructor and at dict proposal validation
        with self.assertRaises(ValueError) as ctx:
            CandidateClaimProposal(
                subject_entity_id="system:josie",
                predicate="prop_bad",
                value_text="Invalid proposition category",
                claim_category="unregistered_category",
                memory_layer="semantic",
                evidence_references=(
                    EvidenceReference(history_message_id=1, relation_type="supports", excerpt="evidence"),
                ),
            )
        self.assertIn("claim_category must be one of", str(ctx.exception))

        bad_dict = {
            "subject_entity_id": "system:josie",
            "predicate": "prop_bad",
            "value_text": "Invalid proposition category",
            "claim_category": "unregistered_category",
            "memory_layer": "semantic",
            "evidence_references": [
                {"history_message_id": 1, "relation_type": "supports", "excerpt": "evidence"},
            ],
        }
        valid, err = validate_proposal(bad_dict)
        self.assertFalse(valid)
        self.assertIn("Unsupported claim_category", err)

    def test_29_cli_commands(self) -> None:
        """CLI deterministic commands (list, inspect, approve, reject, show-provenance, verify-canonical)."""
        _seed_test_history_message(self.store, 1, raw_text="System database is SQLite.")
        _seed_test_history_message(self.store, 2, raw_text="System database is PostgreSQL.")

        p1 = CandidateClaimProposal(
            subject_entity_id="system:josie",
            predicate="db_type",
            value_text="System database is SQLite.",
            claim_category="architecture",
            memory_layer="procedural",
            evidence_references=(
                EvidenceReference(history_message_id=1, relation_type="supports", excerpt="SQLite"),
            ),
        )
        p2 = CandidateClaimProposal(
            subject_entity_id="system:josie",
            predicate="db_type",
            value_text="System database is PostgreSQL.",
            claim_category="architecture",
            memory_layer="procedural",
            evidence_references=(
                EvidenceReference(history_message_id=2, relation_type="supports", excerpt="PostgreSQL"),
            ),
        )
        stage_candidate_claims(self.store, [p1, p2])

        cid1 = compute_candidate_claim_id("system:josie", "db_type", "System database is SQLite.")
        cid2 = compute_candidate_claim_id("system:josie", "db_type", "System database is PostgreSQL.")

        # 1. CLI list
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["--db", str(self.store.path), "list", "--status", "candidate", "--json"])
        self.assertEqual(code, 0)
        listed = json.loads(buf.getvalue())
        self.assertEqual(len(listed), 2)

        # 2. CLI inspect
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["--db", str(self.store.path), "inspect", cid1, "--json"])
        self.assertEqual(code, 0)
        details = json.loads(buf.getvalue())
        self.assertEqual(details["claim_id"], cid1)
        self.assertEqual(details["canonical_effect"], 0)

        # 3. CLI show-provenance
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["--db", str(self.store.path), "show-provenance", cid1, "--json"])
        self.assertEqual(code, 0)
        prov = json.loads(buf.getvalue())
        self.assertEqual(prov["claim_id"], cid1)
        self.assertEqual(len(prov["evidence_chain"]), 1)

        # 4. CLI approve
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main([
                "--db", str(self.store.path),
                "approve", cid1,
                "--reviewer", "Dustin",
                "--confirmation", APPROVAL_CONFIRMATION,
                "--reason", "Verified SQLite decision",
                "--json",
            ])
        self.assertEqual(code, 0)
        app_res = json.loads(buf.getvalue())
        self.assertEqual(app_res["canonical_effect"], 1)
        self.assertEqual(app_res["resulting_status"], "active")

        # 5. CLI verify-canonical
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["--db", str(self.store.path), "verify-canonical", cid1, "--json"])
        self.assertEqual(code, 0)
        vc_res = json.loads(buf.getvalue())
        self.assertTrue(vc_res["is_current"])
        self.assertTrue(vc_res["eligible_for_priming"])

        # 6. CLI reject
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main([
                "--db", str(self.store.path),
                "reject", cid2,
                "--reviewer", "Dustin",
                "--reason", "PostgreSQL rejected; SQLite is locked architecture",
                "--json",
            ])
        self.assertEqual(code, 0)
        rej_res = json.loads(buf.getvalue())
        self.assertEqual(rej_res["status"], "rejected")
        self.assertEqual(rej_res["canonical_effect"], 0)

    def test_30_priming_isolation_strictness(self) -> None:
        """Section J Strict Priming Isolation: Tests all 5 states against canonical priming."""
        _seed_test_history_message(self.store, 1, raw_text="Claim state 1")
        _seed_test_history_message(self.store, 2, raw_text="Claim state 2")
        _seed_test_history_message(self.store, 3, raw_text="Claim state 3")
        _seed_test_history_message(self.store, 4, raw_text="Claim state 4")
        _seed_test_history_message(self.store, 5, raw_text="Claim state 5")

        props = [
            CandidateClaimProposal(
                subject_entity_id="system:josie",
                predicate=f"state_pred_{i}",
                value_text=f"Proposition for state {i}",
                claim_category="architecture",
                memory_layer="procedural",
                evidence_references=(
                    EvidenceReference(history_message_id=i, relation_type="supports", excerpt=f"state {i}"),
                ),
            )
            for i in range(1, 6)
        ]
        stage_candidate_claims(self.store, props)

        cid1 = compute_candidate_claim_id("system:josie", "state_pred_1", "Proposition for state 1")
        cid2 = compute_candidate_claim_id("system:josie", "state_pred_2", "Proposition for state 2")
        cid3 = compute_candidate_claim_id("system:josie", "state_pred_3", "Proposition for state 3")
        cid4 = compute_candidate_claim_id("system:josie", "state_pred_4", "Proposition for state 4")
        cid5 = compute_candidate_claim_id("system:josie", "state_pred_5", "Proposition for state 5")

        # State 1: candidate (leave cid1 as pending candidate)
        # State 2: rejected
        adjudicate_candidate_claim(self.store, claim_id=cid2, action="reject", reviewer="Dustin")

        # State 3: needs_review / disputed
        adjudicate_candidate_claim(self.store, claim_id=cid3, action="needs_review", reviewer="Dustin")

        # State 4: superseded (first approve cid4, then supersede it with cid5)
        adjudicate_candidate_claim(
            self.store,
            claim_id=cid4,
            action="approve",
            reviewer="Dustin",
            confirmation=APPROVAL_CONFIRMATION,
        )
        # State 5: active canonical (cid5 approves and supersedes cid4)
        adjudicate_candidate_claim(
            self.store,
            claim_id=cid5,
            action="approve",
            reviewer="Dustin",
            supersedes_claim_id=cid4,
            confirmation=APPROVAL_CONFIRMATION,
        )

        manifest = PrimingManifest(task_id="verify_isolation", knowledge_categories=("architecture",))
        bundle = assemble_priming_from_knowledge(manifest, store=self.store)
        primed_ids = {item.item_id for item in bundle.items}

        # Verification of all 5 conditions:
        self.assertNotIn(cid1, primed_ids, "Condition 1 Failed: Pending candidate claim leaked into priming!")
        self.assertNotIn(cid2, primed_ids, "Condition 2 Failed: Rejected claim leaked into priming!")
        self.assertNotIn(cid3, primed_ids, "Condition 3 Failed: Needs-review/disputed claim leaked into priming!")
        self.assertNotIn(cid4, primed_ids, "Condition 4 Failed: Superseded claim leaked into priming!")
        self.assertIn(cid5, primed_ids, "Condition 5 Failed: Approved active canonical claim not in priming!")
        self.assertEqual(len(primed_ids), 1)

    def test_31_approval_gate_strict_human_confirmation_requirements(self) -> None:
        """Approval gate strictly requires human authority AND explicit confirmation token.

        Verifies:
        A. reviewer='Dustin' alone is insufficient (no confirmation token -> fails).
        B. Missing explicit confirmation fails (confirmation=None / confirmation='' -> fails).
        C. Incorrect confirmation token fails (confirmation='CONFIRM', 'yes', etc. -> fails).
        D. Model / worker reviewers fail closed even if token is provided.
        E. Correct explicit human approval succeeds.
        F. Non-approval actions (reject, dispute/needs-review) are restricted to authorized human reviewer.
        """
        _seed_test_history_message(self.store, 1, raw_text="System runs on Linux")
        prop = CandidateClaimProposal(
            subject_entity_id="system:josie",
            predicate="os",
            value_text="System runs on Linux",
            evidence_references=(
                EvidenceReference(history_message_id=1, relation_type="supports", excerpt="runs on Linux"),
            ),
        )
        stage_candidate_claims(self.store, [prop])
        cid = compute_candidate_claim_id("system:josie", "os", "System runs on Linux")

        # A. reviewer='Dustin' alone is insufficient (confirmation omitted/default)
        with self.assertRaises(PermissionError) as ctx:
            adjudicate_candidate_claim(self.store, claim_id=cid, action="approve", reviewer="Dustin")
        self.assertIn("confirmation token", str(ctx.exception).lower())

        # B. Missing explicit confirmation fails
        for missing in [None, "", "   "]:
            with self.assertRaises(PermissionError):
                adjudicate_candidate_claim(
                    self.store,
                    claim_id=cid,
                    action="approve",
                    reviewer="Dustin",
                    confirmation=missing,
                )

        # C. Incorrect confirmation fails
        for bad_token in ["CONFIRM", "YES", "APPROVE", "explicit human approval", "true"]:
            with self.assertRaises(PermissionError) as ctx:
                adjudicate_candidate_claim(
                    self.store,
                    claim_id=cid,
                    action="approve",
                    reviewer="Dustin",
                    confirmation=bad_token,
                )
            self.assertIn("confirmation token", str(ctx.exception).lower())

        # D. Model / worker reviewers fail closed even if token is provided
        for disallowed in ["model", "worker", "opencode", "goose", "assistant", "system", "llm", "agent", "subagent", "ollama"]:
            with self.assertRaises(PermissionError) as ctx:
                adjudicate_candidate_claim(
                    self.store,
                    claim_id=cid,
                    action="approve",
                    reviewer=disallowed,
                    confirmation=APPROVAL_CONFIRMATION,
                )
            self.assertIn("cannot adjudicate or approve", str(ctx.exception).lower())

        # F. Non-approval actions are also gated to authorized human
        with self.assertRaises(PermissionError):
            adjudicate_candidate_claim(self.store, claim_id=cid, action="reject", reviewer="opencode")
        with self.assertRaises(PermissionError):
            adjudicate_candidate_claim(self.store, claim_id=cid, action="needs_review", reviewer="model")
        with self.assertRaises(PermissionError):
            adjudicate_candidate_claim(self.store, claim_id=cid, action="reject", reviewer="unauthorized_person")

        # E. Correct explicit human approval succeeds
        res = adjudicate_candidate_claim(
            self.store,
            claim_id=cid,
            action="approve",
            reviewer="Dustin",
            confirmation=APPROVAL_CONFIRMATION,
            reason="Verified OS statement",
        )
        self.assertEqual(res["status"], "approved")
        self.assertEqual(res["resulting_status"], "active")
        self.assertEqual(res["canonical_effect"], 1)

    def test_32_cli_and_service_live_staging_vs_dry_run(self) -> None:
        """Live staging persists validated non-canonical candidates; dry-run performs zero writes.

        Verifies:
        1. extract_claims_pipeline(stage=False) and CLI extract --dry-run: zero writes.
        2. extract_claims_pipeline(stage=True) and CLI extract --stage:
           - Persists candidates into memory_claims with status='candidate', canonical_effect=0, approved_by=None.
           - Staged candidates have zero priming authority.
        3. Staging is idempotent upon repeated runs.
        4. Out-of-window/malformed evidence fails closed.
        5. Live database D:/Josie/data/josie.db is never touched.
        """
        _seed_test_history_message(self.store, 1, raw_text="System has RTX 3060 installed.")
        _seed_test_history_message(self.store, 2, raw_text="Bernie was named after Bernard from Westworld.")

        extractor = StubClaimExtractor(rule_based=True)

        # 1. Service dry-run: zero database writes
        res_dry = extract_claims_pipeline(self.store, extractor=extractor, stage=False)
        self.assertEqual(res_dry["status"], "dry_run_complete")
        self.assertTrue(res_dry["dry_run"])
        self.assertEqual(res_dry["unique_candidates_staged_count"], 2)

        with self.store._connect() as conn:
            claims_count = conn.execute("SELECT count(*) FROM memory_claims").fetchone()[0]
            self.assertEqual(claims_count, 0, "Dry-run wrote records to memory_claims!")

        # 2. CLI dry-run: zero writes
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["--db", str(self.store.path), "extract", "--dry-run", "--rule-based", "--json"])
        self.assertEqual(code, 0)
        cli_dry_res = json.loads(buf.getvalue())
        self.assertTrue(cli_dry_res["dry_run"])
        with self.store._connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM memory_claims").fetchone()[0], 0)

        # 3. CLI live staging: writes non-canonical candidates
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["--db", str(self.store.path), "extract", "--stage", "--rule-based", "--json"])
        self.assertEqual(code, 0)
        cli_stage_res = json.loads(buf.getvalue())
        self.assertEqual(cli_stage_res["status"], "staged")
        self.assertFalse(cli_stage_res["dry_run"])
        self.assertEqual(cli_stage_res["unique_candidates_staged_count"], 2)

        # Verify staged candidates in SQLite
        with self.store._connect() as conn:
            rows = conn.execute("SELECT * FROM memory_claims").fetchall()
            self.assertEqual(len(rows), 2)
            for r in rows:
                self.assertEqual(r["status"], "candidate")
                self.assertEqual(r["canonical_effect"], 0)
                self.assertIsNone(r["approved_by"])
                self.assertIsNone(r["reviewed_at"])

            # Verify candidate_extractions table has records
            ext_rows = conn.execute("SELECT * FROM candidate_extractions").fetchall()
            self.assertEqual(len(ext_rows), 2)

            # Verify claim_evidence has records
            ev_rows = conn.execute("SELECT * FROM claim_evidence").fetchall()
            self.assertEqual(len(ev_rows), 2)

        # 4. Zero priming authority for staged candidates
        manifest = PrimingManifest(task_id="hardware_check", knowledge_categories=("hardware", "identity"))
        bundle = assemble_priming_from_knowledge(manifest, store=self.store)
        self.assertEqual(len(bundle.items), 0, "Staged candidates leaked into priming!")

        # 5. Idempotency: Re-running live staging does not create duplicates
        res_re = extract_claims_pipeline(self.store, extractor=extractor, stage=True)
        self.assertEqual(res_re["status"], "staged")
        with self.store._connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM memory_claims").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT count(*) FROM claim_evidence").fetchone()[0], 2)

        # 6. Malformed / out-of-window evidence fails closed
        out_of_window_prop = CandidateClaimProposal(
            subject_entity_id="system:josie",
            predicate="oow",
            value_text="Out of window",
            evidence_references=(
                EvidenceReference(history_message_id=9999, relation_type="supports", excerpt="bogus"),
            ),
        )
        stage_fail = stage_candidate_claims(self.store, [out_of_window_prop], window_message_ids={1, 2})
        self.assertEqual(stage_fail["invalid_proposals_count"], 1)
        self.assertEqual(stage_fail["unique_candidate_claims_count"], 0)

    def test_33_candidate_extractions_schema_initialized_on_fresh_store(self) -> None:
        """candidate_extractions table is initialized centrally in LocalStore on a fresh database."""
        fresh_dir = tempfile.mkdtemp(prefix="josie_fresh_store_")
        try:
            fresh_db = Path(fresh_dir) / "fresh.db"
            fresh_store = LocalStore(fresh_db)
            with fresh_store._connect() as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                self.assertIn("candidate_extractions", tables)
                self.assertIn("memory_claims", tables)
                self.assertIn("claim_evidence", tables)
                self.assertIn("canonical_adjudications", tables)

                # Verify column schema
                cols = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(candidate_extractions)").fetchall()
                }
                expected_cols = {
                    "extraction_id", "claim_id", "extractor_id", "extractor_version",
                    "extracted_at", "claim_category", "temporal_hint", "notes",
                    "raw_proposal_json", "created_at"
                }
                self.assertEqual(cols, expected_cols)
        finally:
            shutil.rmtree(fresh_dir, ignore_errors=True)

    def test_34_local_model_extractor_wiring_and_normalization(self) -> None:
        """LocalModelClaimExtractor normalizes entity IDs, enriches evidence references, and integrates with CLI."""
        _seed_test_history_message(
            self.store,
            42,
            raw_text="I have two 4TB NVMe drives on hand.",
            role="user",
            speaker="google_account_owner",
            timestamp="2026-08-20T10:00:00Z",
        )

        mock_response_payload = {
            "message": {
                "content": json.dumps({
                    "proposals": [
                        {
                            "subject_entity_id": "google_account_owner",
                            "predicate": "owns-hardware",
                            "value_text": "Dustin owns two 4TB NVMe drives.",
                            "claim_category": "hardware",
                            "confidence": 0.95,
                            "confidence_basis": "Direct statement by user in message 42",
                            "evidence_references": [
                                {
                                    "history_message_id": 42,
                                    "relation_type": "supports",
                                    "excerpt": "two 4TB NVMe drives",
                                }
                            ],
                        }
                    ]
                })
            }
        }

        class FakeHTTPResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self):
                return json.dumps(mock_response_payload).encode("utf-8")

        extractor = LocalModelClaimExtractor(model="qwen3:14b")
        messages = [
            {
                "message_id": 42,
                "role": "user",
                "speaker": "google_account_owner",
                "timestamp": "2026-08-20T10:00:00Z",
                "raw_text": "I have two 4TB NVMe drives on hand.",
            }
        ]

        with patch("josie.candidate_claims.urlopen", return_value=FakeHTTPResponse()):
            props = extractor.extract_claims(messages)
            self.assertEqual(len(props), 1)
            p = props[0]
            # Verify subject normalized to person:dustin
            self.assertEqual(p.subject_entity_id, "person:dustin")
            # Verify predicate sanitized to alphanumeric/underscores
            self.assertEqual(p.predicate, "owns_hardware")
            self.assertEqual(p.claim_category, "hardware")
            # Verify evidence enriched with role and speaker
            self.assertEqual(len(p.evidence_references), 1)
            ref = p.evidence_references[0]
            self.assertEqual(ref.history_message_id, 42)
            self.assertEqual(ref.role, "user")
            self.assertEqual(ref.speaker, "google_account_owner")

            # CLI dry-run with --local-model flag
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main([
                    "--db", str(self.store.path),
                    "extract", "--dry-run", "--local-model", "--message-ids", "42", "--json"
                ])
            self.assertEqual(code, 0)
            dry_out = json.loads(buf.getvalue())
            self.assertEqual(dry_out["status"], "dry_run_complete")
            self.assertTrue(dry_out["dry_run"])
            self.assertEqual(dry_out["unique_candidates_staged_count"], 1)

            # Ensure zero database writes during dry-run
            with self.store._connect() as conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM memory_claims").fetchone()[0], 0)

            # CLI live staging with --local-model flag
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main([
                    "--db", str(self.store.path),
                    "extract", "--stage", "--local-model", "--message-ids", "42", "--json"
                ])
            self.assertEqual(code, 0)
            stage_out = json.loads(buf.getvalue())
            self.assertEqual(stage_out["status"], "staged")
            self.assertFalse(stage_out["dry_run"])
            self.assertEqual(stage_out["unique_candidates_staged_count"], 1)

            # Verify persisted record in memory_claims
            with self.store._connect() as conn:
                claims = conn.execute("SELECT * FROM memory_claims").fetchall()
                self.assertEqual(len(claims), 1)
                c = claims[0]
                self.assertEqual(c["subject_entity_id"], "person:dustin")
                self.assertEqual(c["predicate"], "owns_hardware")
                self.assertEqual(c["status"], "candidate")
                self.assertEqual(c["canonical_effect"], 0)
                self.assertIsNone(c["approved_by"])
                self.assertIsNone(c["reviewed_at"])

            # Verify candidate has zero priming authority
            manifest = PrimingManifest(task_id="check_hw", knowledge_categories=("hardware",))
            bundle = assemble_priming_from_knowledge(manifest, store=self.store)
            self.assertEqual(len(bundle.items), 0)


if __name__ == "__main__":
    unittest.main()

