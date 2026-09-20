"""End-to-end integration tests for automatic front-door canonical knowledge priming.

Proves:
1. Qualifying task enters the normal front-door builder (parse_remote_job).
2. The front door queries live-compatible canonical knowledge from SQLite store.
3. It creates a PrimingManifest without a manual evidence dump.
4. It receives relevant active canonical records.
5. It assembles a deterministic PrimingBundle.
6. It applies the bundle to WorkOrder.
7. retrieved_evidence contains bounded compact canonical evidence.
8. priming_context contains bundle/provenance metadata.
9. Prompt Contract receives compact evidence only.
10. rejected/superseded knowledge is absent.
11. irrelevant categories are absent.
12. receipt retains priming bundle/hash/source IDs without source bodies.

Uses an isolated temporary SQLite database, NEVER the live database.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from josie.storage import LocalStore
from josie.knowledge import (
    BOOTSTRAP_KNOWLEDGE_SEEDS,
    bootstrap_canonical_knowledge,
    load_knowledge_from_store,
    seed_canonical_knowledge,
)
from supervisor.remote_adapter import (
    parse_remote_job,
    resolve_task_categories,
)
from supervisor.prompt_compiler import compile_prompt
from supervisor.run_job import _priming_summary
from supervisor.work_order import WorkOrder


class FrontdoorPrimingTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_root = Path(__file__).resolve().parent.parent / "data" / "tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(dir=temp_root)
        self.base = Path(self.temp_dir.name)
        self.project_root = self.base / "josie"
        self.project_root.mkdir()
        self.workspace = self.base / "repo"
        self.workspace.mkdir()

        # Isolated temporary SQLite database
        self.db_path = self.project_root / "data" / "josie.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.store = LocalStore(self.db_path)

        # Seed the temporary database with canonical bootstrap records
        seed_canonical_knowledge(self.store)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_01_qualifying_arch_supervisor_task_receives_automatic_priming(self) -> None:
        """Requirement 1-12: Qualifying task automatically receives bounded canonical priming."""
        request_text = "\n".join((
            f"Workspace: {self.workspace}",
            "Task:",
            "Update the supervisor prompt compiler to support bounded priming.",
            "Allowed changes:",
            "supervisor/prompt_compiler.py",
            "Acceptance:",
            "command: python -c pass",
        ))

        order, path = parse_remote_job(
            request_text,
            request_id="test-frontdoor-001",
            project_root=self.project_root,
            store=self.store,
        )

        self.assertTrue(path.is_file())
        validated = WorkOrder.validate(order)

        # Item 8: priming_context contains bundle/provenance metadata
        ctx = order.get("priming_context")
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx["schema_version"], "1.0")
        self.assertFalse(ctx["is_empty"])
        self.assertEqual(ctx["item_count"], 3)
        self.assertIn("bundle_hash", ctx)
        self.assertIn("manifest_hash", ctx)
        self.assertEqual(order["priming_bundle_hash"], ctx["bundle_hash"])

        # Item 4 & 5: Source IDs match the active architecture/procedure records in deterministic sort order
        source_ids = list(ctx["source_ids"])
        expected_ids = [
            "arch:identity-above-models",
            "arch:supervisor-worker-separation",
            "procedure:destructive-action-gate",
        ]
        self.assertEqual(source_ids, expected_ids)

        # Item 10: rejected knowledge is absent
        self.assertNotIn("witness:genesis-clm-012-bernie-values", source_ids)

        # Item 11: irrelevant categories (identity without authority request) absent
        self.assertNotIn("identity:dustin-authority", source_ids)

        # Item 7: retrieved_evidence contains bounded compact canonical evidence
        evidence = order.get("retrieved_evidence")
        self.assertIsInstance(evidence, list)
        self.assertEqual(len(evidence), 3)
        for ev in evidence:
            self.assertIn(ev["evidence_id"], expected_ids)
            self.assertTrue(len(ev["excerpt"]) > 0)
            self.assertTrue(len(ev.get("source_reference") or ev.get("source") or "") > 0)

        # Item 9: Prompt Contract receives compact evidence only (under RESOURCE RULES)
        prompt = compile_prompt(validated)
        self.assertIn("RESOURCE RULES", prompt)
        self.assertIn("[arch:identity-above-models]", prompt)
        self.assertIn("[arch:supervisor-worker-separation]", prompt)
        self.assertIn("[procedure:destructive-action-gate]", prompt)
        self.assertNotIn("witness:genesis-clm-012-bernie-values", prompt)
        self.assertNotIn("identity:dustin-authority", prompt)
        self.assertNotIn("memory_claims", prompt)  # No internal DB schema leak

        # Item 12: receipt retains priming bundle/hash/source IDs without source bodies
        receipt_summary = _priming_summary(validated)
        self.assertTrue(receipt_summary["used"])
        self.assertFalse(receipt_summary["is_empty"])
        self.assertEqual(receipt_summary["bundle_hash"], ctx["bundle_hash"])
        self.assertEqual(receipt_summary["manifest_hash"], ctx["manifest_hash"])
        self.assertEqual(receipt_summary["source_ids"], expected_ids)
        self.assertEqual(len(receipt_summary["sources"]), 3)
        for s in receipt_summary["sources"]:
            self.assertIn("item_id", s)
            self.assertIn("category", s)
            self.assertIn("source_kind", s)
            self.assertIn("source_reference", s)
            self.assertIn("item_hash", s)
            self.assertNotIn("content", s)  # No full source body in receipt
            self.assertNotIn("content_excerpt", s)

    def test_02_existing_retrieval_preserved_alongside_canonical_priming(self) -> None:
        """Requirement: Canonical priming supplements existing retrieval without replacing it."""
        request_text = "\n".join((
            f"Workspace: {self.workspace}",
            "Task:",
            "Update supervisor verifier for bounded execution.",
            "Allowed changes:",
            "supervisor/verifier.py",
            "Acceptance:",
            "command: python -c pass",
        ))

        retrieval = {
            "triggered": True,
            "packet": "verifier existing spec",
            "evidence": [
                {"evidence_id": "spec:verifier-rules", "excerpt": "verifier must check path scopes"}
            ],
        }

        order, _ = parse_remote_job(
            request_text,
            request_id="test-frontdoor-002",
            project_root=self.project_root,
            retrieval_context=retrieval,
            store=self.store,
        )

        evidence = order.get("retrieved_evidence")
        self.assertIsInstance(evidence, list)
        self.assertEqual(len(evidence), 4)

        # First 3 items are priming evidence (priority) in deterministic sort order
        priming_ids = [ev["evidence_id"] for ev in evidence[:3]]
        self.assertEqual(priming_ids, [
            "arch:identity-above-models",
            "arch:supervisor-worker-separation",
            "procedure:destructive-action-gate",
        ])

        # Fourth item is preserved existing retrieved evidence
        self.assertEqual(evidence[3]["evidence_id"], "spec:verifier-rules")
        self.assertEqual(evidence[3]["excerpt"], "verifier must check path scopes")

        prompt = compile_prompt(WorkOrder.validate(order))
        self.assertIn("[spec:verifier-rules] verifier must check path scopes", prompt)
        self.assertIn("[arch:supervisor-worker-separation]", prompt)

    def test_03_generic_coding_task_produces_empty_priming_bundle(self) -> None:
        """Requirement: Non-qualifying generic task produces valid empty priming."""
        request_text = "\n".join((
            f"Workspace: {self.workspace}",
            "Task:",
            "Modify result.txt.",
            "Allowed changes:",
            "result.txt",
            "Acceptance:",
            "command: python -c pass",
        ))

        order, _ = parse_remote_job(
            request_text,
            request_id="test-frontdoor-003",
            project_root=self.project_root,
            store=self.store,
        )

        ctx = order.get("priming_context")
        self.assertIsNotNone(ctx)
        self.assertTrue(ctx["is_empty"])
        self.assertEqual(ctx["item_count"], 0)
        self.assertEqual(ctx["source_ids"], [])
        self.assertEqual(order["retrieved_evidence"], [])

        # Prompt compiles cleanly with no priming evidence
        prompt = compile_prompt(WorkOrder.validate(order))
        self.assertIn("RESOURCE RULES", prompt)
        self.assertNotIn("[arch:", prompt)

    def test_04_authority_governance_task_resolves_identity_and_excludes_rejected(self) -> None:
        """Requirement: Authority tasks resolve identity; rejected witness claim is excluded."""
        request_text = "\n".join((
            f"Workspace: {self.workspace}",
            "Task:",
            "Review Dustin authority and governance policies.",
            "Allowed changes:",
            "docs/governance/RATIFICATION.md",
            "Acceptance:",
            "command: python -c pass",
        ))

        order, _ = parse_remote_job(
            request_text,
            request_id="test-frontdoor-004",
            project_root=self.project_root,
            store=self.store,
        )

        ctx = order.get("priming_context")
        self.assertFalse(ctx["is_empty"])
        source_ids = list(ctx["source_ids"])

        # Identity claim is included
        self.assertIn("identity:dustin-authority", source_ids)

        # Rejected witness claim is strictly excluded
        self.assertNotIn("witness:genesis-clm-012-bernie-values", source_ids)

        # Destructive action procedure is included
        self.assertIn("procedure:destructive-action-gate", source_ids)

    def test_05_live_database_remains_isolated_from_test_runs(self) -> None:
        r"""Safety check: Live database D:\Josie\data\josie.db is never touched or mutated by tests."""
        live_db = Path(__file__).resolve().parent.parent / "data" / "josie.db"
        if not live_db.exists():
            # In fresh clone or CI, running tests must not spontaneously create data/josie.db
            self.assertFalse(live_db.exists(), "Running tests must not spontaneously create live data/josie.db")
            return

        def _get_counts() -> tuple[int, int, int]:
            conn = sqlite3.connect(f"file:{live_db.as_posix()}?mode=ro", uri=True)
            try:
                cur = conn.cursor()
                entities = cur.execute("SELECT count(*) FROM entities").fetchone()[0]
                claims = cur.execute("SELECT count(*) FROM memory_claims").fetchone()[0]
                evidence = cur.execute("SELECT count(*) FROM claim_evidence").fetchone()[0]
                return entities, claims, evidence
            finally:
                conn.close()

        before = _get_counts()

        # Run front door parsing with temporary store
        request_text = "\n".join((
            f"Workspace: {self.workspace}",
            "Task:",
            "Update supervisor remote adapter isolation.",
            "Allowed changes:",
            "supervisor/remote_adapter.py",
            "Acceptance:",
            "command: python -c pass",
        ))
        order, _ = parse_remote_job(
            request_text,
            request_id="test-isolation-check",
            project_root=self.project_root,
            store=self.store,
        )
        self.assertIsNotNone(order)

        after = _get_counts()
        self.assertEqual(before, after, "Live database counts were mutated during frontdoor priming run!")

    def test_06_structured_category_resolution_precedence(self) -> None:
        """Issue 2: Structured category resolution precedence (metadata -> task class -> paths -> empty)."""
        # 1. Explicit metadata in retrieval_context
        self.assertEqual(
            resolve_task_categories(
                task="any text",
                allowed_changes=["result.txt"],
                retrieval_context={"priming_categories": ["identity"]},
            ),
            ("identity",),
        )
        self.assertEqual(
            resolve_task_categories(
                task="any text",
                allowed_changes=["result.txt"],
                retrieval_context={"categories": ["procedure", "architecture"]},
            ),
            ("procedure", "architecture"),
        )

        # 2. Known route / task class metadata
        self.assertEqual(
            resolve_task_categories(
                task="any text",
                allowed_changes=["result.txt"],
                retrieval_context={"task_class": "architecture"},
            ),
            ("architecture", "procedure"),
        )
        self.assertEqual(
            resolve_task_categories(
                task="any text",
                allowed_changes=["result.txt"],
                retrieval_context={"operation": "governance"},
            ),
            ("identity", "procedure"),
        )

        # 3. Allowed changed-path prefixes
        self.assertEqual(
            resolve_task_categories(
                task="inspect and build",
                allowed_changes=["supervisor/verifier.py"],
            ),
            ("architecture", "procedure"),
        )
        self.assertEqual(
            resolve_task_categories(
                task="mission management update",
                allowed_changes=["mission_manager/manager.py"],
            ),
            ("architecture", "procedure"),
        )
        self.assertEqual(
            resolve_task_categories(
                task="update constitutional governance docs",
                allowed_changes=["docs/governance/RATIFICATION.md"],
            ),
            ("identity", "procedure"),
        )
        self.assertEqual(
            resolve_task_categories(
                task="update identity genesis doc",
                allowed_changes=["docs/identity/genesis/SESSION_001.md"],
            ),
            ("identity", "procedure"),
        )

        # 4. Empty when no structured signals match
        self.assertEqual(
            resolve_task_categories(
                task="calculate something",
                allowed_changes=["calc.py"],
            ),
            (),
        )

    def test_07_prose_keywords_do_not_trigger_priming(self) -> None:
        """Issue 2 / C: Generic task whose prose mentions supervisor/priming with allowed changes result.txt gets empty bundle."""
        request_text = "\n".join((
            f"Workspace: {self.workspace}",
            "Task:",
            "Do not touch supervisor architecture or authority priming rules. Summarize findings into result.txt.",
            "Allowed changes:",
            "result.txt",
            "Acceptance:",
            "command: python -c pass",
        ))

        order, _ = parse_remote_job(
            request_text,
            request_id="test-frontdoor-prose-kw",
            project_root=self.project_root,
            store=self.store,
        )

        ctx = order.get("priming_context")
        self.assertIsNotNone(ctx)
        self.assertTrue(ctx["is_empty"])
        self.assertEqual(ctx["item_count"], 0)
        self.assertEqual(ctx["source_ids"], [])
        self.assertEqual(order["retrieved_evidence"], [])

        # Prompt contract receives NO priming evidence
        prompt = compile_prompt(WorkOrder.validate(order))
        self.assertIn("RESOURCE RULES", prompt)
        self.assertNotIn("[arch:", prompt)
        self.assertNotIn("[identity:", prompt)

    def test_08_unrelated_coding_task_gets_empty_bundle(self) -> None:
        """Issue 2 / D: Unrelated coding task (e.g. calc.py) gets empty priming bundle."""
        request_text = "\n".join((
            f"Workspace: {self.workspace}",
            "Task:",
            "Implement add function in calc.py.",
            "Allowed changes:",
            "calc.py",
            "Acceptance:",
            "command: python -c pass",
        ))

        order, _ = parse_remote_job(
            request_text,
            request_id="test-frontdoor-unrelated",
            project_root=self.project_root,
            store=self.store,
        )

        ctx = order.get("priming_context")
        self.assertIsNotNone(ctx)
        self.assertTrue(ctx["is_empty"])
        self.assertEqual(ctx["item_count"], 0)
        self.assertEqual(ctx["source_ids"], [])
        self.assertEqual(order["retrieved_evidence"], [])

    def test_09_explicit_metadata_resolves_categories_and_excludes_rejected(self) -> None:
        """Issue 2 / A & E: Explicit metadata resolves requested categories; rejected claims remain excluded."""
        request_text = "\n".join((
            f"Workspace: {self.workspace}",
            "Task:",
            "Execute custom identity-primed check.",
            "Allowed changes:",
            "result.txt",
            "Acceptance:",
            "command: python -c pass",
        ))

        retrieval = {"priming_categories": ["identity"]}
        order, _ = parse_remote_job(
            request_text,
            request_id="test-frontdoor-explicit-meta",
            project_root=self.project_root,
            retrieval_context=retrieval,
            store=self.store,
        )

        ctx = order.get("priming_context")
        self.assertFalse(ctx["is_empty"])
        source_ids = list(ctx["source_ids"])
        self.assertEqual(source_ids, ["identity:dustin-authority"])
        self.assertNotIn("witness:genesis-clm-012-bernie-values", source_ids)

        prompt = compile_prompt(WorkOrder.validate(order))
        self.assertIn("[identity:dustin-authority]", prompt)
        self.assertNotIn("witness:genesis-clm-012-bernie-values", prompt)

    def test_10_idempotent_bootstrap_creates_no_additional_backup(self) -> None:
        """Issue 3: Identical second bootstrap creates no additional backup."""
        test_db = self.base / "idempotent_test.db"
        test_backup_dir = self.base / "backups"
        test_backup_dir.mkdir(parents=True, exist_ok=True)
        store = LocalStore(test_db)

        # 1. Initial bootstrap inserts records and creates pre-mutation backup
        res1 = bootstrap_canonical_knowledge(store, backup=True, backup_dir=test_backup_dir)
        self.assertEqual(res1["status"], "success")
        self.assertEqual(len(res1["inserted"]), len(BOOTSTRAP_KNOWLEDGE_SEEDS))
        self.assertIsNotNone(res1["backup_path"])
        backups1 = list(test_backup_dir.glob("*.db"))
        self.assertEqual(len(backups1), 1)

        # 2. Second identical bootstrap finds 0 records to insert
        res2 = bootstrap_canonical_knowledge(store, backup=True, backup_dir=test_backup_dir)
        self.assertEqual(res2["status"], "success")
        self.assertEqual(len(res2["inserted"]), 0)
        self.assertEqual(len(res2["unchanged"]), len(BOOTSTRAP_KNOWLEDGE_SEEDS))
        # backup_path must be None on idempotent run
        self.assertIsNone(res2["backup_path"])

        # No new backup file was created
        backups2 = list(test_backup_dir.glob("*.db"))
        self.assertEqual(len(backups2), 1)


if __name__ == "__main__":
    unittest.main()
