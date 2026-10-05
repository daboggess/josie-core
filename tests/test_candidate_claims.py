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
    ALLOWED_ATTRIBUTIONS,
    ALLOWED_CLAIM_CATEGORIES,
    ALLOWED_DURABILITIES,
    ALLOWED_EPISTEMIC_MODES,
    ALLOWED_MEMORY_DESTINATIONS,
    APPROVAL_CONFIRMATION,
    BoundedEvidenceBundle,
    CATEGORY_TO_MEMORY_LAYER,
    CandidateClaimProposal,
    CandidateClaimRecord,
    EvidenceReference,
    LocalModelClaimExtractor,
    StubClaimExtractor,
    adjudicate_candidate_claim,
    check_claim_evidence_entailment,
    check_event_vs_preference,
    check_hypothetical_or_fictional,
    classify_epistemic_mode,
    classify_evidence_attribution,
    classify_evidence_span,
    classify_memory_destination,
    clear_unadjudicated_candidate_claims,
    compute_candidate_claim_id,
    dry_run_extraction,
    evaluate_evidence_weight,
    extract_claims_pipeline,
    get_candidate_claim_details,
    get_pasted_regions,
    infer_claim_category,
    infer_durability,
    is_canonical_eligible,
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


class TestEvidenceAttribution(unittest.TestCase):
    """Phase 3B.1 Tests: Evidence Attribution, Envelope Role Decoupling, and Identity Separation."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_attr.db"
        self.store = LocalStore(self.db_path)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_a_direct_user_assertion(self) -> None:
        """Test A: Direct user statement ('Btw i dont own a 3090') receives primary authority."""
        _seed_test_history_message(
            self.store,
            message_id=489,
            raw_text="Btw i dont own a 3090",
            role="user",
            speaker="Dustin",
        )
        attr = classify_evidence_attribution(
            role="user",
            speaker="Dustin",
            raw_text="Btw i dont own a 3090",
            excerpt="Btw i dont own a 3090",
        )
        self.assertEqual(attr, "direct_user_assertion")

        ref = EvidenceReference(
            history_message_id=489,
            relation_type="supports",
            excerpt="Btw i dont own a 3090",
            role="user",
            speaker="Dustin",
            attribution=attr,
        )
        conf, basis, e_class = evaluate_evidence_weight([ref], base_confidence=0.9)
        self.assertGreaterEqual(conf, 0.85)
        self.assertEqual(e_class, "RETRIEVED")
        self.assertIn("Direct user statement", basis)

    def test_b_user_message_containing_pasted_text(self) -> None:
        """Test B: Pasted assistant content inside user envelope is classified as quoted/pasted, NOT direct user."""
        raw_pasted = (
            "Gpt response \n\n"
            "Alright Soph, here's the real truth\n\n"
            "Your parts on hand (2x 24TB Exos, 2x 4TB NVMe, RTX 3090)"
        )
        _seed_test_history_message(
            self.store,
            message_id=485,
            raw_text=raw_pasted,
            role="user",
            speaker="google_account_owner",
        )
        attr = classify_evidence_attribution(
            role="user",
            speaker="google_account_owner",
            raw_text=raw_pasted,
            excerpt="Your parts on hand (2x 24TB Exos, 2x 4TB NVMe, RTX 3090)",
            proposed_attribution="direct_user_assertion",  # Attempted false direct assertion
        )
        self.assertEqual(attr, "quoted_or_pasted_content")

        ref = EvidenceReference(
            history_message_id=485,
            relation_type="supports",
            excerpt="Your parts on hand (RTX 3090)",
            role="user",
            speaker="google_account_owner",
            attribution=attr,
        )
        conf, basis, e_class = evaluate_evidence_weight([ref], base_confidence=0.95)
        self.assertLessEqual(conf, 0.60)
        self.assertEqual(e_class, "INFERRED")
        self.assertIn("Quoted or pasted external content", basis)

    def test_c_gemini_assistant_output_identity_isolation(self) -> None:
        """Test C: Gemini output maps to assistant:gemini (NOT system:josie) and assistant_assertion."""
        _seed_test_history_message(
            self.store,
            message_id=478,
            raw_text="The RTX 2080 Ti 22GB Modded Edition is unreliable for long-term AI work.",
            role="assistant",
            speaker="Gemini Apps",
        )
        attr = classify_evidence_attribution(
            role="assistant",
            speaker="Gemini Apps",
            raw_text="The RTX 2080 Ti 22GB Modded Edition is unreliable for long-term AI work.",
            excerpt="unreliable for long-term AI work",
        )
        self.assertEqual(attr, "assistant_assertion")

        ref = EvidenceReference(
            history_message_id=478,
            relation_type="supports",
            excerpt="unreliable for long-term AI work",
            role="assistant",
            speaker="Gemini Apps",
            attribution=attr,
        )
        conf, basis, e_class = evaluate_evidence_weight([ref], base_confidence=0.9)
        self.assertLessEqual(conf, 0.60)
        self.assertEqual(e_class, "INFERRED")
        self.assertIn("Assistant assertion", basis)

        # Stage with assistant:gemini subject entity ID
        proposal = CandidateClaimProposal(
            subject_entity_id="assistant:gemini",
            predicate="warns_against_hardware",
            value_text="Modded RTX 2080 Ti is unreliable",
            claim_category="hardware",
            confidence=0.6,
            confidence_basis=basis,
            evidence_references=(ref,),
        )
        res = stage_candidate_claims(self.store, [proposal])
        self.assertEqual(res["unique_candidate_claims_count"], 1)
        staged = res["staged_claims"][0]
        self.assertEqual(staged["subject_entity_id"], "assistant:gemini")
        self.assertNotEqual(staged["subject_entity_id"], "system:josie")

    def test_d_ambiguous_source_attribution(self) -> None:
        """Test D: Ambiguous text without clear speaker/provenance receives ambiguous_source attribution."""
        _seed_test_history_message(
            self.store,
            message_id=999,
            raw_text="Unattributed notes without identified speaker.",
            role="system",
            speaker="unknown_source",
        )
        attr = classify_evidence_attribution(
            role="system",
            speaker="unknown_source",
            raw_text="Unattributed notes without identified speaker.",
            excerpt="Unattributed notes",
        )
        self.assertEqual(attr, "ambiguous_source")

        ref = EvidenceReference(
            history_message_id=999,
            relation_type="supports",
            excerpt="Unattributed notes",
            role="system",
            speaker="unknown_source",
            attribution=attr,
        )
        conf, basis, e_class = evaluate_evidence_weight([ref], base_confidence=0.9)
        self.assertLessEqual(conf, 0.50)
        self.assertEqual(e_class, "INFERRED")
        self.assertIn("Historical conversation context (ambiguous source)", basis)

    def test_e_authority_hierarchy_ordering(self) -> None:
        """Test E: Direct-user evidence receives greater authority than assistant, quoted, or ambiguous."""
        ref_user = EvidenceReference(
            history_message_id=1,
            attribution="direct_user_assertion",
            role="user",
            speaker="Dustin",
        )
        ref_quoted = EvidenceReference(
            history_message_id=2,
            attribution="quoted_or_pasted_content",
            role="user",
            speaker="google_account_owner",
        )
        ref_assistant = EvidenceReference(
            history_message_id=3,
            attribution="assistant_assertion",
            role="assistant",
            speaker="Gemini Apps",
        )
        ref_ambiguous = EvidenceReference(
            history_message_id=4,
            attribution="ambiguous_source",
            role="unknown",
            speaker="unknown",
        )

        conf_user, _, class_user = evaluate_evidence_weight([ref_user], base_confidence=0.9)
        conf_quoted, _, class_quoted = evaluate_evidence_weight([ref_quoted], base_confidence=0.9)
        conf_asst, _, class_asst = evaluate_evidence_weight([ref_assistant], base_confidence=0.9)
        conf_ambig, _, class_ambig = evaluate_evidence_weight([ref_ambiguous], base_confidence=0.9)

        self.assertGreater(conf_user, conf_quoted)
        self.assertGreater(conf_user, conf_asst)
        self.assertGreater(conf_user, conf_ambig)
        self.assertGreater(conf_quoted, conf_ambig)
        self.assertEqual(class_user, "RETRIEVED")
        self.assertEqual(class_quoted, "INFERRED")
        self.assertEqual(class_asst, "INFERRED")
        self.assertEqual(class_ambig, "INFERRED")

    def test_f_attribution_cannot_bypass_adjudication_gate(self) -> None:
        """Test F: Attribution change cannot bypass candidate status or human approval requirement."""
        _seed_test_history_message(
            self.store,
            message_id=10,
            raw_text="Direct statement from Dustin",
            role="user",
            speaker="Dustin",
        )
        ref = EvidenceReference(
            history_message_id=10,
            relation_type="supports",
            excerpt="Direct statement from Dustin",
            role="user",
            speaker="Dustin",
            attribution="direct_user_assertion",
        )
        proposal = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="direct_fact",
            value_text="A fact stated directly by Dustin",
            claim_category="profile",
            confidence=0.95,
            evidence_references=(ref,),
        )
        res = stage_candidate_claims(self.store, [proposal])
        cid = res["staged_claims"][0]["claim_id"]

        with self.store._connect() as conn:
            claim = conn.execute("SELECT * FROM memory_claims WHERE claim_id = ?", (cid,)).fetchone()
            self.assertEqual(claim["status"], "candidate")
            self.assertEqual(claim["canonical_effect"], 0)
            self.assertIsNone(claim["approved_by"])

        # Attempted model approval fails closed
        with self.assertRaises((PermissionError, ValueError)):
            adjudicate_candidate_claim(
                self.store,
                claim_id=cid,
                action="approve",
                reviewer="model",
                confirmation=APPROVAL_CONFIRMATION,
            )

        # Attempted human approval without confirmation token fails closed
        with self.assertRaises((PermissionError, ValueError)):
            adjudicate_candidate_claim(
                self.store,
                claim_id=cid,
                action="approve",
                reviewer="Dustin",
                confirmation="unconfirmed",
            )

    def test_g_zero_candidate_priming_leakage(self) -> None:
        """Test G: No candidate claim with any attribution leaks into priming bundles."""
        _seed_test_history_message(
            self.store,
            message_id=20,
            raw_text="User statement",
            role="user",
            speaker="Dustin",
        )
        _seed_test_history_message(
            self.store,
            message_id=21,
            raw_text="Gpt response \n\nPasted info",
            role="user",
            speaker="Dustin",
        )
        _seed_test_history_message(
            self.store,
            message_id=22,
            raw_text="Assistant opinion",
            role="assistant",
            speaker="Gemini Apps",
        )

        p1 = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="user_pref",
            value_text="User preference value",
            claim_category="preference",
            evidence_references=(EvidenceReference(history_message_id=20, attribution="direct_user_assertion"),),
        )
        p2 = CandidateClaimProposal(
            subject_entity_id="assistant:chatgpt",
            predicate="quoted_statement",
            value_text="Pasted third-party statement",
            claim_category="general",
            evidence_references=(EvidenceReference(history_message_id=21, attribution="quoted_or_pasted_content"),),
        )
        p3 = CandidateClaimProposal(
            subject_entity_id="assistant:gemini",
            predicate="assistant_opinion",
            value_text="Gemini assistant opinion",
            claim_category="hardware",
            evidence_references=(EvidenceReference(history_message_id=22, attribution="assistant_assertion"),),
        )

        stage_candidate_claims(self.store, [p1, p2, p3])

        for cat in ("preference", "general", "hardware"):
            manifest = PrimingManifest(task_id="leak_test", knowledge_categories=(cat,))
            bundle = assemble_priming_from_knowledge(manifest, store=self.store)
            self.assertEqual(len(bundle.items), 0, f"Candidate in category '{cat}' leaked into priming bundle!")


class TestSpanEvidenceAttribution(unittest.TestCase):
    """Test suite for Phase 3B.2 Span-Level Evidence Attribution and Mixed-Message Handling."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="josie-span-test-")
        self.db_path = Path(self.temp_dir) / "test_span.db"
        self.store = LocalStore(self.db_path)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_a_mixed_message_different_semantic_attributions(self) -> None:
        """A. A single message may contain evidence spans with different semantic attribution."""
        raw_msg_485 = (
            "Gpt response \n\n"
            "Btw i am a+ certified with years of experience with commercial servers\n\n"
            "Alright Soph, here’s the real truth — cut through all the noise...\n"
            "Your parts on hand (2× 24TB Exos, 2× 4TB NVMe, RTX 3090)"
        )
        _seed_test_history_message(
            self.store,
            message_id=485,
            raw_text=raw_msg_485,
            role="user",
            speaker="google_account_owner",
        )

        span_a = "Btw i am a+ certified with years of experience with commercial servers"
        span_b = "Your parts on hand (2× 24TB Exos, 2× 4TB NVMe, RTX 3090)"

        attr_a, start_a, end_a = classify_evidence_span(
            raw_text=raw_msg_485,
            excerpt=span_a,
            role="user",
            speaker="google_account_owner",
        )
        attr_b, start_b, end_b = classify_evidence_span(
            raw_text=raw_msg_485,
            excerpt=span_b,
            role="user",
            speaker="google_account_owner",
        )

        self.assertEqual(attr_a, "direct_user_assertion")
        self.assertIsNotNone(start_a)
        self.assertIsNotNone(end_a)
        self.assertEqual(raw_msg_485[start_a:end_a], span_a)

        self.assertEqual(attr_b, "quoted_or_pasted_content")
        self.assertIsNotNone(start_b)
        self.assertIsNotNone(end_b)
        self.assertEqual(raw_msg_485[start_b:end_b], span_b)

        # Stage both claims referencing the SAME message ID 485
        ref_a = EvidenceReference(
            history_message_id=485,
            relation_type="supports",
            excerpt=span_a,
            role="user",
            speaker="google_account_owner",
            attribution=attr_a,
            span_start=start_a,
            span_end=end_a,
        )
        ref_b = EvidenceReference(
            history_message_id=485,
            relation_type="supports",
            excerpt=span_b,
            role="user",
            speaker="google_account_owner",
            attribution=attr_b,
            span_start=start_b,
            span_end=end_b,
        )

        prop_a = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="has_professional_certification",
            value_text="A+ certified with years of experience with commercial servers",
            claim_category="profile",
            evidence_references=(ref_a,),
        )
        prop_b = CandidateClaimProposal(
            subject_entity_id="assistant:chatgpt",
            predicate="lists_hardware_on_hand",
            value_text="ChatGPT lists parts on hand including RTX 3090",
            claim_category="hardware",
            evidence_references=(ref_b,),
        )

        res = stage_candidate_claims(self.store, [prop_a, prop_b])
        self.assertEqual(res["unique_candidate_claims_count"], 2)

        # Inspect details of both staged claims
        cid_a = res["staged_claims"][0]["claim_id"]
        cid_b = res["staged_claims"][1]["claim_id"]
        det_a = get_candidate_claim_details(self.store, cid_a)
        det_b = get_candidate_claim_details(self.store, cid_b)

        self.assertIsNotNone(det_a)
        self.assertIsNotNone(det_b)
        self.assertEqual(det_a["evidence_references"][0]["attribution"], "direct_user_assertion")
        self.assertEqual(det_b["evidence_references"][0]["attribution"], "quoted_or_pasted_content")
        self.assertEqual(det_a["evidence_references"][0]["history_message_id"], 485)
        self.assertEqual(det_b["evidence_references"][0]["history_message_id"], 485)
        self.assertNotEqual(det_a["evidence_references"][0]["evidence_id"], det_b["evidence_references"][0]["evidence_id"])

    def test_b_role_user_does_not_force_direct_user_authority(self) -> None:
        """B. Provider 'role=user' does not force all spans to direct-user authority."""
        raw_text = (
            "Gpt response \n\n"
            "Alright Soph, here’s the real truth...\n"
            "Your parts on hand include an RTX 3090"
        )
        _seed_test_history_message(
            self.store,
            message_id=501,
            raw_text=raw_text,
            role="user",
            speaker="google_account_owner",
        )

        # Proposing direct_user_assertion for a span inside the pasted block must fail validation
        prop_invalid = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="owns_hardware",
            value_text="Dustin owns an RTX 3090",
            claim_category="hardware",
            evidence_references=(
                EvidenceReference(
                    history_message_id=501,
                    relation_type="supports",
                    excerpt="Your parts on hand include an RTX 3090",
                    attribution="direct_user_assertion",
                ),
            ),
        )
        valid, reason = validate_proposal(prop_invalid, store=self.store)
        self.assertFalse(valid)
        self.assertIn("Proposed attribution 'direct_user_assertion' not permitted", reason)

        # Properly proposing quoted_or_pasted_content succeeds and caps confidence at <= 0.60
        prop_valid = CandidateClaimProposal(
            subject_entity_id="assistant:chatgpt",
            predicate="claims_hardware",
            value_text="Pasted ChatGPT text claims RTX 3090",
            claim_category="hardware",
            confidence=0.9,
            evidence_references=(
                EvidenceReference(
                    history_message_id=501,
                    relation_type="supports",
                    excerpt="Your parts on hand include an RTX 3090",
                    attribution="quoted_or_pasted_content",
                ),
            ),
        )
        res = stage_candidate_claims(self.store, [prop_valid])
        self.assertEqual(res["unique_candidate_claims_count"], 1)
        staged = res["staged_claims"][0]
        self.assertLessEqual(staged["confidence"], 0.60)
        self.assertEqual(staged["evidence_class"], "INFERRED")

    def test_c_supporting_excerpt_must_exist_in_referenced_message(self) -> None:
        """C. Supporting excerpt/span must actually exist in the referenced message."""
        raw_text = "I am testing the new server chassis."
        _seed_test_history_message(self.store, message_id=601, raw_text=raw_text)

        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="hardware_action",
            value_text="Dustin is testing the new server chassis",
            evidence_references=(
                EvidenceReference(
                    history_message_id=601,
                    relation_type="supports",
                    excerpt="testing the new server chassis",
                ),
            ),
        )
        valid, reason = validate_proposal(prop, store=self.store)
        self.assertTrue(valid, f"Validation failed unexpectedly: {reason}")

    def test_d_invalid_or_fabricated_excerpts_fail_closed(self) -> None:
        """D. Invalid or fabricated excerpts fail closed."""
        raw_text = "I have two Seagate Exos 24TB drives."
        _seed_test_history_message(self.store, message_id=602, raw_text=raw_text)

        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="owns_hardware",
            value_text="Dustin owns four Western Digital drives",
            evidence_references=(
                EvidenceReference(
                    history_message_id=602,
                    relation_type="supports",
                    excerpt="four Western Digital drives",  # Fabricated, does not occur in message
                ),
            ),
        )
        valid, reason = validate_proposal(prop, store=self.store)
        self.assertFalse(valid)
        self.assertIn("Supporting excerpt does not exist in historical message", reason)

        # stage_candidate_claims should fail closed and not persist fabricated claims
        res = stage_candidate_claims(self.store, [prop])
        self.assertEqual(res["unique_candidate_claims_count"], 0)
        self.assertEqual(len(res["invalid_proposals"]), 1)

    def test_e_invalid_offsets_fail_closed(self) -> None:
        """E. Invalid offsets fail closed."""
        # 1. Constructor checks
        with self.assertRaises(ValueError):
            EvidenceReference(history_message_id=1, span_start=-1, span_end=10)

        with self.assertRaises(ValueError):
            EvidenceReference(history_message_id=1, span_start=20, span_end=10)

        with self.assertRaises(ValueError):
            EvidenceReference(history_message_id=1, span_start=10, span_end=None)

        # 2. Out-of-bounds offset check against message text
        raw_text = "Short text."  # length 11
        _seed_test_history_message(self.store, message_id=603, raw_text=raw_text)

        prop_oob = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="text_check",
            value_text="Short text check",
            evidence_references=(
                EvidenceReference(
                    history_message_id=603,
                    relation_type="supports",
                    excerpt="Short text.",
                    span_start=0,
                    span_end=50,  # exceeds len(raw_text) == 11
                ),
            ),
        )
        valid, reason = validate_proposal(prop_oob, store=self.store)
        self.assertFalse(valid)
        self.assertIn("out of bounds for message 603", reason)

        # 3. Mismatch between span slice and excerpt
        prop_mismatch = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="text_check",
            value_text="Short text check",
            evidence_references=(
                EvidenceReference(
                    history_message_id=603,
                    relation_type="supports",
                    excerpt="Completely different text",
                    span_start=0,
                    span_end=5,
                ),
            ),
        )
        valid_m, reason_m = validate_proposal(prop_mismatch, store=self.store)
        self.assertFalse(valid_m)
        self.assertIn("does not match excerpt", reason_m)

    def test_f_direct_dustin_span_higher_weight_than_pasted_span(self) -> None:
        """F. Direct Dustin span can receive higher evidence weight than pasted span in the same provider message."""
        raw_msg = (
            "Gpt response \n\n"
            "Btw i am a+ certified with years of experience with commercial servers\n\n"
            "Alright Soph, here’s the real truth...\n"
            "Your parts on hand include an RTX 3090"
        )
        _seed_test_history_message(self.store, message_id=701, raw_text=raw_msg, role="user", speaker="Dustin")

        span_user = "Btw i am a+ certified with years of experience with commercial servers"
        span_ai = "Your parts on hand include an RTX 3090"

        attr_user, s1, e1 = classify_evidence_span(raw_text=raw_msg, excerpt=span_user, role="user", speaker="Dustin")
        attr_ai, s2, e2 = classify_evidence_span(raw_text=raw_msg, excerpt=span_ai, role="user", speaker="Dustin")

        ref_user = EvidenceReference(
            history_message_id=701,
            excerpt=span_user,
            attribution=attr_user,
            span_start=s1,
            span_end=e1,
            role="user",
            speaker="Dustin",
        )
        ref_ai = EvidenceReference(
            history_message_id=701,
            excerpt=span_ai,
            attribution=attr_ai,
            span_start=s2,
            span_end=e2,
            role="user",
            speaker="Dustin",
        )

        conf_user, basis_user, class_user = evaluate_evidence_weight([ref_user], base_confidence=0.95)
        conf_ai, basis_ai, class_ai = evaluate_evidence_weight([ref_ai], base_confidence=0.95)

        self.assertGreater(conf_user, conf_ai)
        self.assertGreaterEqual(conf_user, 0.85)
        self.assertLessEqual(conf_ai, 0.60)
        self.assertEqual(class_user, "RETRIEVED")
        self.assertEqual(class_ai, "INFERRED")

    def test_g_gemini_remains_assistant_gemini(self) -> None:
        """G. Gemini remains 'assistant:gemini' and is never elevated to 'system:josie'."""
        raw_gemini = "Z690 motherboard with i7-12700K is the lowest-friction setup."
        _seed_test_history_message(
            self.store,
            message_id=801,
            raw_text=raw_gemini,
            role="assistant",
            speaker="Gemini Apps",
        )
        attr, start, end = classify_evidence_span(
            raw_text=raw_gemini,
            excerpt="lowest-friction setup",
            role="assistant",
            speaker="Gemini Apps",
        )
        self.assertEqual(attr, "assistant_assertion")

        ref = EvidenceReference(
            history_message_id=801,
            excerpt="lowest-friction setup",
            attribution=attr,
            span_start=start,
            span_end=end,
            role="assistant",
            speaker="Gemini Apps",
        )
        prop = CandidateClaimProposal(
            subject_entity_id="assistant:gemini",
            predicate="recommends_build",
            value_text="Z690 is lowest friction",
            claim_category="hardware",
            evidence_references=(ref,),
        )
        res = stage_candidate_claims(self.store, [prop])
        self.assertEqual(res["unique_candidate_claims_count"], 1)
        staged = res["staged_claims"][0]
        self.assertEqual(staged["subject_entity_id"], "assistant:gemini")
        self.assertNotEqual(staged["subject_entity_id"], "system:josie")
        self.assertLessEqual(staged["confidence"], 0.60)

    def test_h_no_span_attribution_bypasses_human_adjudication(self) -> None:
        """H. No span-attribution path bypasses human adjudication."""
        raw_text = "I built the entire server cluster myself."
        _seed_test_history_message(self.store, message_id=901, raw_text=raw_text, role="user", speaker="Dustin")

        ref = EvidenceReference(
            history_message_id=901,
            excerpt="built the entire server cluster myself",
            attribution="direct_user_assertion",
        )
        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="built_cluster",
            value_text="Dustin built server cluster",
            claim_category="profile",
            evidence_references=(ref,),
        )
        res = stage_candidate_claims(self.store, [prop])
        cid = res["staged_claims"][0]["claim_id"]

        with self.store._connect() as conn:
            row = conn.execute("SELECT status, canonical_effect, approved_by FROM memory_claims WHERE claim_id = ?", (cid,)).fetchone()
            self.assertEqual(row["status"], "candidate")
            self.assertEqual(row["canonical_effect"], 0)
            self.assertIsNone(row["approved_by"])

        # Model approval fails
        with self.assertRaises((PermissionError, ValueError)):
            adjudicate_candidate_claim(self.store, claim_id=cid, action="approve", reviewer="model", confirmation=APPROVAL_CONFIRMATION)

        # Unconfirmed approval fails
        with self.assertRaises((PermissionError, ValueError)):
            adjudicate_candidate_claim(self.store, claim_id=cid, action="approve", reviewer="Dustin", confirmation="")

    def test_i_no_candidate_leaks_into_priming(self) -> None:
        """I. No candidate claim with span attribution leaks into priming bundles."""
        raw_text = "Important fact from user span."
        _seed_test_history_message(self.store, message_id=1001, raw_text=raw_text, role="user", speaker="Dustin")

        ref = EvidenceReference(
            history_message_id=1001,
            excerpt=raw_text,
            attribution="direct_user_assertion",
        )
        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="span_fact",
            value_text="Important fact from user span",
            claim_category="architecture",
            evidence_references=(ref,),
        )
        stage_candidate_claims(self.store, [prop])

        manifest = PrimingManifest(task_id="priming_test", knowledge_categories=("architecture",))
        bundle = assemble_priming_from_knowledge(manifest, store=self.store)
        self.assertEqual(len(bundle.items), 0)

    def test_critical_fixture_message_485_pattern(self) -> None:
        """Critical Fixture (Requirement 6): Synthetic message matching Message 485 structure.

        Proves:
        Claim A: 'Dustin has A+ certification with commercial server experience' receives direct_user_assertion.
        Claim B: 'Dustin owns RTX 3090' must NOT receive direct Dustin authority merely because it appears in the same message.
        Claim A and Claim B are NOT forced to share one attribution solely because they occur in one message.
        """
        raw_msg_485 = (
            "Gpt response \n\n"
            "Btw i am a+ certified with years of experience with commercial servers\n\n"
            "Alright Soph, here’s the real truth – cut through all the noise...\n"
            "Your parts on hand include an RTX 3090..."
        )
        _seed_test_history_message(
            self.store,
            message_id=485,
            raw_text=raw_msg_485,
            role="user",
            speaker="google_account_owner",
        )

        span_a = "Btw i am a+ certified with years of experience with commercial servers"
        span_b = "Your parts on hand include an RTX 3090..."

        attr_a, s_a, e_a = classify_evidence_span(raw_text=raw_msg_485, excerpt=span_a, role="user", speaker="google_account_owner")
        attr_b, s_b, e_b = classify_evidence_span(raw_text=raw_msg_485, excerpt=span_b, role="user", speaker="google_account_owner")

        # Claim A: Dustin-authored credential
        self.assertEqual(attr_a, "direct_user_assertion")
        ref_a = EvidenceReference(
            history_message_id=485,
            relation_type="supports",
            excerpt=span_a,
            attribution=attr_a,
            span_start=s_a,
            span_end=e_a,
        )

        # Claim B: Pasted assistant assertion
        self.assertEqual(attr_b, "quoted_or_pasted_content")
        ref_b = EvidenceReference(
            history_message_id=485,
            relation_type="supports",
            excerpt=span_b,
            attribution=attr_b,
            span_start=s_b,
            span_end=e_b,
        )

        prop_a = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="has_professional_certification",
            value_text="Dustin has A+ certification with commercial server experience",
            claim_category="profile",
            evidence_references=(ref_a,),
        )
        prop_b = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="owns_hardware",
            value_text="Dustin owns an RTX 3090",
            claim_category="hardware",
            confidence=0.9,  # Proposed 0.9, but must be demoted
            evidence_references=(ref_b,),
        )

        res = stage_candidate_claims(self.store, [prop_a, prop_b])
        self.assertEqual(res["unique_candidate_claims_count"], 2)

        staged_a = res["staged_claims"][0]
        staged_b = res["staged_claims"][1]

        # Claim A achieves primary authority
        self.assertEqual(staged_a["evidence_class"], "RETRIEVED")
        self.assertGreaterEqual(staged_a["confidence"], 0.85)

        # Claim B is demoted to secondary authority (capped at <= 0.60)
        self.assertEqual(staged_b["evidence_class"], "INFERRED")
        self.assertLessEqual(staged_b["confidence"], 0.60)
        self.assertIn("Quoted or pasted external content", staged_b["confidence_basis"])

    def test_direct_correction_fixture_message_485_vs_489(self) -> None:
        """Direct Correction Fixture (Requirement 7):
        Message 485 mixed-source statement: '... RTX 3090 ...'
        Later Message 489 direct Dustin statement: 'Btw i dont own a 3090'

        Verify:
        - Msg 489 remains 'direct_user_assertion'
        - High-confidence direct-user evidence outranks the pasted older statement
        - Neither is automatically canonical
        - Chronology and contradiction remain visible for later adjudication
        """
        raw_485 = (
            "Gpt response \n\n"
            "Btw i am a+ certified with years of experience with commercial servers\n\n"
            "Alright Soph, here’s the real truth...\n"
            "Your parts on hand (2× 24TB Exos, 2× 4TB NVMe, RTX 3090)"
        )
        raw_489 = "Btw i dont own a 3090"

        _seed_test_history_message(
            self.store,
            message_id=485,
            raw_text=raw_485,
            role="user",
            speaker="google_account_owner",
            timestamp="2025-11-27T21:05:00Z",
        )
        _seed_test_history_message(
            self.store,
            message_id=489,
            raw_text=raw_489,
            role="user",
            speaker="google_account_owner",
            timestamp="2025-11-27T21:09:00Z",
        )

        span_485 = "Your parts on hand (2× 24TB Exos, 2× 4TB NVMe, RTX 3090)"
        span_489 = "Btw i dont own a 3090"

        attr_485, s1, e1 = classify_evidence_span(raw_text=raw_485, excerpt=span_485, role="user")
        attr_489, s2, e2 = classify_evidence_span(raw_text=raw_489, excerpt=span_489, role="user")

        self.assertEqual(attr_485, "quoted_or_pasted_content")
        self.assertEqual(attr_489, "direct_user_assertion")

        ref_485 = EvidenceReference(
            history_message_id=485,
            relation_type="supports",
            excerpt=span_485,
            attribution=attr_485,
            span_start=s1,
            span_end=e1,
            source_timestamp="2025-11-27T21:05:00Z",
        )
        ref_489 = EvidenceReference(
            history_message_id=489,
            relation_type="supports",
            excerpt=span_489,
            attribution=attr_489,
            span_start=s2,
            span_end=e2,
            source_timestamp="2025-11-27T21:09:00Z",
        )

        prop_old = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="hardware_inventory",
            value_text="Dustin parts on hand include RTX 3090",
            claim_category="hardware",
            confidence=0.8,
            evidence_references=(ref_485,),
        )
        prop_corr = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="does_not_own_hardware",
            value_text="does not own an RTX 3090",
            claim_category="hardware",
            confidence=0.95,
            evidence_references=(ref_489,),
        )

        res = stage_candidate_claims(self.store, [prop_old, prop_corr])
        self.assertEqual(res["unique_candidate_claims_count"], 2)

        staged_old = res["staged_claims"][0]
        staged_corr = res["staged_claims"][1]

        # Msg 489 direct assertion achieves primary weight (0.95, RETRIEVED)
        self.assertEqual(staged_corr["evidence_class"], "RETRIEVED")
        self.assertEqual(staged_corr["confidence"], 0.95)

        # Msg 485 pasted assertion remains secondary (<= 0.60, INFERRED)
        self.assertEqual(staged_old["evidence_class"], "INFERRED")
        self.assertLessEqual(staged_old["confidence"], 0.60)

        # Direct user evidence outranks older pasted assertion
        self.assertGreater(staged_corr["confidence"], staged_old["confidence"])

        # Neither is automatically canonical
        self.assertEqual(staged_old["canonical_effect"], 0)
        self.assertEqual(staged_corr["canonical_effect"], 0)
        self.assertEqual(staged_old["status"], "candidate")
        self.assertEqual(staged_corr["status"], "candidate")


class TestTemporalDurabilitySemantics(unittest.TestCase):
    """Phase 3B.3 Tests: Temporal and Durability Semantics."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_durability.db"
        self.store = LocalStore(self.db_path)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_a_valid_durability_values_persist_and_reload(self) -> None:
        """Test A: Valid durability values ('durable', 'current_state', 'preference', 'transient') persist and reload."""
        raw_evidence = (
            "Evidence snippet durable fact. "
            "Evidence snippet current_state fact. "
            "Evidence snippet preference fact. "
            "Evidence snippet transient fact."
        )
        _seed_test_history_message(
            self.store,
            message_id=101,
            raw_text=raw_evidence,
            role="user",
            speaker="Dustin",
            timestamp="2025-11-27T12:00:00Z",
        )
        durabilities = ["durable", "current_state", "preference", "transient"]
        proposals = []
        for idx, dur in enumerate(durabilities):
            ref = EvidenceReference(
                history_message_id=101,
                relation_type="supports",
                excerpt=f"Evidence snippet {dur} fact.",
                role="user",
                speaker="Dustin",
                source_timestamp="2025-11-27T12:00:00Z",
            )
            prop = CandidateClaimProposal(
                subject_entity_id="person:dustin",
                predicate=f"test_pred_{idx}",
                value_text=f"Value for {dur}",
                durability=dur,
                evidence_references=(ref,),
            )
            proposals.append(prop)

        res = stage_candidate_claims(self.store, proposals)
        self.assertEqual(res["unique_candidate_claims_count"], 4)

        listed = list_candidate_claims(self.store)
        self.assertEqual(len(listed), 4)
        dur_by_pred = {c["predicate"]: c["durability"] for c in listed}

        for idx, dur in enumerate(durabilities):
            pred = f"test_pred_{idx}"
            self.assertEqual(dur_by_pred[pred], dur)
            cid = compute_candidate_claim_id("person:dustin", pred, f"Value for {dur}")
            details = get_candidate_claim_details(self.store, cid)
            self.assertIsNotNone(details)
            self.assertEqual(details["durability"], dur)
            self.assertEqual(details["valid_from"], "2025-11-27T12:00:00Z")

    def test_b_invalid_durability_fails_closed(self) -> None:
        """Test B: Invalid durability values fail closed at proposal and storage levels."""
        ref = EvidenceReference(
            history_message_id=101,
            relation_type="supports",
            excerpt="some evidence",
            source_pointer="test_ptr",
        )
        invalid_values = ["eternal", "permanent", "temporary_state", "invalid", ""]
        for bad_dur in invalid_values:
            with self.assertRaises(ValueError):
                CandidateClaimProposal(
                    subject_entity_id="person:dustin",
                    predicate="test_invalid",
                    value_text="Some value",
                    durability=bad_dur,
                    evidence_references=(ref,),
                )

            with self.assertRaises(ValueError):
                CandidateClaimProposal.from_dict({
                    "subject_entity_id": "person:dustin",
                    "predicate": "test_invalid",
                    "value_text": "Some value",
                    "durability": bad_dur,
                    "evidence_references": [ref.to_dict()],
                })

            valid, err = validate_proposal({
                "subject_entity_id": "person:dustin",
                "predicate": "test_invalid",
                "value_text": "Some value",
                "durability": bad_dur,
                "evidence_references": [ref.to_dict()],
            })
            self.assertFalse(valid)

        # Database CHECK constraint also fails closed
        with self.store._connect() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO memory_claims("
                    "claim_id, subject_entity_id, predicate, value_text, memory_layer, "
                    "status, evidence_class, authority_scope, confidence, confidence_basis, "
                    "created_at, updated_at, canonical_effect, version, durability"
                    ") VALUES ('c:bad_dur', 'person:dustin', 'pred', 'val', 'semantic', "
                    "'candidate', 'RETRIEVED', 'candidate:general', 0.8, 'test', '2026-01-01', '2026-01-01', 0, 1, 'eternal')"
                )

    def test_c_source_timestamp_populates_valid_from(self) -> None:
        """Test C: Source timestamps automatically populate valid_from when omitted."""
        ts = "2025-11-27T19:27:57Z"
        _seed_test_history_message(
            self.store,
            message_id=485,
            raw_text="Btw i am a+ certified with years of experience with commercial servers",
            role="user",
            speaker="Dustin",
            timestamp=ts,
        )
        ref = EvidenceReference(
            history_message_id=485,
            relation_type="supports",
            excerpt="Btw i am a+ certified",
            role="user",
            speaker="Dustin",
            source_timestamp=ts,
        )
        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="certifications",
            value_text="A+ certified",
            durability="durable",
            evidence_references=(ref,),
        )
        self.assertEqual(prop.valid_from, ts)

        res = stage_candidate_claims(self.store, [prop])
        staged = res["staged_claims"][0]
        self.assertEqual(staged["valid_from"], ts)

        details = get_candidate_claim_details(self.store, staged["claim_id"])
        self.assertEqual(details["valid_from"], ts)

    def test_d_durable_a_plus_fixture_classifies_durable(self) -> None:
        """Test D: Professional credential fixture classifies durable."""
        dur = infer_durability(
            subject_entity_id="person:dustin",
            predicate="technical_certifications",
            value_text="Dustin is A+ certified with years of experience with commercial servers",
            claim_category="profile",
        )
        self.assertEqual(dur, "durable")

    def test_e_hardware_inventory_fixture_classifies_current_state(self) -> None:
        """Test E: Hardware inventory fixture classifies current_state."""
        dur = infer_durability(
            subject_entity_id="person:dustin",
            predicate="hardware_inventory",
            value_text="Dustin parts on hand include 2x 24TB Exos HDDs and 2x 4TB NVMe SSDs",
            claim_category="hardware",
        )
        self.assertEqual(dur, "current_state")

    def test_f_rtx_3090_negative_fixture_classifies_current_state(self) -> None:
        """Test F: RTX 3090 negative ownership fixture classifies current_state, NOT durable."""
        dur = infer_durability(
            subject_entity_id="person:dustin",
            predicate="does_not_own_hardware",
            value_text="Dustin does not own an NVIDIA RTX 3090 GPU",
            claim_category="hardware",
        )
        self.assertEqual(dur, "current_state")
        self.assertNotEqual(dur, "durable")

    def test_g_cheapest_hardware_goal_fixture_classifies_preference(self) -> None:
        """Test G: Cheapest-hardware goal fixture classifies preference."""
        dur = infer_durability(
            subject_entity_id="person:dustin",
            predicate="hardware_strategy_goal",
            value_text="Dustin seeks cheapest hardware setup capable of achieving his AI goals",
            claim_category="preference",
        )
        self.assertEqual(dur, "preference")

    def test_h_candidate_claims_cannot_enter_priming_across_all_durabilities(self) -> None:
        """Test H: Candidate claims across all durabilities cannot enter priming."""
        raw_evidence = (
            "Evidence snippet durable fact. "
            "Evidence snippet current_state fact. "
            "Evidence snippet preference fact. "
            "Evidence snippet transient fact."
        )
        _seed_test_history_message(
            self.store,
            message_id=200,
            raw_text=raw_evidence,
            role="user",
            speaker="Dustin",
            timestamp="2025-11-27T10:00:00Z",
        )
        props = []
        for dur in ("durable", "current_state", "preference", "transient"):
            ref = EvidenceReference(
                history_message_id=200,
                relation_type="supports",
                excerpt=f"Evidence snippet {dur} fact.",
                source_timestamp="2025-11-27T10:00:00Z",
            )
            props.append(
                CandidateClaimProposal(
                    subject_entity_id="person:dustin",
                    predicate=f"pred_{dur}",
                    value_text=f"Value for {dur}",
                    claim_category="general",
                    durability=dur,
                    evidence_references=(ref,),
                )
            )
        res = stage_candidate_claims(self.store, props)
        self.assertEqual(res["unique_candidate_claims_count"], 4)

        manifest = PrimingManifest(task_id="test_priming_gate", knowledge_categories=("general", "hardware", "profile", "identity"))
        bundle = assemble_priming_from_knowledge(manifest, store=self.store)
        self.assertEqual(len(bundle.items), 0)

    def test_i_durability_cannot_bypass_human_approval_gate(self) -> None:
        """Test I: Claim marked durable cannot bypass human approval gate."""
        _seed_test_history_message(
            self.store,
            message_id=300,
            raw_text="Durable fact evidence",
            role="user",
            speaker="Dustin",
        )
        ref = EvidenceReference(
            history_message_id=300,
            relation_type="supports",
            excerpt="Durable fact evidence",
            role="user",
            speaker="Dustin",
        )
        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="durable_credential",
            value_text="Dustin is A+ certified",
            durability="durable",
            evidence_references=(ref,),
        )
        res = stage_candidate_claims(self.store, [prop])
        cid = res["staged_claims"][0]["claim_id"]

        # Worker cannot approve
        with self.assertRaises(PermissionError):
            adjudicate_candidate_claim(
                self.store,
                claim_id=cid,
                action="approve",
                reviewer="worker",
                confirmation=APPROVAL_CONFIRMATION,
            )

        # Missing confirmation token fails
        with self.assertRaises(PermissionError):
            adjudicate_candidate_claim(
                self.store,
                claim_id=cid,
                action="approve",
                reviewer="Dustin",
                confirmation=None,
            )

        # Wrong confirmation token fails
        with self.assertRaises(PermissionError):
            adjudicate_candidate_claim(
                self.store,
                claim_id=cid,
                action="approve",
                reviewer="Dustin",
                confirmation="CONFIRM",
            )

        # Valid approval by Dustin succeeds
        adj = adjudicate_candidate_claim(
            self.store,
            claim_id=cid,
            action="approve",
            reviewer="Dustin",
            confirmation=APPROVAL_CONFIRMATION,
        )
        self.assertEqual(adj["resulting_status"], "active")
        self.assertEqual(adj["canonical_effect"], 1)

    def test_j_existing_span_evidence_behavior_unchanged(self) -> None:
        """Test J: Existing span-level attribution behavior remains intact alongside durability."""
        raw_text = (
            "Gpt response \n\n"
            "Btw i am a+ certified with years of experience with commercial servers\n\n"
            "Alright Soph, here’s the real truth...\n"
            "Recommended: RTX 3090"
        )
        attr1, s1, e1 = classify_evidence_span(raw_text=raw_text, excerpt="Btw i am a+ certified", role="user")
        attr2, s2, e2 = classify_evidence_span(raw_text=raw_text, excerpt="Recommended: RTX 3090", role="user")

        self.assertEqual(attr1, "direct_user_assertion")
        self.assertEqual(attr2, "quoted_or_pasted_content")

        ref1 = EvidenceReference(
            history_message_id=400,
            relation_type="supports",
            excerpt="Btw i am a+ certified",
            attribution=attr1,
            span_start=s1,
            span_end=e1,
            source_timestamp="2025-11-27T10:00:00Z",
        )
        prop1 = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="a_plus_certified",
            value_text="Dustin is A+ certified",
            durability="durable",
            evidence_references=(ref1,),
        )
        self.assertEqual(prop1.evidence_references[0].attribution, "direct_user_assertion")
        self.assertEqual(prop1.durability, "durable")

    def test_k_existing_canonical_claims_migrate_and_read(self) -> None:
        """Test K: Existing canonical claims migrate cleanly and load_knowledge_from_store preserves durability."""
        seed_canonical_knowledge(self.store)
        records = load_knowledge_from_store(self.store)
        self.assertGreater(len(records), 0)
        for r in records:
            self.assertIn("durability", r.metadata)
            self.assertEqual(r.metadata["durability"], "durable")

    def test_l_no_automatic_conflict_resolution(self) -> None:
        """Test L: Conflicting claims coexist without autonomous deletion or overwrite."""
        _seed_test_history_message(
            self.store,
            message_id=501,
            raw_text="Earlier: owns RTX 3090",
            role="user",
            speaker="Dustin",
            timestamp="2025-11-27T18:00:00Z",
        )
        _seed_test_history_message(
            self.store,
            message_id=502,
            raw_text="Later: does not own RTX 3090",
            role="user",
            speaker="Dustin",
            timestamp="2025-11-27T19:00:00Z",
        )
        ref1 = EvidenceReference(
            history_message_id=501,
            relation_type="supports",
            excerpt="Earlier: owns RTX 3090",
            source_timestamp="2025-11-27T18:00:00Z",
        )
        ref2 = EvidenceReference(
            history_message_id=502,
            relation_type="supports",
            excerpt="Later: does not own RTX 3090",
            source_timestamp="2025-11-27T19:00:00Z",
        )
        prop_pos = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="rtx_3090_ownership",
            value_text="Dustin owns an RTX 3090",
            durability="current_state",
            evidence_references=(ref1,),
        )
        prop_neg = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="rtx_3090_ownership",
            value_text="Dustin does not own an RTX 3090",
            durability="current_state",
            evidence_references=(ref2,),
        )
        res = stage_candidate_claims(self.store, [prop_pos, prop_neg])
        self.assertEqual(res["unique_candidate_claims_count"], 2)

        # Both exist simultaneously as candidates
        with self.store._connect() as conn:
            rows = conn.execute(
                "SELECT claim_id, value_text, status, canonical_effect FROM memory_claims WHERE predicate = 'rtx_3090_ownership'"
            ).fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual({r["value_text"] for r in rows}, {"Dustin owns an RTX 3090", "Dustin does not own an RTX 3090"})
            for r in rows:
                self.assertEqual(r["status"], "candidate")
                self.assertEqual(r["canonical_effect"], 0)

    def test_m_fixture_authority_guard_durability_does_not_override_attribution(self) -> None:
        """Fixture Authority Guard: Durability classification does NOT manufacture direct Dustin authority.

        If 'Dustin is A+ certified with years of commercial server experience' is extracted
        from inside a quoted/pasted AI block, its attribution remains 'quoted_or_pasted_content'
        and evidence_class remains 'INFERRED' (confidence <= 0.60).
        Durability answers 'How long/type of truth is this?', NOT 'Who said this?'.
        """
        raw_text = (
            "Gpt response \n\n"
            "Here is the plan for your architecture...\n"
            "ChatGPT note: Dustin is A+ certified with years of experience with commercial servers"
        )
        _seed_test_history_message(
            self.store,
            message_id=601,
            raw_text=raw_text,
            role="user",
            speaker="google_account_owner",
            timestamp="2025-11-27T19:30:00Z",
        )
        excerpt = "Dustin is A+ certified with years of experience with commercial servers"
        attr, s_start, s_end = classify_evidence_span(
            raw_text=raw_text,
            excerpt=excerpt,
            role="user",
            speaker="google_account_owner",
        )
        # Sourced within ChatGPT block -> MUST be quoted_or_pasted_content, NOT direct_user_assertion
        self.assertEqual(attr, "quoted_or_pasted_content")

        ref = EvidenceReference(
            history_message_id=601,
            relation_type="supports",
            excerpt=excerpt,
            role="user",
            speaker="google_account_owner",
            attribution=attr,
            span_start=s_start,
            span_end=s_end,
            source_timestamp="2025-11-27T19:30:00Z",
        )
        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="has_credential",
            value_text="Dustin is A+ certified with years of experience with commercial servers",
            claim_category="profile",
            durability="durable",
            evidence_references=(ref,),
        )
        # Durability is durable
        self.assertEqual(prop.durability, "durable")

        res = stage_candidate_claims(self.store, [prop])
        staged = res["staged_claims"][0]

        # Authority guard: evidence_class must NOT be elevated to RETRIEVED or direct user authority
        self.assertEqual(staged["evidence_class"], "INFERRED")
        self.assertLessEqual(staged["confidence"], 0.60)
        self.assertEqual(staged["evidence_references"][0]["attribution"], "quoted_or_pasted_content")
        self.assertEqual(staged["canonical_effect"], 0)

    def test_n_category_closure_regression_suite(self) -> None:
        """Memory Retrieval Category Closure Regression Suite (Points 1 through 9)."""
        ts = "2025-11-27T19:27:57Z"
        _seed_test_history_message(
            self.store,
            message_id=701,
            raw_text="Btw i am a+ certified with years of experience with commercial servers",
            role="user",
            speaker="Dustin",
            timestamp=ts,
        )
        ref = EvidenceReference(
            history_message_id=701,
            relation_type="supports",
            excerpt="Btw i am a+ certified with years of experience with commercial servers",
            role="user",
            speaker="Dustin",
            attribution="direct_user_assertion",
            span_start=0,
            span_end=70,
            source_timestamp=ts,
        )

        # 1. Professional credential claim maps to profile/background semantics
        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="has_durable_credential",
            value_text="A+ certified with years of experience with commercial servers",
            claim_category="decision",  # deliberately pass 'decision' to test inference normalization
            durability="durable",
            evidence_references=(ref,),
        )
        self.assertEqual(prop.claim_category, "profile")
        self.assertEqual(prop.memory_layer, "identity")
        self.assertEqual(
            infer_claim_category(
                predicate="has_durable_credential",
                value_text="A+ certified with years of experience with commercial servers",
                subject_entity_id="person:dustin",
                proposed_category="decision",
            ),
            "profile",
        )

        # 7. Evidence attribution remains unchanged
        self.assertEqual(prop.evidence_references[0].attribution, "direct_user_assertion")

        # 8. Durability remains unchanged
        self.assertEqual(prop.durability, "durable")

        stage_res = stage_candidate_claims(self.store, [prop])
        cid = stage_res["staged_claims"][0]["claim_id"]

        with self.store._connect() as conn:
            c_row = conn.execute("SELECT * FROM memory_claims WHERE claim_id = ?", (cid,)).fetchone()
            self.assertEqual(c_row["claim_category"], "profile")
            self.assertEqual(c_row["authority_scope"], "candidate")
            self.assertEqual(c_row["status"], "candidate")
            self.assertEqual(c_row["canonical_effect"], 0)
            self.assertEqual(c_row["durability"], "durable")

        # 2. Canonical promotion preserves semantic category
        # 3. Authority scope does not silently replace semantic category
        adj_res = adjudicate_candidate_claim(
            self.store,
            claim_id=cid,
            action="approve",
            reviewer="Dustin",
            confirmation=APPROVAL_CONFIRMATION,
            reason="Approved A+ certification credential claim",
        )
        self.assertEqual(adj_res["status"], "approved")

        with self.store._connect() as conn:
            promoted_row = conn.execute("SELECT * FROM memory_claims WHERE claim_id = ?", (cid,)).fetchone()
            self.assertEqual(promoted_row["status"], "active")
            self.assertEqual(promoted_row["canonical_effect"], 1)
            # Authority scope is governing authority ('canonical')
            self.assertEqual(promoted_row["authority_scope"], "canonical")
            # Semantic retrieval category is preserved ('profile')
            self.assertEqual(promoted_row["claim_category"], "profile")
            # Durability is preserved ('durable')
            self.assertEqual(promoted_row["durability"], "durable")

            # Check canonical_adjudications record
            adj_row = conn.execute("SELECT * FROM canonical_adjudications WHERE source_pointer = ?", (f"claim:{cid}",)).fetchone()
            self.assertEqual(adj_row["authority_scope"], "canonical")

            # Check evidence attribution preserved in claim_evidence
            ev_row = conn.execute("SELECT * FROM claim_evidence WHERE claim_id = ?", (cid,)).fetchone()
            self.assertEqual(ev_row["attribution"], "direct_user_assertion")

        # 4. Profile query retrieves approved credential
        manifest_profile = PrimingManifest(task_id="test-profile", knowledge_categories=("profile",))
        bundle_profile = assemble_priming_from_knowledge(manifest_profile, store=self.store)
        profile_cids = [item.item_id for item in bundle_profile.items]
        self.assertIn(cid, profile_cids)

        # 5. Decision-only query does not incorrectly retrieve it
        manifest_decision = PrimingManifest(task_id="test-decision", knowledge_categories=("decision",))
        bundle_decision = assemble_priming_from_knowledge(manifest_decision, store=self.store)
        decision_cids = [item.item_id for item in bundle_decision.items]
        self.assertNotIn(cid, decision_cids)

        # 6. Candidate claims remain excluded
        _seed_test_history_message(self.store, 702, raw_text="Pending candidate claim message")
        ref_cand = EvidenceReference(
            history_message_id=702,
            relation_type="supports",
            excerpt="Pending candidate",
            role="user",
            speaker="Dustin",
            attribution="direct_user_assertion",
        )
        prop_cand = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="has_unapproved_skill",
            value_text="Pending candidate profile fact",
            claim_category="profile",
            evidence_references=(ref_cand,),
        )
        stage_res_cand = stage_candidate_claims(self.store, [prop_cand])
        cand_id = stage_res_cand["staged_claims"][0]["claim_id"]

        # Run profile query again
        bundle_profile_after = assemble_priming_from_knowledge(manifest_profile, store=self.store)
        profile_after_cids = [item.item_id for item in bundle_profile_after.items]
        self.assertIn(cid, profile_after_cids)
        self.assertNotIn(cand_id, profile_after_cids)

        # 9. Existing canonical claims remain backward-compatible
        seed_res = seed_canonical_knowledge(self.store)
        records = load_knowledge_from_store(self.store)
        rec_map = {r.record_id: r for r in records}
        self.assertIn("identity:dustin-authority", rec_map)
        self.assertEqual(rec_map["identity:dustin-authority"].category, "identity")
        self.assertIn("arch:supervisor-worker-separation", rec_map)
        self.assertEqual(rec_map["arch:supervisor-worker-separation"].category, "architecture")

        # Priming query for bootstrap categories retrieves all of them
        manifest_boot = PrimingManifest(task_id="test-boot", knowledge_categories=("architecture", "procedure", "identity"))
        bundle_boot = assemble_priming_from_knowledge(manifest_boot, store=self.store)
        boot_cids = {item.item_id for item in bundle_boot.items}
        self.assertTrue({"identity:dustin-authority", "arch:supervisor-worker-separation", "arch:identity-above-models", "procedure:destructive-action-gate"}.issubset(boot_cids))

        # Legacy backward-compatibility: simulate legacy row where claim_category is NULL and authority_scope is 'canonical_versioned:architecture'
        with self.store._connect() as conn:
            conn.execute(
                "INSERT INTO memory_claims("
                "claim_id, subject_entity_id, predicate, value_text, memory_layer, "
                "status, evidence_class, authority_scope, confidence, confidence_basis, "
                "created_at, updated_at, approved_by, reviewed_at, canonical_effect, "
                "version, durability, claim_category"
                ") VALUES ('legacy:arch-rule', 'system:josie', 'arch_rule', 'Legacy rule', 'procedural', "
                "'active', 'CANONICAL', 'canonical_versioned:architecture', 1.0, 'legacy test', "
                "'2026-01-01', '2026-01-01', 'Dustin', '2026-01-01', 1, 1, 'durable', NULL)"
            )
        legacy_records = load_knowledge_from_store(self.store)
        legacy_rec = next(r for r in legacy_records if r.record_id == "legacy:arch-rule")
        self.assertEqual(legacy_rec.category, "architecture")


class Batch001PolicyHardeningTests(unittest.TestCase):
    """Regression tests for the 5 candidate-memory policy hardening rules exposed by Batch 001."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp(prefix="josie_batch001_tests_")
        self.db_path = Path(self.tmpdir) / "test.db"
        self.store = LocalStore(self.db_path)
        with self.store._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO entities(entity_id, canonical_name, normalized_name, entity_type, created_at, updated_at) VALUES ('person:dustin', 'Dustin', 'dustin', 'person', '2026-01-01', '2026-01-01')")
            conn.execute("INSERT OR IGNORE INTO entities(entity_id, canonical_name, normalized_name, entity_type, created_at, updated_at) VALUES ('system:josie', 'Josie', 'josie', 'system', '2026-01-01', '2026-01-01')")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_rule_1_unentailed_entity_greensky_fails_closed(self) -> None:
        """Rule 1: Prohibits inventing named accounts (GreenSky) absent from evidence text."""
        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="reduced_green_sky_payment_to_minimum",
            value_text="from $350 to minimum",
            memory_layer="semantic",
            claim_category="general",
            confidence=0.9,
            confidence_basis="Direct user statement in historical conversation",
            durability="current_state",
            evidence_references=(
                EvidenceReference(
                    history_message_id=1,
                    relation_type="supports",
                    excerpt="Also i dumped this down from 350 to minimum",
                    role="user",
                    speaker="Dustin",
                ),
            ),
        )
        lookup = {1: {"raw_text": "Also i dumped this down from 350 to minimum", "role": "user", "speaker": "Dustin"}}
        valid, err = check_claim_evidence_entailment(prop, lookup)
        self.assertFalse(valid)
        self.assertIn("green sky", err.lower().replace("_", " "))

        valid_prop, prop_err = validate_proposal(prop, messages_lookup=lookup)
        self.assertFalse(valid_prop)
        self.assertIn("green sky", prop_err.lower().replace("_", " "))

    def test_rule_1_unentailed_entity_401k_fails_closed(self) -> None:
        """Rule 1: Prohibits inventing unentailed financial products (401(k)) absent from evidence."""
        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="considers_repaying_401k_loan",
            value_text="to reach $170,000 mortgage payoff",
            memory_layer="semantic",
            claim_category="general",
            confidence=0.85,
            confidence_basis="Direct user statement in historical conversation",
            durability="current_state",
            evidence_references=(
                EvidenceReference(
                    history_message_id=2,
                    relation_type="supports",
                    excerpt="If I repay the $41,000 that I still have outstanding, that'd put me right around that exact number.",
                    role="user",
                    speaker="Dustin",
                ),
            ),
        )
        lookup = {2: {"raw_text": "I think we're at like $170,000. If I repay the $41,000 that I still have outstanding, that'd put me right around that exact number.", "role": "user", "speaker": "Dustin"}}
        valid, err = check_claim_evidence_entailment(prop, lookup)
        self.assertFalse(valid)
        self.assertIn("401k", err.lower())

    def test_rule_2_transaction_level_choice_rejected_as_preference(self) -> None:
        """Rule 2: Transaction-specific negotiations cannot be classified as durability='preference'."""
        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="prefers",
            value_text="paying $250 with buyer protection for GPU purchase",
            memory_layer="relational",
            claim_category="preference",
            confidence=0.9,
            confidence_basis="Direct user statement",
            durability="preference",
            evidence_references=(
                EvidenceReference(
                    history_message_id=3,
                    relation_type="supports",
                    excerpt="Or just pay 250 and be done..... buyer protection is nice, fb does it on shipped items.",
                    role="user",
                    speaker="Dustin",
                ),
            ),
        )
        lookup = {3: {"raw_text": "Or just pay 250 and be done..... buyer protection is nice, fb does it on shipped items.", "role": "user", "speaker": "Dustin"}}
        valid, err = check_event_vs_preference("prefers", "paying $250 with buyer protection for GPU purchase", "preference")
        self.assertFalse(valid)
        self.assertIn("Single-transaction purchase", err)

        valid_prop, prop_err = validate_proposal(prop, messages_lookup=lookup)
        self.assertFalse(valid_prop)
        self.assertIn("Single-transaction purchase", prop_err)

    def test_rule_3_truth_not_memory_worthiness_canonical_eligibility(self) -> None:
        """Rule 3: Transient rewards balances and consumer subscription rosters fail closed for canonical memory."""
        # 1. Rewards balance
        claim_rewards = {"durability": "transient", "predicate": "budget_rewards_balance", "value_text": "allocated $80 from Upside and $50 Amazon from Zen"}
        eligible, reason = is_canonical_eligible(claim_rewards)
        self.assertFalse(eligible)
        self.assertIn("Transient claims", reason)

        # 2. Subscriptions roster
        claim_subs = {"durability": "current_state", "predicate": "retained_subscriptions", "value_text": "cancelled everything except Hulu, Netflix, Disney"}
        eligible, reason = is_canonical_eligible(claim_subs)
        self.assertFalse(eligible)
        self.assertIn("subscription", reason.lower())

        # 3. Deliberative consideration
        claim_musing = {"durability": "current_state", "predicate": "considers_repaying_loan", "value_text": "if I repay $41,000"}
        eligible, reason = is_canonical_eligible(claim_musing)
        self.assertFalse(eligible)
        self.assertIn("Deliberative considerations", reason)

        # 4. Valid durable preference passes
        claim_valid = {"durability": "preference", "subject_entity_id": "person:dustin", "predicate": "seeks_profit_work_tier", "value_text": "Dustin prefers profit and work models with minimal regular personal involvement."}
        eligible, reason = is_canonical_eligible(claim_valid)
        self.assertTrue(eligible)
        self.assertEqual(reason, "")

    def test_rule_4_corroboration_transfers_evidence_without_duplicate_canonical(self) -> None:
        """Rule 4: Corroboration merges evidence into existing target without duplicate canonical claim."""
        # Create target claim
        target_id = "claim:candidate:person:dustin:prefers_model_access:target01"
        _seed_test_history_message(self.store, 101, raw_text="Maintain subscription limits")
        _seed_test_history_message(self.store, 102, raw_text="Give Josie as much access as possible without burning limits")
        with self.store._connect() as conn:
            conn.execute(
                "INSERT INTO memory_claims("
                "claim_id, subject_entity_id, predicate, value_text, memory_layer, "
                "status, evidence_class, authority_scope, confidence, confidence_basis, "
                "created_at, updated_at, canonical_effect, durability, claim_category"
                ") VALUES (?, 'person:dustin', 'prefers_model_access', 'Maintain subscription limits', 'relational', "
                "'candidate', 'RETRIEVED', 'relational:preference', 0.85, 'Direct user', '2026-08-01', '2026-08-01', 0, 'preference', 'preference')",
                (target_id,),
            )
            conn.execute(
                "INSERT INTO claim_evidence(claim_id, evidence_id, relation_type, source_type, history_message_id, source_pointer, evidence_class, created_at) "
                "VALUES (?, 'ev:101', 'supports', 'history_message', 101, 'msg:101', 'RETRIEVED', '2026-08-01')",
                (target_id,),
            )

        # Stage candidate claim
        cand_prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="prefers_maximizing_access_without_burning_limits",
            value_text="want to give Josie access without burning limits",
            memory_layer="relational",
            claim_category="preference",
            confidence=0.95,
            confidence_basis="Direct user statement",
            durability="preference",
            evidence_references=(
                EvidenceReference(
                    history_message_id=102,
                    relation_type="supports",
                    excerpt="Give Josie as much access as possible without burning limits",
                    role="user",
                    speaker="Dustin",
                    attribution="direct_user_assertion",
                ),
            ),
        )
        stage_res = stage_candidate_claims(self.store, [cand_prop])
        cand_id = stage_res["staged_claims"][0]["claim_id"]

        # Corroborate candidate into target
        res = adjudicate_candidate_claim(
            self.store,
            claim_id=cand_id,
            action="corroborate",
            reviewer="Dustin",
            target_claim_id=target_id,
            reason="Corroborated ChatGPT evidence into existing preference",
        )
        self.assertEqual(res["status"], "corroborated")
        self.assertEqual(res["canonical_effect"], 0)
        self.assertEqual(res["evidence_transferred"], 1)

        # Verify DB state
        with self.store._connect() as conn:
            cand_row = conn.execute("SELECT status, canonical_effect, superseded_by_claim_id FROM memory_claims WHERE claim_id = ?", (cand_id,)).fetchone()
            self.assertEqual(cand_row["status"], "superseded")
            self.assertEqual(cand_row["canonical_effect"], 0)
            self.assertEqual(cand_row["superseded_by_claim_id"], target_id)

            target_row = conn.execute("SELECT status, canonical_effect FROM memory_claims WHERE claim_id = ?", (target_id,)).fetchone()
            self.assertEqual(target_row["status"], "candidate")
            self.assertEqual(target_row["canonical_effect"], 0)

            ev_rows = conn.execute("SELECT history_message_id FROM claim_evidence WHERE claim_id = ? ORDER BY history_message_id ASC", (target_id,)).fetchall()
            self.assertEqual(len(ev_rows), 2)
            self.assertEqual([r[0] for r in ev_rows], [101, 102])

    def test_rule_5_conservative_relationship_mapping_run_vs_own(self) -> None:
        """Rule 5: 'run a vape shop' does not justify claiming 'jointly own a vape shop'."""
        lookup = {201: {"raw_text": "how Jess and I run our vape shop and how we have taken in a lot of strays.", "role": "user", "speaker": "Dustin"}}
        
        # Ownership proposal fails closed
        prop_own = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="operates_business",
            value_text="Dustin and Jess jointly own a vape shop business",
            memory_layer="semantic",
            claim_category="profile",
            confidence=0.9,
            confidence_basis="Direct user statement",
            durability="current_state",
            evidence_references=(
                EvidenceReference(history_message_id=201, relation_type="supports", excerpt="how Jess and I run our vape shop", role="user", speaker="Dustin"),
            ),
        )
        valid, err = check_claim_evidence_entailment(prop_own, lookup)
        self.assertFalse(valid)
        self.assertIn("ownership without explicit ownership evidence", err)

        # Operational proposal succeeds
        prop_run = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="operates_business",
            value_text="Dustin and Jess run a vape shop together",
            memory_layer="semantic",
            claim_category="profile",
            confidence=0.9,
            confidence_basis="Direct user statement",
            durability="current_state",
            evidence_references=(
                EvidenceReference(history_message_id=201, relation_type="supports", excerpt="how Jess and I run our vape shop", role="user", speaker="Dustin"),
            ),
        )
        valid, err = check_claim_evidence_entailment(prop_run, lookup)
        self.assertTrue(valid)
        self.assertEqual(err, "")

    def test_human_approval_with_edits_and_temporal_bounds(self) -> None:
        """Test explicit human approval supports value editing, durability change, and temporal bounding."""
        _seed_test_history_message(self.store, 301, raw_text="Kevin Slack is assisting me")

        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="ministry_co_leader",
            value_text="co-leads Everyday Discipleship with Kevin Slack",
            memory_layer="relational",
            claim_category="relationship_context",
            confidence=0.9,
            confidence_basis="Direct user statement",
            durability="current_state",
            evidence_references=(
                EvidenceReference(history_message_id=301, relation_type="supports", excerpt="Kevin Slack is assisting me", role="user", speaker="Dustin"),
            ),
        )
        stage_res = stage_candidate_claims(self.store, [prop])
        cid = stage_res["staged_claims"][0]["claim_id"]

        # Approve with edits and temporal bounds
        adj = adjudicate_candidate_claim(
            self.store,
            claim_id=cid,
            action="approve",
            reviewer="Dustin",
            confirmation=APPROVAL_CONFIRMATION,
            edited_value_text="In August 2026, Kevin Slack was assisting/co-leading Dustin's Everyday Discipleship study.",
            durability="current_state",
            valid_from="2026-08-17",
            valid_to="2026-08-31",
            reason="Approved with temporal bounds",
        )
        self.assertEqual(adj["status"], "approved")
        self.assertEqual(adj["canonical_effect"], 1)
        self.assertEqual(adj["value_text"], "In August 2026, Kevin Slack was assisting/co-leading Dustin's Everyday Discipleship study.")
        self.assertEqual(adj["valid_from"], "2026-08-17")
        self.assertEqual(adj["valid_to"], "2026-08-31")

        with self.store._connect() as conn:
            row = conn.execute("SELECT value_text, durability, valid_from, valid_to, status, canonical_effect FROM memory_claims WHERE claim_id = ?", (cid,)).fetchone()
            self.assertEqual(row["value_text"], "In August 2026, Kevin Slack was assisting/co-leading Dustin's Everyday Discipleship study.")
            self.assertEqual(row["durability"], "current_state")
            self.assertEqual(row["valid_from"], "2026-08-17")
            self.assertEqual(row["valid_to"], "2026-08-31")
            self.assertEqual(row["status"], "active")
            self.assertEqual(row["canonical_effect"], 1)

    def test_canonical_eligibility_enforced_on_approve(self) -> None:
        """Test that adjudicate_candidate_claim rejects ineligible claims on approve unless force=True."""
        _seed_test_history_message(self.store, 401, raw_text="I have $80 from Upside and $50 from Zen")

        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="budget_rewards_balance",
            value_text="allocated $80 from Upside and $50 Amazon from Zen rewards",
            memory_layer="semantic",
            claim_category="hardware",
            confidence=0.9,
            confidence_basis="Direct user statement",
            durability="transient",
            evidence_references=(
                EvidenceReference(history_message_id=401, relation_type="supports", excerpt="I have $80 from Upside and $50 from Zen", role="user", speaker="Dustin"),
            ),
        )
        stage_res = stage_candidate_claims(self.store, [prop])
        cid = stage_res["staged_claims"][0]["claim_id"]

        with self.assertRaises(ValueError) as ctx:
            adjudicate_candidate_claim(
                self.store,
                claim_id=cid,
                action="approve",
                reviewer="Dustin",
                confirmation=APPROVAL_CONFIRMATION,
            )
        self.assertIn("ineligible for canonical promotion", str(ctx.exception))

        # With force=True, can override if human explicitly mandates
        res_forced = adjudicate_candidate_claim(
            self.store,
            claim_id=cid,
            action="approve",
            reviewer="Dustin",
            confirmation=APPROVAL_CONFIRMATION,
            force=True,
            reason="Human explicit override",
        )
        self.assertEqual(res_forced["status"], "approved")
        self.assertEqual(res_forced["canonical_effect"], 1)



class HypotheticalFictionalGuardTests(unittest.TestCase):
    """Regression tests for the Epistemic Guard (hypothetical/fictional/roleplay) and Destination Routing."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_epistemic.db"
        self.store = LocalStore(self.db_path)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_fictional_backstory_dual_xeons_rejected(self) -> None:
        """Batch 002 Msg 20975 regression: Fictional backstory describing dual Xeons must NOT establish hardware ownership."""
        raw_msg = (
            "Josie's personality and backstory. She's an autonomous AI born in a lab. "
            "Eventually, Josie has a full-blown rack server with dual Xeons, two RTX 3090s, 256GB RAM."
        )
        _seed_test_history_message(self.store, 20975, raw_text=raw_msg, role="user", speaker="Dustin")

        # Test classify_epistemic_mode classifies backstory framing
        mode, _ = classify_epistemic_mode("Josie's personality and backstory. She's an autonomous AI born in a lab.")
        self.assertEqual(mode, "fictional_backstory")

        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="owns_hardware",
            value_text="owns a rack server with dual Xeons, two RTX 3090s, 256GB RAM",
            claim_category="hardware",
            durability="current_state",
            evidence_references=(
                EvidenceReference(
                    history_message_id=20975,
                    relation_type="supports",
                    excerpt="Eventually, Josie has a full-blown rack server with dual Xeons, two RTX 3090s, 256GB RAM.",
                    role="user",
                    speaker="Dustin",
                ),
            ),
        )

        # 1. Epistemic check directly fails closed
        valid, reason = check_hypothetical_or_fictional(prop, {20975: {"raw_text": raw_msg, "role": "user"}})
        self.assertFalse(valid)
        self.assertIn("fails hypothetical/fictional guard", reason.lower())

        # 2. validate_proposal fails
        v_ok, v_reason = validate_proposal(prop, store=self.store)
        self.assertFalse(v_ok)
        self.assertIn("fictional", v_reason.lower())

        # 3. Canonical eligibility fails closed
        c_ok, c_reason = is_canonical_eligible(prop)
        self.assertFalse(c_ok)
        self.assertIn("fictional", c_reason.lower())

    def test_proposed_future_hardware_cannot_be_current_hardware(self) -> None:
        """Proposed future hardware plans must not be extracted or staged as current hardware ownership."""
        raw_msg = "In the future, I plan to get two RTX 4090s for local training."
        _seed_test_history_message(self.store, 501, raw_text=raw_msg, role="user", speaker="Dustin")

        mode, _ = classify_epistemic_mode(raw_msg)
        self.assertEqual(mode, "plan_intention")

        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="owns_hardware",
            value_text="owns two RTX 4090s",
            claim_category="hardware",
            durability="current_state",
            evidence_references=(
                EvidenceReference(
                    history_message_id=501,
                    relation_type="supports",
                    excerpt="In the future, I plan to get two RTX 4090s for local training.",
                    role="user",
                    speaker="Dustin",
                ),
            ),
        )

        valid, reason = check_hypothetical_or_fictional(prop, {501: {"raw_text": raw_msg, "role": "user"}})
        self.assertFalse(valid)
        self.assertIn("future hardware", reason.lower())

        v_ok, v_reason = validate_proposal(prop, store=self.store)
        self.assertFalse(v_ok)
        self.assertIn("future hardware", v_reason.lower())

    def test_hypothetical_scenarios_remain_non_canonical(self) -> None:
        """Hypothetical scenarios fail closed for factual memory extraction."""
        raw_msg = "What if we hypothetically had 10 RTX 4090s running in parallel?"
        _seed_test_history_message(self.store, 502, raw_text=raw_msg, role="user", speaker="Dustin")

        mode, _ = classify_epistemic_mode(raw_msg)
        self.assertEqual(mode, "hypothetical")

        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="hardware_gpu",
            value_text="has 10 RTX 4090s running in parallel",
            claim_category="hardware",
            durability="current_state",
            evidence_references=(
                EvidenceReference(
                    history_message_id=502,
                    relation_type="supports",
                    excerpt="What if we hypothetically had 10 RTX 4090s running in parallel?",
                    role="user",
                    speaker="Dustin",
                ),
            ),
        )

        valid, reason = check_hypothetical_or_fictional(prop, {502: {"raw_text": raw_msg, "role": "user"}})
        self.assertFalse(valid)
        self.assertIn("hypothetical", reason.lower())

        c_ok, c_reason = is_canonical_eligible(prop)
        self.assertFalse(c_ok)
        self.assertIn("hypothetical", c_reason.lower())

    def test_factual_statement_adjacent_to_fictional_text_extractable(self) -> None:
        """Factual assertions in a message containing fictional text remain extractable and valid."""
        raw_msg = (
            "In my sci-fi story, the AI lives in a crystal matrix. "
            "In real life, I am CompTIA A+ certified and have two 4TB NVMe drives on my desk."
        )
        _seed_test_history_message(self.store, 503, raw_text=raw_msg, role="user", speaker="Dustin")

        # Factual certification proposal
        prop_cert = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="certification",
            value_text="CompTIA A+ certified",
            claim_category="profile",
            durability="durable",
            evidence_references=(
                EvidenceReference(
                    history_message_id=503,
                    relation_type="supports",
                    excerpt="In real life, I am CompTIA A+ certified",
                    role="user",
                    speaker="Dustin",
                ),
            ),
        )

        valid_cert, reason_cert = check_hypothetical_or_fictional(prop_cert, {503: {"raw_text": raw_msg, "role": "user"}})
        self.assertTrue(valid_cert)
        self.assertEqual(reason_cert, "")

        mode_cert, _ = classify_epistemic_mode("In real life, I am CompTIA A+ certified", context_text=raw_msg)
        self.assertIn(mode_cert, ("factual_assertion", "current_factual_assertion"))

        v_ok_cert, _ = validate_proposal(prop_cert, store=self.store)
        self.assertTrue(v_ok_cert)

        # Factual hardware proposal
        prop_hw = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="owns_hardware",
            value_text="has two 4TB NVMe drives on desk",
            claim_category="hardware",
            durability="current_state",
            evidence_references=(
                EvidenceReference(
                    history_message_id=503,
                    relation_type="supports",
                    excerpt="have two 4TB NVMe drives on my desk",
                    role="user",
                    speaker="Dustin",
                ),
            ),
        )

        valid_hw, reason_hw = check_hypothetical_or_fictional(prop_hw, {503: {"raw_text": raw_msg, "role": "user"}})
        self.assertTrue(valid_hw)
        self.assertEqual(reason_hw, "")

        mode_hw, _ = classify_epistemic_mode("have two 4TB NVMe drives on my desk", context_text=raw_msg)
        self.assertIn(mode_hw, ("factual_assertion", "current_factual_assertion"))

        v_ok_hw, _ = validate_proposal(prop_hw, store=self.store)
        self.assertTrue(v_ok_hw)

    def test_operational_facts_route_away_from_personal_identity(self) -> None:
        """Operational machine facts (BIOS settings, procedures) route away from personal identity."""
        prop_bios = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="bios_setting",
            value_text="Advantech AIMB-785 BIOS set to UEFI boot with Above 4G Decoding enabled",
            claim_category="hardware",
            durability="current_state",
            evidence_references=(
                EvidenceReference(
                    history_message_id=504,
                    relation_type="supports",
                    excerpt="set the Advantech AIMB-785 BIOS to UEFI boot with Above 4G Decoding enabled",
                    role="user",
                    speaker="Dustin",
                ),
            ),
        )
        dest_bios, _ = classify_memory_destination(prop_bios)
        self.assertEqual(dest_bios, "hardware_state")
        self.assertNotEqual(dest_bios, "personal_canonical")

        prop_proc = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="os_sysprep_procedure",
            value_text="Run sysprep before capturing the Windows 11 image",
            claim_category="procedure",
            durability="durable",
            evidence_references=(
                EvidenceReference(
                    history_message_id=505,
                    relation_type="supports",
                    excerpt="Run sysprep before capturing the Windows 11 image",
                    role="user",
                    speaker="Dustin",
                ),
            ),
        )
        dest_proc, _ = classify_memory_destination(prop_proc)
        self.assertEqual(dest_proc, "runbook_procedure")
        self.assertNotEqual(dest_proc, "personal_canonical")



class SensitiveReviewQuarantineTests(unittest.TestCase):
    """Regression tests for the Sensitive Personal Claim Quarantine destination."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_sensitive.db"
        self.store = LocalStore(self.db_path)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_batch_003_inherently_dangerous_quarantined(self) -> None:
        """Batch 003 regression: 'identifies_as_inherently_dangerous_to_self_and_others' must route to sensitive_review."""
        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="identifies_as_inherently_dangerous_to_self_and_others",
            value_text="dangerous to me. I am dangerous to those around me. I have proven it. Consistently proven it. I am aware of it",
            claim_category="identity",
            durability="durable",
            evidence_references=(
                EvidenceReference(
                    history_message_id=19427,
                    relation_type="supports",
                    excerpt="Bro, I am fucking inherently dangerous. I am dangerous to me. I am dangerous to those around me. I have proven it. Consistently proven it. I am aware of it.",
                    role="user",
                    speaker="Dustin",
                ),
            ),
        )

        dest, reason = classify_memory_destination(prop)
        self.assertEqual(dest, "sensitive_review")
        self.assertIn("sensitive", reason.lower())

        is_elig, elig_reason = is_canonical_eligible(prop)
        self.assertFalse(is_elig)
        self.assertIn("sensitive", elig_reason.lower())

    def test_substance_addiction_mental_health_quarantined(self) -> None:
        """Substance use, mental health diagnoses, and trauma route to sensitive_review."""
        test_cases = [
            ("mental_health_status", "diagnosed with severe clinical depression and anxiety disorder"),
            ("substance_status", "struggling with alcohol addiction and attending rehab meetings"),
            ("trauma_history", "survived severe domestic abuse and trauma"),
            ("legal_history", "arrested and convicted of misdemeanor charges"),
            ("financial_distress", "filed for Chapter 7 bankruptcy due to severe debt"),
        ]

        for pred, val in test_cases:
            prop = CandidateClaimProposal(
                subject_entity_id="person:dustin",
                predicate=pred,
                value_text=val,
                claim_category="profile",
                durability="durable",
                evidence_references=(),
            )
            dest, _ = classify_memory_destination(prop)
            self.assertEqual(dest, "sensitive_review", f"Failed to quarantine sensitive claim: {pred}={val}")
            is_elig, _ = is_canonical_eligible(prop)
            self.assertFalse(is_elig, f"Sensitive claim was considered canonical eligible: {pred}={val}")

    def test_sensitive_claims_staged_with_quarantine_notes(self) -> None:
        """Sensitive claims staged in the DB retain full provenance, status='candidate', and quarantine notes."""
        _seed_test_history_message(self.store, 777, raw_text="I am dangerous to me and those around me.", role="user", speaker="Dustin")

        prop = CandidateClaimProposal(
            subject_entity_id="person:dustin",
            predicate="identifies_as_inherently_dangerous_to_self_and_others",
            value_text="dangerous to me and those around me",
            claim_category="identity",
            durability="durable",
            evidence_references=(
                EvidenceReference(
                    history_message_id=777,
                    relation_type="supports",
                    excerpt="I am dangerous to me and those around me.",
                    role="user",
                    speaker="Dustin",
                ),
            ),
        )

        stage_res = stage_candidate_claims(self.store, [prop])
        self.assertEqual(stage_res["unique_candidate_claims_count"], 1)
        staged_rec = stage_res["staged_claims"][0]
        self.assertEqual(staged_rec["memory_destination"], "sensitive_review")
        self.assertIn("[QUARANTINE: sensitive_review]", staged_rec["notes"])

        with self.store._connect() as conn:
            row = conn.execute("SELECT * FROM memory_claims WHERE claim_id = ?", (staged_rec["claim_id"],)).fetchone()
            self.assertEqual(row["status"], "candidate")
            self.assertEqual(row["canonical_effect"], 0)
            self.assertIsNone(row["approved_by"])
            self.assertIsNone(row["reviewed_at"])

    def test_ordinary_claims_not_quarantined(self) -> None:
        """Ordinary facts, business operations, and tech configs do NOT trigger sensitive quarantine."""
        safe_cases = [
            ("owns_hardware", "has two 4TB NVMe drives on desk", "hardware_state"),
            ("operates_business", "Dustin and Jess run a vape shop together", "personal_canonical"),
            ("has_monthly_mortgage", "household mortgage payment was approximately $1,500/month", "personal_canonical"),
            ("prefers", "remotely controlled browser sessions without exposing credentials", "personal_canonical"),
            ("bios_setting", "Advantech AIMB-785 BIOS set to UEFI boot", "hardware_state"),
        ]

        for pred, val, expected_dest in safe_cases:
            prop = CandidateClaimProposal(
                subject_entity_id="person:dustin",
                predicate=pred,
                value_text=val,
                claim_category="hardware" if "hardware" in expected_dest else "profile",
                durability="current_state" if ("mortgage" in pred or "hardware" in expected_dest) else "durable",
                evidence_references=(),
            )
            dest, _ = classify_memory_destination(prop)
            self.assertNotEqual(dest, "sensitive_review", f"False positive sensitive quarantine on {pred}: {val}")
            self.assertEqual(dest, expected_dest)


if __name__ == "__main__":
    unittest.main()


