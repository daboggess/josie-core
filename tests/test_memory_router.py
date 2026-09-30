"""Unit and integration tests for Josie Memory Relevance Router.

Covers:
- Matrix cases A through J
- MemoryRelevance contract invariants (fail-closed, threshold, category filtering)
- Resolution precedence (explicit -> task_class -> path prefix -> router -> empty)
- Real recall and negative control task queries
- Candidate and rejected claim exclusion
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from josie.candidate_claims import ALLOWED_CLAIM_CATEGORIES
from josie.knowledge import seed_canonical_knowledge
from josie.memory_router import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    ROUTER_VERSION,
    MemoryRelevance,
    route_memory_relevance,
)
from josie.storage import LocalStore
from supervisor.remote_adapter import (
    evaluate_task_memory_relevance,
    parse_remote_job,
    resolve_task_categories,
)
from supervisor.run_job import _priming_summary
from supervisor.work_order import WorkOrder


class MemoryRouterContractTests(unittest.TestCase):
    """Test MemoryRelevance dataclass and contract invariants."""

    def test_relevance_valid_initialization(self) -> None:
        rel = MemoryRelevance(
            memory_needed=True,
            categories=("profile", "hardware"),
            confidence=0.95,
            reason="test reason",
        )
        self.assertTrue(rel.memory_needed)
        self.assertEqual(rel.categories, ("profile", "hardware"))
        self.assertEqual(rel.confidence, 0.95)
        self.assertEqual(rel.router_version, ROUTER_VERSION)

        d = rel.to_dict()
        self.assertTrue(d["memory_needed"])
        self.assertEqual(d["categories"], ["profile", "hardware"])
        self.assertEqual(d["confidence"], 0.95)
        self.assertEqual(d["reason"], "test reason")
        self.assertEqual(d["router_version"], ROUTER_VERSION)

    def test_relevance_filters_unknown_categories(self) -> None:
        rel = MemoryRelevance(
            memory_needed=True,
            categories=("profile", "nonexistent_bogus_category"),
            confidence=0.90,
            reason="test unknown category",
        )
        self.assertTrue(rel.memory_needed)
        self.assertEqual(rel.categories, ("profile",))

    def test_relevance_fails_closed_below_confidence_threshold(self) -> None:
        # Confidence < 0.70 MUST fail closed to memory_needed=False and empty categories
        rel = MemoryRelevance(
            memory_needed=True,
            categories=("profile",),
            confidence=0.69,
            reason="insufficient confidence",
        )
        self.assertFalse(rel.memory_needed)
        self.assertEqual(rel.categories, ())

    def test_relevance_fails_closed_on_empty_categories(self) -> None:
        rel = MemoryRelevance(
            memory_needed=True,
            categories=(),
            confidence=0.95,
            reason="no categories",
        )
        self.assertFalse(rel.memory_needed)
        self.assertEqual(rel.categories, ())

    def test_relevance_invalid_confidence_raises(self) -> None:
        with self.assertRaises(ValueError):
            MemoryRelevance(
                memory_needed=True,
                categories=("profile",),
                confidence=1.5,
                reason="bad confidence",
            )
        with self.assertRaises(ValueError):
            MemoryRelevance(
                memory_needed=True,
                categories=("profile",),
                confidence=-0.1,
                reason="negative confidence",
            )


class MemoryRouterMatrixTests(unittest.TestCase):
    """Test required matrix cases A through J and safety invariants."""

    def test_case_a_direct_credential_question(self) -> None:
        task = "What technical certifications or server experience do I have?"
        res = route_memory_relevance(task, use_model_fallback=False)
        self.assertTrue(res.memory_needed)
        self.assertIn("profile", res.categories)
        self.assertGreaterEqual(res.confidence, DEFAULT_CONFIDENCE_THRESHOLD)

    def test_case_b_hardware_inventory_question(self) -> None:
        task = "What hardware do I already own for Josie?"
        res = route_memory_relevance(task, use_model_fallback=False)
        self.assertTrue(res.memory_needed)
        self.assertIn("hardware", res.categories)
        self.assertGreaterEqual(res.confidence, DEFAULT_CONFIDENCE_THRESHOLD)

    def test_case_c_preference_budget_question(self) -> None:
        task = "What is my preferred strategy for getting the cheapest hardware for Josie?"
        res = route_memory_relevance(task, use_model_fallback=False)
        self.assertTrue(res.memory_needed)
        self.assertIn("preference", res.categories)
        self.assertGreaterEqual(res.confidence, DEFAULT_CONFIDENCE_THRESHOLD)

    def test_case_d_past_decision_question(self) -> None:
        task = "What did we decide about the model family for the worker?"
        res = route_memory_relevance(task, use_model_fallback=False)
        self.assertTrue(res.memory_needed)
        self.assertIn("decision", res.categories)
        self.assertGreaterEqual(res.confidence, DEFAULT_CONFIDENCE_THRESHOLD)

    def test_case_e_architectural_question(self) -> None:
        task = "Explain the relationship between Goose and OpenCode in Josie's architecture."
        res = route_memory_relevance(task, use_model_fallback=False)
        self.assertTrue(res.memory_needed)
        self.assertIn("architecture", res.categories)
        self.assertGreaterEqual(res.confidence, DEFAULT_CONFIDENCE_THRESHOLD)

    def test_case_f_operational_question(self) -> None:
        task = "How do we handle destructive actions?"
        res = route_memory_relevance(task, use_model_fallback=False)
        self.assertTrue(res.memory_needed)
        self.assertTrue(any(c in res.categories for c in ("procedure", "constraint")))
        self.assertGreaterEqual(res.confidence, DEFAULT_CONFIDENCE_THRESHOLD)

    def test_case_g_irrelevant_coding_task(self) -> None:
        task = "Write a Python function to compute the Fibonacci sequence."
        res = route_memory_relevance(task, use_model_fallback=False)
        self.assertFalse(res.memory_needed)
        self.assertEqual(res.categories, ())

    def test_case_h_negative_control_string_literal(self) -> None:
        task = "Write a script that parses a log file for the word 'certification'."
        res = route_memory_relevance(task, use_model_fallback=False)
        self.assertFalse(res.memory_needed)
        self.assertEqual(res.categories, ())

    def test_case_i_conversational_ambiguity_fails_closed(self) -> None:
        task = "Tell me about that thing we discussed yesterday."
        res = route_memory_relevance(task, use_model_fallback=False)
        self.assertFalse(res.memory_needed)
        self.assertEqual(res.categories, ())

    def test_case_j_explicit_category_override(self) -> None:
        retrieval = {"priming_categories": ["identity"]}
        cats = resolve_task_categories(
            task="What technical certifications or server experience do I have?",
            allowed_changes=["result.txt"],
            retrieval_context=retrieval,
        )
        self.assertEqual(cats, ("identity",))


class FrontdoorRoutingPrecedenceTests(unittest.TestCase):
    """Test precedence: explicit -> task_class -> path prefix -> router -> empty."""

    def test_precedence_1_explicit_priming_categories(self) -> None:
        cats = resolve_task_categories(
            task="What hardware do I already own for Josie?",
            retrieval_context={"priming_categories": ["architecture"]},
        )
        self.assertEqual(cats, ("architecture",))

    def test_precedence_2_task_class_route(self) -> None:
        cats = resolve_task_categories(
            task="What hardware do I already own for Josie?",
            retrieval_context={"task_class": "architecture"},
        )
        self.assertEqual(cats, ("architecture", "procedure"))

    def test_precedence_3_changed_path_prefix(self) -> None:
        cats = resolve_task_categories(
            task="Perform routine maintenance",
            allowed_changes=["supervisor/verifier.py"],
        )
        self.assertEqual(cats, ("architecture", "procedure"))

    def test_precedence_4_automatic_router_fallback(self) -> None:
        cats = resolve_task_categories(
            task="What technical certification or server experience do I have that's relevant to working on Josie?",
            allowed_changes=["result.txt"],
        )
        self.assertEqual(cats, ("profile",))

    def test_precedence_5_fail_closed_empty(self) -> None:
        cats = resolve_task_categories(
            task="Write a Python function that reverses a string.",
            allowed_changes=["result.txt"],
        )
        self.assertEqual(cats, ())


class FrontdoorWorkOrderAuditTests(unittest.TestCase):
    """Test WorkOrder and receipt audit metadata generation."""

    def setUp(self) -> None:
        temp_root = Path(__file__).resolve().parent.parent / "data" / "tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(dir=temp_root)
        self.base = Path(self.temp_dir.name)
        self.project_root = self.base / "josie"
        self.project_root.mkdir()
        self.workspace = self.base / "repo"
        self.workspace.mkdir()

        self.db_path = self.project_root / "data" / "josie.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.store = LocalStore(self.db_path)
        seed_canonical_knowledge(self.store)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_frontdoor_records_complete_router_audit(self) -> None:
        task_text = "What technical certifications or server experience do I have?"
        request_text = "\n".join((
            f"Workspace: {self.workspace}",
            "Task:",
            task_text,
            "Allowed changes:",
            "result.txt",
            "Acceptance:",
            "command: python -c pass",
        ))

        order, path = parse_remote_job(
            request_text,
            request_id="test-router-audit-001",
            project_root=self.project_root,
            store=self.store,
        )

        self.assertTrue(path.is_file())
        validated = WorkOrder.validate(order)

        mr = order.get("memory_router")
        self.assertIsNotNone(mr)
        self.assertEqual(mr["router_version"], ROUTER_VERSION)
        self.assertTrue(mr["memory_needed"])
        self.assertIn("profile", mr["selected_categories"])
        self.assertGreaterEqual(mr["confidence"], 0.70)
        self.assertTrue(len(mr["reason"]) > 0)
        self.assertTrue(len(mr["task_hash"]) == 64)

        # Receipt summary check
        summary = _priming_summary(validated)
        self.assertIn("router", summary)
        self.assertEqual(summary["router"]["router_version"], ROUTER_VERSION)
        self.assertEqual(summary["router"]["selected_categories"], ["profile"])


if __name__ == "__main__":
    unittest.main()
