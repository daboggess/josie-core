from __future__ import annotations

import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from josie.knowledge import (
    BOOTSTRAP_KNOWLEDGE_SEEDS,
    CANONICAL_KNOWLEDGE_RECORDS,
    KNOWLEDGE_SCHEMA_VERSION,
    KnowledgeQuery,
    KnowledgeRecord,
    assemble_priming_from_knowledge,
    load_knowledge_from_store,
    query_knowledge,
    query_knowledge_for_priming,
    seed_canonical_knowledge,
    sort_knowledge_records,
)
from josie.storage import LocalStore
from supervisor.priming import (
    PrimingItem,
    PrimingManifest,
    apply_priming_to_work_order,
    assemble_priming_bundle,
)
from supervisor.prompt_compiler import compile_prompt
from supervisor.prompt_contract import validate_contract_prompt
from supervisor.work_order import WorkOrder


class KnowledgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp(prefix="josie_knowledge_test_")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_real_structured_knowledge_query_deterministic(self) -> None:
        """Requirement 1: Real structured knowledge query returns deterministic results."""
        query = KnowledgeQuery(categories=("identity", "architecture"))
        results1 = query_knowledge(query)
        results2 = query_knowledge(query)

        self.assertGreater(len(results1), 0)
        self.assertEqual(len(results1), len(results2))
        self.assertEqual(
            [r.record_id for r in results1],
            [r.record_id for r in results2],
        )
        self.assertEqual(
            [r.record_hash for r in results1],
            [r.record_hash for r in results2],
        )

    def test_02_categories_constrain_results_correctly(self) -> None:
        """Requirement 2: Categories constrain results correctly."""
        proc_query = KnowledgeQuery(categories=("procedure",))
        proc_results = query_knowledge(proc_query)
        self.assertEqual(len(proc_results), 1)
        self.assertEqual(proc_results[0].record_id, "procedure:destructive-action-gate")
        self.assertEqual(proc_results[0].category, "procedure")

        arch_query = KnowledgeQuery(categories=("architecture",))
        arch_results = query_knowledge(arch_query)
        self.assertEqual(len(arch_results), 2)
        for r in arch_results:
            self.assertEqual(r.category, "architecture")

        # Identity category has 1 active record by default (rejected witness claim excluded)
        identity_query = KnowledgeQuery(categories=("identity",))
        identity_results = query_knowledge(identity_query)
        self.assertEqual(len(identity_results), 1)
        self.assertEqual(identity_results[0].record_id, "identity:dustin-authority")

        nonexistent_query = KnowledgeQuery(categories=("nonexistent_category",))
        empty_results = query_knowledge(nonexistent_query)
        self.assertEqual(len(empty_results), 0)

    def test_03_provenance_survives_conversion_into_priming_item(self) -> None:
        """Requirement 3: Provenance survives conversion into PrimingItem."""
        rec = next(r for r in BOOTSTRAP_KNOWLEDGE_SEEDS if r.record_id == "identity:dustin-authority")
        item = rec.to_priming_item()

        self.assertIsInstance(item, PrimingItem)
        self.assertEqual(item.item_id, "identity:dustin-authority")
        self.assertEqual(item.excerpt, rec.content)
        self.assertEqual(item.category, "identity")
        self.assertEqual(item.source_kind, "constitution")
        self.assertEqual(item.source_reference, "docs/constitution/JOSIE_CONSTITUTION.md#human-authority")
        self.assertEqual(item.confidence, "high")

        # Compact evidence conversion preserves core provenance fields
        evidence = item.to_retrieved_evidence()
        self.assertEqual(evidence["evidence_id"], "identity:dustin-authority")
        self.assertEqual(evidence["excerpt"], rec.content)
        self.assertEqual(evidence["source_kind"], "constitution")
        self.assertEqual(evidence["source_reference"], "docs/constitution/JOSIE_CONSTITUTION.md#human-authority")

    def test_04_current_canonical_distinguishable_from_superseded_rejected(self) -> None:
        """Requirement 4: Current/canonical records are distinguishable from superseded/rejected records."""
        # By default, rejected records are excluded
        default_results = query_knowledge(KnowledgeQuery())
        result_ids = {r.record_id for r in default_results}
        self.assertNotIn("witness:genesis-clm-012-bernie-values", result_ids)

        # Include rejected witness record explicitly
        rejected_results = query_knowledge(
            KnowledgeQuery(categories=("identity",), include_rejected=True)
        )
        rej_ids = {r.record_id for r in rejected_results}
        self.assertIn("witness:genesis-clm-012-bernie-values", rej_ids)
        witness_rec = next(r for r in rejected_results if r.record_id == "witness:genesis-clm-012-bernie-values")
        self.assertTrue(witness_rec.is_rejected())
        self.assertFalse(witness_rec.is_current())

        # Test superseded claim distinguishing
        superseded_seed = KnowledgeRecord(
            record_id="arch:historical-hydra-multihead",
            category="architecture",
            content="Hydra was the multi-model multi-head orchestration project name.",
            source_kind="canonical_versioned",
            source_reference="docs/identity/genesis/CLAIM_LEDGER.yaml#GEN-CLM-008",
            timestamp="2026-08-09",
            confidence="high",
            status="superseded",
            evidence_class="CANONICAL",
            superseded_by="arch:identity-above-models",
        )
        custom_query_default = query_knowledge(
            KnowledgeQuery(categories=("architecture",), include_superseded=False),
            records=[*BOOTSTRAP_KNOWLEDGE_SEEDS, superseded_seed],
        )
        self.assertNotIn("arch:historical-hydra-multihead", {r.record_id for r in custom_query_default})

        custom_query_sup = query_knowledge(
            KnowledgeQuery(categories=("architecture",), include_superseded=True),
            records=[*BOOTSTRAP_KNOWLEDGE_SEEDS, superseded_seed],
        )
        self.assertIn("arch:historical-hydra-multihead", {r.record_id for r in custom_query_sup})
        sup_rec = next(r for r in custom_query_sup if r.record_id == "arch:historical-hydra-multihead")
        self.assertTrue(sup_rec.is_superseded())
        self.assertFalse(sup_rec.is_current())
        self.assertEqual(sup_rec.superseded_by, "arch:identity-above-models")

    def test_05_invalid_missing_provenance_fails_closed(self) -> None:
        """Requirement 5: Invalid/missing provenance fails closed where required."""
        with self.assertRaises(ValueError):
            KnowledgeRecord(
                record_id="",
                category="identity",
                content="test",
                source_kind="constitution",
                source_reference="ref",
                timestamp="2026-08-09",
            )

        with self.assertRaises(ValueError):
            KnowledgeRecord(
                record_id="rec-01",
                category="identity",
                content="test",
                source_kind="constitution",
                source_reference="",
                timestamp="2026-08-09",
            )

        with self.assertRaises(ValueError):
            KnowledgeRecord(
                record_id="rec-01",
                category="identity",
                content="test",
                source_kind="constitution",
                source_reference="ref",
                timestamp="2026-08-09",
                confidence="untested",
            )

        with self.assertRaises(ValueError):
            KnowledgeRecord(
                record_id="rec-01",
                category="identity",
                content="test",
                source_kind="constitution",
                source_reference="ref",
                timestamp="2026-08-09",
                status="uncertain",
            )

        with self.assertRaises(ValueError):
            KnowledgeRecord(
                record_id="rec-01",
                category="identity",
                content="test",
                source_kind="constitution",
                source_reference="ref",
                timestamp="2026-08-09",
                evidence_class="UNVALIDATED_CLASS",
            )

        with self.assertRaises(ValueError):
            KnowledgeQuery(schema_version="99.0")

        with self.assertRaises(ValueError):
            KnowledgeQuery(max_records=0)

        with self.assertRaises(ValueError):
            KnowledgeRecord.from_dict({"record_id": ""})

    def test_06_empty_query_result_is_explicit_and_valid(self) -> None:
        """Requirement 6: Empty query result is explicit and valid."""
        manifest = PrimingManifest(
            task_id="task-empty-001",
            knowledge_categories=("nonexistent_category",),
        )
        bundle = assemble_priming_from_knowledge(manifest)

        self.assertTrue(bundle.is_empty)
        self.assertEqual(len(bundle.items), 0)
        self.assertEqual(len(bundle.source_ids), 0)
        self.assertEqual(len(bundle.bundle_hash), 64)

        prov = bundle.to_provenance_record()
        self.assertTrue(prov["is_empty"])
        self.assertEqual(prov["item_count"], 0)
        self.assertEqual(prov["source_ids"], [])

    def test_07_same_knowledge_records_and_manifest_produce_identical_bundle_hash(self) -> None:
        """Requirement 7: Same knowledge records + same manifest produce identical priming bundle hash."""
        manifest = PrimingManifest(
            task_id="task-reproduce-hash",
            knowledge_categories=("identity", "architecture"),
        )
        bundle1 = assemble_priming_from_knowledge(manifest)
        bundle2 = assemble_priming_from_knowledge(manifest)

        self.assertEqual(bundle1.bundle_hash, bundle2.bundle_hash)
        self.assertEqual(bundle1.manifest_hash, bundle2.manifest_hash)
        self.assertFalse(bundle1.is_empty)

        # Shuffled records passed to assemble_priming_bundle still produce identical bundle hash
        records = query_knowledge_for_priming(manifest)
        shuffled = list(reversed(records))
        bundle_shuffled = assemble_priming_bundle(manifest, shuffled)
        self.assertEqual(bundle1.bundle_hash, bundle_shuffled.bundle_hash)

    def test_08_irrelevant_knowledge_does_not_enter_worker_prompt(self) -> None:
        """Requirement 8: Irrelevant knowledge does not enter worker prompt."""
        manifest = PrimingManifest(
            task_id="task-proc-only",
            knowledge_categories=("procedure",),
        )
        bundle = assemble_priming_from_knowledge(manifest)

        order_data = {
            "schema_version": "1",
            "job_id": "job-proc-001",
            "role": "safety inspector",
            "objective": "Audit destructive action gates",
            "workspace": str(self.tmp_dir),
            "harness": "mock",
            "harness_executable": sys.executable,
            "model": "mock/exact",
            "allowed_changed_paths": ["report.txt"],
            "timeout_seconds": 60,
            "max_attempts": 1,
            "acceptance": [{"type": "file_exists", "path": "report.txt"}],
            "prompt_profile": "test",
            "receipt_destination": str(self.tmp_dir),
        }
        apply_priming_to_work_order(order_data, bundle)
        order = WorkOrder.validate(order_data)
        prompt = compile_prompt(order)

        # Procedure evidence is present
        self.assertIn("Capability is not authority", prompt)
        # Unrelated identity/architecture knowledge is NOT present
        self.assertNotIn("Dustin is final human authority", prompt)
        self.assertNotIn("Supervisor and worker separation", prompt)

    def test_09_compact_evidence_reaches_prompt_contract(self) -> None:
        """Requirement 9: Compact evidence reaches Prompt Contract."""
        manifest = PrimingManifest(
            task_id="task-authority-check",
            knowledge_categories=("identity",),
        )
        bundle = assemble_priming_from_knowledge(manifest)

        order_data = {
            "schema_version": "1",
            "job_id": "job-authority-001",
            "role": "governance inspector",
            "objective": "Audit human authority boundaries",
            "workspace": str(self.tmp_dir),
            "harness": "mock",
            "harness_executable": sys.executable,
            "model": "mock/exact",
            "allowed_changed_paths": ["audit.txt"],
            "timeout_seconds": 60,
            "max_attempts": 1,
            "acceptance": [{"type": "file_exists", "path": "audit.txt"}],
            "prompt_profile": "test",
            "receipt_destination": str(self.tmp_dir),
        }
        apply_priming_to_work_order(order_data, bundle)
        order = WorkOrder.validate(order_data)
        prompt = compile_prompt(order)

        self.assertTrue(validate_contract_prompt(prompt))
        self.assertIn("RESOURCE RULES", prompt)
        self.assertIn("Task-relevant evidence:", prompt)
        self.assertIn("[identity:dustin-authority]", prompt)
        self.assertIn("Dustin is final human authority", prompt)

    def test_10_priming_provenance_reaches_receipts_without_source_body_duplication(self) -> None:
        """Requirement 10: Priming provenance still reaches receipts without source-body duplication."""
        manifest = PrimingManifest(
            task_id="task-audit-provenance",
            knowledge_categories=("architecture", "procedure"),
        )
        bundle = assemble_priming_from_knowledge(manifest)

        order_data = {
            "schema_version": "1",
            "job_id": "job-provenance-001",
            "role": "auditor",
            "objective": "Record execution receipt",
            "workspace": str(self.tmp_dir),
            "harness": "mock",
            "harness_executable": sys.executable,
            "model": "mock/exact",
            "allowed_changed_paths": ["out.txt"],
            "timeout_seconds": 60,
            "max_attempts": 1,
            "acceptance": [{"type": "file_exists", "path": "out.txt"}],
            "prompt_profile": "test",
            "receipt_destination": str(self.tmp_dir),
        }
        apply_priming_to_work_order(order_data, bundle)
        order = WorkOrder.validate(order_data)

        receipt_priming = order.priming_context
        self.assertIsNotNone(receipt_priming)
        self.assertEqual(receipt_priming["bundle_hash"], bundle.bundle_hash)
        self.assertEqual(receipt_priming["manifest_hash"], bundle.manifest_hash)
        self.assertEqual(receipt_priming["item_count"], len(bundle.items))
        self.assertEqual(receipt_priming["source_ids"], list(bundle.source_ids))

        for src in receipt_priming["sources"]:
            self.assertIn("item_id", src)
            self.assertIn("category", src)
            self.assertIn("source_kind", src)
            self.assertIn("source_reference", src)
            self.assertIn("confidence", src)
            self.assertIn("item_hash", src)
            self.assertNotIn("excerpt", src)
            self.assertNotIn("content", src)

    def test_11_sqlite_persistence_and_loading_roundtrip(self) -> None:
        """Requirement 11/Schema: SQLite storage round-trip through existing memory_claims schema."""
        db_path = Path(self.tmp_dir) / "test_josie.db"
        store = LocalStore(db_path)

        seed_stats = seed_canonical_knowledge(store)
        self.assertEqual(seed_stats["entities_seeded"], 3)
        self.assertEqual(seed_stats["claims_seeded"], len(BOOTSTRAP_KNOWLEDGE_SEEDS))
        self.assertEqual(len(seed_stats.inserted), len(BOOTSTRAP_KNOWLEDGE_SEEDS))
        self.assertEqual(len(seed_stats.unchanged), 0)
        self.assertEqual(len(seed_stats.conflicts), 0)

        loaded_records = load_knowledge_from_store(store)
        self.assertEqual(len(loaded_records), len(BOOTSTRAP_KNOWLEDGE_SEEDS))

        proc_records = query_knowledge(KnowledgeQuery(categories=("procedure",)), store=store)
        self.assertEqual(len(proc_records), 1)
        self.assertEqual(proc_records[0].record_id, "procedure:destructive-action-gate")

    def test_12_direct_knowledge_record_in_assemble_priming_bundle(self) -> None:
        """Requirement 12: KnowledgeRecord duck-typing directly into assemble_priming_bundle."""
        manifest = PrimingManifest(
            task_id="task-duck-typing",
            knowledge_categories=("procedure",),
        )
        bundle = assemble_priming_bundle(manifest, BOOTSTRAP_KNOWLEDGE_SEEDS)
        self.assertFalse(bundle.is_empty)
        self.assertEqual(len(bundle.items), 1)
        self.assertEqual(bundle.items[0].item_id, "procedure:destructive-action-gate")
        self.assertEqual(bundle.items[0].category, "procedure")

    def test_13_human_adjudication_overwrite_protection(self) -> None:
        """Problem 2: Seeding must never overwrite human adjudication or modified claims."""
        db_path = Path(self.tmp_dir) / "test_protect.db"
        store = LocalStore(db_path)

        # 1. Initial seed inserts records
        res1 = seed_canonical_knowledge(store)
        self.assertEqual(len(res1.inserted), len(BOOTSTRAP_KNOWLEDGE_SEEDS))
        self.assertEqual(len(res1.conflicts), 0)

        # 2. Identical reseed is idempotent
        res2 = seed_canonical_knowledge(store)
        self.assertEqual(len(res2.inserted), 0)
        self.assertEqual(len(res2.unchanged), len(BOOTSTRAP_KNOWLEDGE_SEEDS))
        self.assertEqual(len(res2.conflicts), 0)
        self.assertFalse(res2.has_conflicts)

        # 3. Simulate human adjudication: mark identity claim superseded in SQLite
        with store._connect() as conn:
            conn.execute(
                "UPDATE memory_claims SET status = 'superseded', superseded_by_claim_id = 'claim:new-human-adjudication', "
                "canonical_effect = 0 WHERE claim_id = 'identity:dustin-authority'"
            )

        # Reseeding must NOT reset status back to active
        res3 = seed_canonical_knowledge(store)
        self.assertTrue(res3.has_conflicts)
        self.assertEqual(len(res3.conflicts), 1)
        conflict = res3.conflicts[0]
        self.assertEqual(conflict["claim_id"], "identity:dustin-authority")
        self.assertEqual(conflict["persisted"]["status"], "superseded")
        self.assertEqual(conflict["seed"]["status"], "active")

        # Verify database still retains human adjudication
        loaded = {r.record_id: r for r in load_knowledge_from_store(store)}
        self.assertEqual(loaded["identity:dustin-authority"].status, "superseded")
        self.assertEqual(loaded["identity:dustin-authority"].superseded_by, "claim:new-human-adjudication")

        # 4. Simulate human content refinement in SQLite
        with store._connect() as conn:
            conn.execute(
                "UPDATE memory_claims SET value_text = 'Custom human-reviewed refined wording.' "
                "WHERE claim_id = 'arch:identity-above-models'"
            )

        res4 = seed_canonical_knowledge(store)
        conflict_ids = {c["claim_id"] for c in res4.conflicts}
        self.assertIn("arch:identity-above-models", conflict_ids)

        # Persisted text was preserved and not overwritten
        loaded2 = {r.record_id: r for r in load_knowledge_from_store(store)}
        self.assertEqual(loaded2["arch:identity-above-models"].content, "Custom human-reviewed refined wording.")

    def test_14_multi_evidence_claims_do_not_duplicate_knowledge_records(self) -> None:
        """Problem 3: Multiple evidence rows for one claim must produce exactly one KnowledgeRecord."""
        db_path = Path(self.tmp_dir) / "test_multiev.db"
        store = LocalStore(db_path)

        # Seed initial records
        seed_canonical_knowledge(store)

        # Add two additional evidence rows for identity:dustin-authority
        with store._connect() as conn:
            conn.execute(
                "INSERT INTO claim_evidence(claim_id, evidence_id, relation_type, source_type, source_pointer, evidence_class, excerpt_sha256, created_at) "
                "VALUES ('identity:dustin-authority', 'ev:genesis-001', 'supports', 'genesis_session', 'docs/identity/genesis/SESSION_001.md', 'CANONICAL', 'abc123', '2026-08-09')"
            )
            conn.execute(
                "INSERT INTO claim_evidence(claim_id, evidence_id, relation_type, source_type, source_pointer, evidence_class, excerpt_sha256, created_at) "
                "VALUES ('identity:dustin-authority', 'ev:ratification', 'supports', 'decision_log', 'docs/governance/RATIFICATION.md', 'CANONICAL', 'def456', '2026-08-09')"
            )

        loaded = load_knowledge_from_store(store)
        authority_records = [r for r in loaded if r.record_id == "identity:dustin-authority"]

        # Exactly ONE KnowledgeRecord exists despite 3 evidence rows
        self.assertEqual(len(authority_records), 1)
        rec = authority_records[0]

        # Multi-evidence metadata retained in structured references
        ev_refs = rec.metadata.get("evidence_references", [])
        self.assertEqual(len(ev_refs), 3)
        ev_ids = {e["evidence_id"] for e in ev_refs}
        self.assertIn("ev:identity:dustin-authority", ev_ids)
        self.assertIn("ev:genesis-001", ev_ids)
        self.assertIn("ev:ratification", ev_ids)

        # Priming manifest with identity returns exactly 1 item (no duplication in worker prompt)
        manifest = PrimingManifest(task_id="t-multi", knowledge_categories=("identity",))
        bundle = assemble_priming_from_knowledge(manifest, store=store)
        self.assertEqual(len(bundle.items), 1)
        self.assertEqual(bundle.items[0].item_id, "identity:dustin-authority")

    def test_15_authority_evidence_class_ordering(self) -> None:
        """Authority audit: Lower-quality evidence cannot outrank CANONICAL/VERIFIED evidence."""
        # Create a lower-quality RETRIEVED record whose record_id alphabetically sorts BEFORE canonical record
        retrieved_record = KnowledgeRecord(
            record_id="aaa_first_alphabetical",
            category="identity",
            content="Retrieved secondary witness note.",
            source_kind="witness",
            source_reference="notes/witness.txt",
            timestamp="2026-08-09",
            confidence="high",
            status="active",
            evidence_class="RETRIEVED",
        )
        canonical_record = KnowledgeRecord(
            record_id="zzz_last_alphabetical",
            category="identity",
            content="Canonical constitutional law.",
            source_kind="constitution",
            source_reference="docs/constitution/JOSIE_CONSTITUTION.md",
            timestamp="2026-08-09",
            confidence="high",
            status="active",
            evidence_class="CANONICAL",
        )

        sorted_recs = sort_knowledge_records([retrieved_record, canonical_record])
        # CANONICAL must sort FIRST despite its record_id starting with 'zzz'
        self.assertEqual(sorted_recs[0].record_id, "zzz_last_alphabetical")
        self.assertEqual(sorted_recs[0].evidence_class, "CANONICAL")
        self.assertEqual(sorted_recs[1].record_id, "aaa_first_alphabetical")
        self.assertEqual(sorted_recs[1].evidence_class, "RETRIEVED")

    def test_16_live_database_protection(self) -> None:
        """Problem 4: Tests and queries must never touch or mutate D:\\Josie\\data\\josie.db."""
        live_db = ROOT / "data" / "josie.db"
        self.assertTrue(live_db.exists(), f"live database file {live_db} not found")

        # Open in read-only URI mode to verify baseline state
        conn = sqlite3.connect(f"file:{live_db.as_posix()}?mode=ro", uri=True)
        try:
            cur = conn.cursor()
            entities_count = cur.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
            claims_count = cur.execute("SELECT COUNT(*) FROM memory_claims").fetchone()[0]
            evidence_count = cur.execute("SELECT COUNT(*) FROM claim_evidence").fetchone()[0]
        finally:
            conn.close()

        # The live database must remain pristine (0 bootstrap rows inserted by test suite)
        self.assertEqual(entities_count, 0)
        self.assertEqual(claims_count, 0)
        self.assertEqual(evidence_count, 0)


if __name__ == "__main__":
    unittest.main()
