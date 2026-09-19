from __future__ import annotations

import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.priming import (
    DEFAULT_MAX_CHARACTERS,
    DEFAULT_MAX_ITEM_CHARACTERS,
    DEFAULT_MAX_ITEMS,
    PRIMING_SCHEMA_VERSION,
    PrimingBundle,
    PrimingItem,
    PrimingManifest,
    apply_priming_to_work_order,
    assemble_priming_bundle,
)
from supervisor.prompt_compiler import compile_prompt
from supervisor.prompt_contract import validate_contract_prompt
from supervisor.run_job import execute
from supervisor.work_order import ValidationError, WorkOrder


class PrimingTests(unittest.TestCase):
    def setUp(self):
        self.workspace = ROOT

    def sample_records(self) -> list[dict]:
        return [
            {
                "item_id": "CLM-001",
                "category": "architecture",
                "excerpt": "Supervisor manages bounded worker process lifecycles and independent acceptance.",
                "source_kind": "canonical_versioned",
                "source_reference": "docs/architecture/SUPERVISOR.md",
                "confidence": "high",
            },
            {
                "item_id": "CLM-002",
                "category": "architecture",
                "excerpt": "Prompt Contract v1 enforces 12 canonical sections in strict order.",
                "source_kind": "canonical_versioned",
                "source_reference": "supervisor/prompt_contract.py",
                "confidence": "high",
            },
            {
                "item_id": "CLM-003",
                "category": "conventions",
                "excerpt": "Worker outputs are evidence and cannot declare authoritative PASS.",
                "source_kind": "primary_authoritative",
                "source_reference": "docs/memory/MEMORY_SCHEMA.md",
                "confidence": "high",
            },
            {
                "item_id": "CLM-004",
                "category": "identity",
                "excerpt": "Josie identity is stewardship, not sovereignty.",
                "source_kind": "canonical_versioned",
                "source_reference": "docs/constitution/CONSTITUTION.md",
                "confidence": "high",
            },
        ]

    def test_01_same_manifest_and_sources_produces_identical_bundle_and_hash(self):
        manifest = PrimingManifest(
            task_id="task-reproducibility-01",
            knowledge_categories=("architecture", "conventions"),
        )
        sources = self.sample_records()

        bundle1 = assemble_priming_bundle(manifest, sources)
        bundle2 = assemble_priming_bundle(manifest, list(sources))

        self.assertEqual(bundle1.bundle_hash, bundle2.bundle_hash)
        self.assertEqual(bundle1.manifest_hash, bundle2.manifest_hash)
        self.assertEqual(bundle1.source_ids, bundle2.source_ids)
        self.assertEqual(len(bundle1.items), len(bundle2.items))
        self.assertFalse(bundle1.is_empty)

    def test_02_content_or_provenance_changes_bundle_hash(self):
        manifest = PrimingManifest(
            task_id="task-provenance-01",
            knowledge_categories=("architecture",),
        )
        sources_base = self.sample_records()
        bundle_base = assemble_priming_bundle(manifest, sources_base)

        # 1. Change excerpt content
        sources_content_diff = [dict(s) for s in sources_base]
        sources_content_diff[0]["excerpt"] = "Modified excerpt content."
        bundle_content_diff = assemble_priming_bundle(manifest, sources_content_diff)
        self.assertNotEqual(bundle_base.bundle_hash, bundle_content_diff.bundle_hash)

        # 2. Change source_reference (provenance)
        sources_prov_diff = [dict(s) for s in sources_base]
        sources_prov_diff[0]["source_reference"] = "docs/other/different_path.md"
        bundle_prov_diff = assemble_priming_bundle(manifest, sources_prov_diff)
        self.assertNotEqual(bundle_base.bundle_hash, bundle_prov_diff.bundle_hash)

        # 3. Change source_kind
        sources_kind_diff = [dict(s) for s in sources_base]
        sources_kind_diff[0]["source_kind"] = "model_output"
        bundle_kind_diff = assemble_priming_bundle(manifest, sources_kind_diff)
        self.assertNotEqual(bundle_base.bundle_hash, bundle_kind_diff.bundle_hash)

        # 4. Change category
        sources_cat_diff = [dict(s) for s in sources_base]
        sources_cat_diff[0]["category"] = "conventions"
        bundle_cat_diff = assemble_priming_bundle(manifest, sources_cat_diff)
        self.assertNotEqual(bundle_base.bundle_hash, bundle_cat_diff.bundle_hash)

    def test_03_priming_respects_item_count_and_size_bounds(self):
        # Test max_items bound
        manifest_count = PrimingManifest(task_id="task-bounds-count", max_items=2)
        bundle_count = assemble_priming_bundle(manifest_count, self.sample_records())
        self.assertEqual(len(bundle_count.items), 2)

        # Test max_item_characters bound
        long_record = {
            "item_id": "CLM-LONG",
            "category": "testing",
            "excerpt": "X" * 2000,
        }
        manifest_item_size = PrimingManifest(
            task_id="task-bounds-item-size",
            max_item_characters=300,
        )
        bundle_item_size = assemble_priming_bundle(manifest_item_size, [long_record])
        self.assertEqual(len(bundle_item_size.items), 1)
        self.assertEqual(len(bundle_item_size.items[0].excerpt), 300)

        # Test total max_characters budget
        manifest_total_budget = PrimingManifest(
            task_id="task-bounds-total",
            max_characters=150,
            max_item_characters=100,
        )
        records_multi = [
            {"item_id": f"CLM-{i}", "excerpt": "A" * 90}
            for i in range(5)
        ]
        bundle_total = assemble_priming_bundle(manifest_total_budget, records_multi)
        total_chars = sum(len(item.excerpt) for item in bundle_total.items)
        self.assertLessEqual(total_chars, 150)
        # First item gets 90 chars, second item truncated to remaining budget of 60 chars
        self.assertEqual(len(bundle_total.items), 2)
        self.assertEqual(len(bundle_total.items[0].excerpt), 90)
        self.assertEqual(len(bundle_total.items[1].excerpt), 60)
        self.assertEqual(total_chars, 150)

    def test_04_empty_no_match_priming_is_explicit_and_valid(self):
        manifest = PrimingManifest(
            task_id="task-empty-01",
            knowledge_categories=("nonexistent_category",),
        )
        bundle = assemble_priming_bundle(manifest, self.sample_records())

        self.assertTrue(bundle.is_empty)
        self.assertEqual(len(bundle.items), 0)
        self.assertEqual(bundle.source_ids, ())
        self.assertTrue(isinstance(bundle.bundle_hash, str))
        self.assertEqual(len(bundle.bundle_hash), 64)

        prov = bundle.to_provenance_record()
        self.assertTrue(prov["is_empty"])
        self.assertEqual(prov["item_count"], 0)
        self.assertEqual(prov["source_ids"], [])
        self.assertEqual(prov["sources"], [])

    def test_05_unsupported_priming_schema_version_fails_closed(self):
        # PrimingManifest rejects invalid version
        with self.assertRaises(ValueError):
            PrimingManifest(task_id="t1", schema_version="2.0")

        # PrimingBundle rejects invalid version
        with self.assertRaises(ValueError):
            PrimingBundle(schema_version="0.9", manifest_hash="abc")

        # WorkOrder rejects unsupported priming schema_version
        base_order = {
            "schema_version": "1",
            "job_id": "job-bad-priming-ver",
            "objective": "test",
            "workspace": str(self.workspace),
            "harness": "mock",
            "harness_executable": sys.executable,
            "model": "mock/exact",
            "allowed_changed_paths": ["target.txt"],
            "timeout_seconds": 30,
            "max_attempts": 1,
            "acceptance": [{"type": "file_exists", "path": "target.txt"}],
            "prompt_profile": "test",
            "receipt_destination": str(self.workspace / "receipts"),
            "priming_context": {
                "schema_version": "99.0",
                "bundle_hash": "a" * 64,
                "is_empty": False,
            },
        }
        with self.assertRaises(ValidationError) as cm:
            WorkOrder.validate(base_order)
        self.assertIn("unsupported priming schema_version", str(cm.exception))

    def test_06_work_order_accepts_valid_priming_metadata_and_rejects_malformed(self):
        base_order = {
            "schema_version": "1",
            "job_id": "job-priming-valid",
            "objective": "test valid priming metadata",
            "workspace": str(self.workspace),
            "harness": "mock",
            "harness_executable": sys.executable,
            "model": "mock/exact",
            "allowed_changed_paths": ["target.txt"],
            "timeout_seconds": 30,
            "max_attempts": 1,
            "acceptance": [{"type": "file_exists", "path": "target.txt"}],
            "prompt_profile": "test",
            "receipt_destination": str(self.workspace / "receipts"),
        }

        manifest = PrimingManifest(task_id="t-val", knowledge_categories=("architecture",))
        bundle = assemble_priming_bundle(manifest, self.sample_records())

        # 1. Valid priming metadata
        valid_order_data = dict(base_order)
        apply_priming_to_work_order(valid_order_data, bundle)
        order = WorkOrder.validate(valid_order_data)
        self.assertIsNotNone(order.priming_context)
        self.assertEqual(order.priming_bundle_hash, bundle.bundle_hash)
        self.assertEqual(order.priming_context["bundle_hash"], bundle.bundle_hash)

        # 2. Malformed: priming_context is not a dict
        bad_pc_type = dict(base_order, priming_context="not-a-dict")
        with self.assertRaises(ValidationError):
            WorkOrder.validate(bad_pc_type)

        # 3. Malformed: missing bundle_hash
        bad_pc_hash = dict(base_order, priming_context={"schema_version": "1.0", "is_empty": False})
        with self.assertRaises(ValidationError):
            WorkOrder.validate(bad_pc_hash)

        # 4. Malformed: source_ids not list of strings
        bad_pc_sources = dict(base_order, priming_context={"schema_version": "1.0", "bundle_hash": "a" * 64, "source_ids": [123]})
        with self.assertRaises(ValidationError):
            WorkOrder.validate(bad_pc_sources)

        # 5. Malformed: sources has entries missing item_id
        bad_pc_entry = dict(base_order, priming_context={"schema_version": "1.0", "bundle_hash": "a" * 64, "sources": [{}]})
        with self.assertRaises(ValidationError):
            WorkOrder.validate(bad_pc_entry)

        # 6. Malformed: priming_bundle_hash mismatch
        bad_mismatch = dict(base_order, priming_context={"schema_version": "1.0", "bundle_hash": "a" * 64}, priming_bundle_hash="b" * 64)
        with self.assertRaises(ValidationError):
            WorkOrder.validate(bad_mismatch)

    def test_07_prompt_compilation_contains_only_compact_evidence_no_provenance_bulk(self):
        manifest = PrimingManifest(task_id="t-prompt", knowledge_categories=("architecture",))
        bundle = assemble_priming_bundle(manifest, self.sample_records())

        order_data = {
            "schema_version": "1",
            "job_id": "job-prompt-test",
            "objective": "check prompt compactness",
            "workspace": str(self.workspace),
            "harness": "mock",
            "harness_executable": sys.executable,
            "model": "mock/exact",
            "allowed_changed_paths": ["target.txt"],
            "timeout_seconds": 30,
            "max_attempts": 1,
            "acceptance": [{"type": "file_exists", "path": "target.txt"}],
            "prompt_profile": "test",
            "receipt_destination": str(self.workspace / "receipts"),
        }
        apply_priming_to_work_order(order_data, bundle)
        order = WorkOrder.validate(order_data)
        prompt = compile_prompt(order)

        # Conforms strictly to Prompt Contract v1
        parsed = validate_contract_prompt(prompt)
        resource_sec = parsed["RESOURCE RULES"]

        # Compact excerpts appear in prompt
        self.assertIn("CLM-001", resource_sec)
        self.assertIn("CLM-002", resource_sec)

        # Provenance metadata, bundle hash, and manifest hash MUST NOT appear in the prompt
        self.assertNotIn(bundle.bundle_hash, prompt)
        self.assertNotIn(bundle.manifest_hash, prompt)
        self.assertNotIn("docs/architecture/SUPERVISOR.md", prompt)
        self.assertNotIn("canonical_versioned", prompt)

    def test_08_receipts_expose_priming_metadata_without_full_source_bodies(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            receipts_dir = tmp_path / "receipts"
            receipts_dir.mkdir(parents=True)

            target_file = tmp_path / "result.txt"
            target_file.write_text("OK", encoding="utf-8")

            manifest = PrimingManifest(task_id="t-receipt", knowledge_categories=("architecture",))
            bundle = assemble_priming_bundle(manifest, self.sample_records())

            order_data = {
                "schema_version": "1",
                "job_id": "job-receipt-audit-01",
                "objective": "allowed",
                "workspace": str(tmp_path),
                "harness": "mock",
                "harness_executable": sys.executable,
                "model": "mock/exact",
                "allowed_changed_paths": ["result.txt"],
                "timeout_seconds": 10,
                "max_attempts": 1,
                "acceptance": [{"type": "file_exists", "path": "result.txt"}],
                "prompt_profile": "test",
                "receipt_destination": str(receipts_dir),
            }
            apply_priming_to_work_order(order_data, bundle)

            order_file = tmp_path / "order.json"
            order_file.write_text(json.dumps(order_data), encoding="utf-8")
            order_data["allowed_changed_paths"].append("order.json")
            order_file.write_text(json.dumps(order_data), encoding="utf-8")

            receipt, receipt_path = execute(order_file)

            self.assertIsNotNone(receipt)
            self.assertIn("priming", receipt)
            priming_rec = receipt["priming"]

            # Answers core audit questions
            self.assertTrue(priming_rec["used"])
            self.assertEqual(priming_rec["bundle_hash"], bundle.bundle_hash)
            self.assertEqual(priming_rec["manifest_hash"], bundle.manifest_hash)
            self.assertFalse(priming_rec["is_empty"])
            self.assertEqual(priming_rec["source_ids"], list(bundle.source_ids))
            self.assertEqual(priming_rec["schema_version"], PRIMING_SCHEMA_VERSION)

            # Check that sources list contains provenance references/hashes, not entire bodies
            for s in priming_rec["sources"]:
                self.assertIn("item_id", s)
                self.assertIn("source_kind", s)
                self.assertIn("source_reference", s)
                self.assertIn("item_hash", s)
                self.assertNotIn("excerpt", s)

    def test_09_exclusion_filtering(self):
        manifest = PrimingManifest(
            task_id="task-excl",
            knowledge_categories=("architecture", "conventions"),
            exclusions=("CLM-001", "docs/memory/MEMORY_SCHEMA.md"),
        )
        bundle = assemble_priming_bundle(manifest, self.sample_records())

        self.assertNotIn("CLM-001", bundle.source_ids)
        self.assertNotIn("CLM-003", bundle.source_ids)  # excluded by source_reference
        self.assertIn("CLM-002", bundle.source_ids)

    def test_10_apply_priming_supplements_existing_retrieved_evidence(self):
        order_data = {
            "retrieved_evidence": [{"evidence_id": "PRE-EXISTING", "excerpt": "Prior context"}],
        }
        manifest = PrimingManifest(task_id="t-suppl", knowledge_categories=("architecture",))
        bundle = assemble_priming_bundle(manifest, self.sample_records()[:1])

        apply_priming_to_work_order(order_data, bundle, replace_evidence=False)
        eids = [e["evidence_id"] for e in order_data["retrieved_evidence"]]
        self.assertIn("PRE-EXISTING", eids)
        self.assertIn("CLM-001", eids)
        self.assertEqual(order_data["priming_bundle_hash"], bundle.bundle_hash)

    def test_11_character_budget_not_exceeded_even_when_first_item_larger_than_max_characters(self):
        # Specific regression test for Issue 1:
        # sum(len(item.excerpt) for item in bundle.items) <= manifest.max_characters
        # even when the FIRST source item is larger than max_characters.
        # Example from problem statement:
        # max_characters = 150, max_item_characters = 300, first excerpt length = 300
        manifest = PrimingManifest(
            task_id="task-budget-regression",
            max_characters=150,
            max_item_characters=300,
        )
        sources = [
            {
                "item_id": "CLM-001-LARGE",
                "category": "general",
                "excerpt": "A" * 300,
            },
            {
                "item_id": "CLM-002-SMALL",
                "category": "general",
                "excerpt": "B" * 50,
            },
        ]
        bundle = assemble_priming_bundle(manifest, sources)

        total_chars = sum(len(item.excerpt) for item in bundle.items)
        self.assertLessEqual(total_chars, manifest.max_characters)
        self.assertEqual(len(bundle.items), 1)
        self.assertEqual(len(bundle.items[0].excerpt), 150)
        self.assertEqual(bundle.items[0].excerpt, "A" * 150)

        # Regression test with multiple items where aggregate budget is strictly enforced
        manifest_multi = PrimingManifest(
            task_id="task-budget-multi",
            max_characters=150,
            max_item_characters=100,
        )
        sources_multi = [
            {"item_id": "CLM-M1", "excerpt": "X" * 120},  # truncated to 100
            {"item_id": "CLM-M2", "excerpt": "Y" * 120},  # truncated to remaining 50
            {"item_id": "CLM-M3", "excerpt": "Z" * 120},  # budget exhausted, skipped
        ]
        bundle_multi = assemble_priming_bundle(manifest_multi, sources_multi)
        self.assertEqual(len(bundle_multi.items), 2)
        self.assertEqual(len(bundle_multi.items[0].excerpt), 100)
        self.assertEqual(len(bundle_multi.items[1].excerpt), 50)
        self.assertEqual(sum(len(it.excerpt) for it in bundle_multi.items), 150)

        # Verify empty excerpts are never emitted merely to satisfy item count
        manifest_empty = PrimingManifest(
            task_id="task-budget-empty-never-emitted",
            max_characters=150,
            max_item_characters=100,
            max_items=5,
        )
        sources_with_empty = [
            {"item_id": "CLM-EMPTY-1", "excerpt": "   "},
            {"item_id": "CLM-VALID-1", "excerpt": "Valid content"},
            {"item_id": "CLM-EMPTY-2", "excerpt": ""},
        ]
        bundle_empty = assemble_priming_bundle(manifest_empty, sources_with_empty)
        self.assertEqual(len(bundle_empty.items), 1)
        self.assertEqual(bundle_empty.items[0].item_id, "CLM-VALID-1")
        self.assertGreater(len(bundle_empty.items[0].excerpt), 0)

    def test_12_apply_priming_prioritizes_priming_evidence_over_existing_retrieval(self):
        # Specific regression test for Issue 2:
        # A. Five generic retrieval items already exist and two-item priming bundle is applied;
        #    resulting bounded retrieved_evidence includes the two priming items.
        existing_evidence = [
            {"evidence_id": f"GEN-{i}", "excerpt": f"Generic retrieval item {i}"}
            for i in range(1, 6)
        ]
        order_data = {
            "retrieved_evidence": list(existing_evidence),
        }

        priming_sources = [
            {"item_id": "PRIME-01", "category": "architecture", "excerpt": "Priming item 1"},
            {"item_id": "PRIME-02", "category": "architecture", "excerpt": "Priming item 2"},
        ]
        manifest = PrimingManifest(task_id="task-prio", max_items=2)
        bundle = assemble_priming_bundle(manifest, priming_sources)

        apply_priming_to_work_order(order_data, bundle, replace_evidence=False)
        result_ids = [e["evidence_id"] for e in order_data["retrieved_evidence"]]

        # Condition A: Resulting bounded retrieved_evidence includes the two priming items (first priority)
        self.assertIn("PRIME-01", result_ids)
        self.assertIn("PRIME-02", result_ids)
        self.assertEqual(result_ids[0], "PRIME-01")
        self.assertEqual(result_ids[1], "PRIME-02")

        # Condition B: Remaining slots may be filled by non-duplicate existing retrieval
        self.assertEqual(result_ids[2:], ["GEN-1", "GEN-2", "GEN-3"])

        # Condition D: The result remains within the existing evidence-count bound (DEFAULT_MAX_ITEMS = 5)
        self.assertEqual(len(order_data["retrieved_evidence"]), DEFAULT_MAX_ITEMS)

        # Condition C: Duplicate evidence IDs are not repeated
        order_with_dupes = {
            "retrieved_evidence": [
                {"evidence_id": "PRIME-01", "excerpt": "Old duplicate of prime 1"},
                {"evidence_id": "GEN-1", "excerpt": "Generic 1"},
                {"evidence_id": "GEN-1", "excerpt": "Generic 1 repeat"},
                {"evidence_id": "GEN-2", "excerpt": "Generic 2"},
            ]
        }
        apply_priming_to_work_order(order_with_dupes, bundle, replace_evidence=False)
        dupe_result_ids = [e["evidence_id"] for e in order_with_dupes["retrieved_evidence"]]
        self.assertEqual(len(dupe_result_ids), len(set(dupe_result_ids)))
        self.assertEqual(dupe_result_ids, ["PRIME-01", "PRIME-02", "GEN-1", "GEN-2"])
        self.assertLessEqual(len(dupe_result_ids), DEFAULT_MAX_ITEMS)

    def test_13_work_order_hash_validation_fails_closed(self):
        base_order = {
            "schema_version": "1",
            "job_id": "job-hash-val",
            "objective": "test hash validation",
            "workspace": str(self.workspace),
            "harness": "mock",
            "harness_executable": sys.executable,
            "model": "mock/exact",
            "allowed_changed_paths": ["target.txt"],
            "timeout_seconds": 30,
            "max_attempts": 1,
            "acceptance": [{"type": "file_exists", "path": "target.txt"}],
            "prompt_profile": "test",
            "receipt_destination": str(self.workspace / "receipts"),
        }

        # 1. Non-hex characters rejected
        bad_hex_order = dict(base_order, priming_bundle_hash="g" * 64)
        with self.assertRaises(ValidationError):
            WorkOrder.validate(bad_hex_order)

        # 2. Arbitrary non-64-character hash string rejected (e.g. "abc", 63 chars, 65 chars)
        for bad_hash in ("abc", "a" * 63, "a" * 65, "", 12345):
            bad_hash_order = dict(base_order, priming_bundle_hash=bad_hash)
            with self.assertRaises(ValidationError):
                WorkOrder.validate(bad_hash_order)

        # 3. Valid uppercase and lowercase SHA-256 accepted
        valid_lower = dict(base_order, priming_bundle_hash="a" * 64)
        self.assertIsNotNone(WorkOrder.validate(valid_lower))
        valid_upper = dict(base_order, priming_bundle_hash="A" * 64)
        self.assertIsNotNone(WorkOrder.validate(valid_upper))

        # 4. priming_context.bundle_hash must be valid SHA-256 hex string
        bad_pc_bhash = dict(base_order, priming_context={"schema_version": "1.0", "bundle_hash": "abc"})
        with self.assertRaises(ValidationError):
            WorkOrder.validate(bad_pc_bhash)

        # 5. priming_context.manifest_hash must be valid SHA-256 hex string when present
        bad_pc_mhash = dict(base_order, priming_context={
            "schema_version": "1.0",
            "bundle_hash": "a" * 64,
            "manifest_hash": "not-valid-hash",
        })
        with self.assertRaises(ValidationError):
            WorkOrder.validate(bad_pc_mhash)

        # 6. sources item_hash must be valid SHA-256 hex string when present
        bad_item_hash = dict(base_order, priming_context={
            "schema_version": "1.0",
            "bundle_hash": "a" * 64,
            "sources": [{"item_id": "IT-1", "item_hash": "invalid"}],
        })
        with self.assertRaises(ValidationError):
            WorkOrder.validate(bad_item_hash)

        # 7. source_ids must be list of nonempty strings
        bad_empty_sid = dict(base_order, priming_context={
            "schema_version": "1.0",
            "bundle_hash": "a" * 64,
            "source_ids": ["valid-id", ""],
        })
        with self.assertRaises(ValidationError):
            WorkOrder.validate(bad_empty_sid)

        # 8. PrimingBundle itself rejects non-SHA-256 manifest_hash
        with self.assertRaises(ValueError):
            PrimingBundle(schema_version="1.0", manifest_hash="not-a-sha256-hex-hash")

    def test_14_terminal_receipt_paths_retain_compact_priming_metadata(self):
        manifest = PrimingManifest(task_id="t-terminal-receipts", knowledge_categories=("architecture",))
        bundle = assemble_priming_bundle(manifest, self.sample_records()[:2])

        def _assert_priming_metadata(priming_rec):
            self.assertIsNotNone(priming_rec)
            self.assertTrue(priming_rec["used"])
            self.assertEqual(priming_rec["schema_version"], PRIMING_SCHEMA_VERSION)
            self.assertEqual(priming_rec["bundle_hash"], bundle.bundle_hash)
            self.assertEqual(priming_rec["manifest_hash"], bundle.manifest_hash)
            self.assertFalse(priming_rec["is_empty"])
            self.assertEqual(priming_rec["source_ids"], list(bundle.source_ids))
            for s in priming_rec.get("sources", []):
                self.assertNotIn("excerpt", s)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            receipts_dir = tmp_path / "receipts"
            receipts_dir.mkdir(parents=True, exist_ok=True)

            base_order = {
                "schema_version": "1",
                "job_id": "job-receipt-paths",
                "objective": "allowed",
                "workspace": str(tmp_path),
                "harness": "mock",
                "harness_executable": sys.executable,
                "model": "mock/exact",
                "allowed_changed_paths": ["allowed.txt", "order.json"],
                "timeout_seconds": 10,
                "max_attempts": 1,
                "acceptance": [{"type": "file_exact", "path": "allowed.txt", "content": "OK"}],
                "prompt_profile": "test",
                "receipt_destination": str(receipts_dir),
            }
            apply_priming_to_work_order(base_order, bundle)

            # 1. Normal PASS path
            order_file = tmp_path / "order.json"
            order_file.write_text(json.dumps(base_order), encoding="utf-8")
            receipt_pass, path_pass = execute(order_file)
            self.assertEqual(receipt_pass["final_status"], "PASS")
            _assert_priming_metadata(receipt_pass.get("priming"))
            self.assertTrue(path_pass.is_file())

            # 2. Normal FAIL path
            fail_order = dict(base_order, objective="nonzero")
            order_file.write_text(json.dumps(fail_order), encoding="utf-8")
            receipt_fail, path_fail = execute(order_file)
            self.assertEqual(receipt_fail["final_status"], "FAIL")
            _assert_priming_metadata(receipt_fail.get("priming"))
            self.assertTrue(path_fail.is_file())

            # 3. Preflight/resource BLOCKED path
            with patch("supervisor.run_job.resource_check", return_value={"ok": False, "reason": "THERMAL_PREFLIGHT_BLOCKED"}):
                receipt_res_blocked, path_res = execute(order_file)
                self.assertEqual(receipt_res_blocked["final_status"], "BLOCKED")
                self.assertEqual(receipt_res_blocked["reason"], "THERMAL_PREFLIGHT_BLOCKED")
                _assert_priming_metadata(receipt_res_blocked.get("priming"))
                self.assertTrue(path_res.is_file())

            # 4. Model preflight BLOCKED path
            goose_order = dict(base_order, harness="goose")
            order_file.write_text(json.dumps(goose_order), encoding="utf-8")
            with patch("supervisor.run_job.resource_check", return_value={"ok": True, "reason": "OK"}):
                with patch("supervisor.run_job.preflight", return_value={"ok": False, "reason": "MODEL_PREFLIGHT_BLOCKED"}):
                    receipt_model_blocked, path_model = execute(order_file)
                    self.assertEqual(receipt_model_blocked["final_status"], "BLOCKED")
                    self.assertEqual(receipt_model_blocked["reason"], "MODEL_PREFLIGHT_BLOCKED")
                    _assert_priming_metadata(receipt_model_blocked.get("priming"))
                    self.assertTrue(path_model.is_file())

            # 5. Launch error path
            order_file.write_text(json.dumps(base_order), encoding="utf-8")
            with patch("supervisor.run_job.launch", side_effect=OSError("harness launch failed")):
                receipt_launch_err, path_launch = execute(order_file)
                self.assertEqual(receipt_launch_err["final_status"], "FAIL")
                self.assertEqual(receipt_launch_err["reason"], "LAUNCH_ERROR")
                _assert_priming_metadata(receipt_launch_err.get("priming"))
                self.assertTrue(path_launch.is_file())

            # 6. Retry attempt path
            retry_order = dict(base_order, max_attempts=2)
            order_file.write_text(json.dumps(retry_order), encoding="utf-8")
            (tmp_path / "result.txt").write_text("OK", encoding="utf-8")
            receipt_retry, path_retry = execute(order_file)
            self.assertEqual(receipt_retry["final_status"], "PASS")
            _assert_priming_metadata(receipt_retry.get("priming"))
            self.assertTrue(path_retry.is_file())

            # 7. Coder fallback aggregate receipt
            coder_order = dict(base_order, harness="coder", model="josie-qual-ornith-1.5-9b-q6")
            order_file.write_text(json.dumps(coder_order), encoding="utf-8")
            primary_rec = {
                "schema_version": "1", "supervisor_version": "1.0", "job_id": coder_order["job_id"],
                "final_status": "FAIL", "reason": "FAIL_TIMEOUT", "harness": "goose",
                "priming": {
                    "used": True, "bundle_hash": bundle.bundle_hash,
                    "manifest_hash": bundle.manifest_hash, "is_empty": False,
                    "source_ids": list(bundle.source_ids), "schema_version": PRIMING_SCHEMA_VERSION,
                    "sources": [],
                },
            }
            fallback_rec = {
                "schema_version": "1", "supervisor_version": "1.0", "job_id": coder_order["job_id"],
                "final_status": "PASS", "reason": "PASS", "harness": "goose",
                "acceptance_results": [{"passed": True}], "changed_files": [],
                "priming": {
                    "used": True, "bundle_hash": bundle.bundle_hash,
                    "manifest_hash": bundle.manifest_hash, "is_empty": False,
                    "source_ids": list(bundle.source_ids), "schema_version": PRIMING_SCHEMA_VERSION,
                    "sources": [],
                },
            }
            fb_path = receipts_dir / "fb.json"
            with patch("supervisor.run_job._execute_one", side_effect=[(primary_rec, None), (fallback_rec, fb_path)]):
                receipt_coder, path_coder = execute(order_file)
                self.assertTrue(receipt_coder["fallback_occurred"])
                _assert_priming_metadata(receipt_coder.get("priming"))
                self.assertTrue(path_coder.is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)