from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.prompt_compiler import compile_prompt
from supervisor.prompt_contract import (
    CANONICAL_SECTIONS,
    DEFAULT_PROMPT_CONTRACT_VERSION,
    PROMPT_CONTRACT_VERSION_V1,
    PromptContract,
    parse_prompt_contract,
    render_prompt_contract,
    validate_contract_prompt,
    validate_contract_version,
)
from supervisor.work_order import ValidationError, WorkOrder


class PromptContractTests(unittest.TestCase):
    def setUp(self):
        self.workspace = ROOT

    def make_order_data(self, **overrides) -> dict:
        base = {
            "schema_version": "1",
            "job_id": f"job-{uuid.uuid4().hex[:8]}",
            "objective": "Implement prompt contract validation.",
            "workspace": str(self.workspace),
            "harness": "mock",
            "harness_executable": sys.executable,
            "model": "mock/exact",
            "allowed_changed_paths": ["supervisor/prompt_contract.py"],
            "timeout_seconds": 60,
            "max_attempts": 2,
            "acceptance": [{"type": "file_exists", "path": "supervisor/prompt_contract.py"}],
            "prompt_profile": "test",
            "receipt_destination": str(self.workspace / "receipts"),
        }
        base.update(overrides)
        return base

    def test_01_all_12_sections_exist_once_and_in_canonical_order(self):
        order = WorkOrder.validate(self.make_order_data())
        prompt = compile_prompt(order)

        sections = validate_contract_prompt(prompt)
        self.assertEqual(tuple(sections.keys()), CANONICAL_SECTIONS)

        for sec in CANONICAL_SECTIONS:
            self.assertIn(sec, sections)
            self.assertTrue(len(sections[sec]) > 0, f"Section {sec} should not be empty")

        for sec in CANONICAL_SECTIONS:
            lines = [line.strip() for line in prompt.splitlines() if line.strip() == sec]
            self.assertEqual(len(lines), 1, f"Header {sec} must appear exactly once as a standalone line")

        # Verify canonical ordering in the rendered prompt
        header_positions = [prompt.index(f"\n{sec}\n") if f"\n{sec}\n" in prompt else prompt.index(f"{sec}\n") for sec in CANONICAL_SECTIONS]
        self.assertEqual(header_positions, sorted(header_positions), "Section headers must appear in canonical order")

    def test_02_requires_modification_false_does_not_claim_write_is_mandatory(self):
        order = WorkOrder.validate(self.make_order_data(requires_modification=False))
        prompt = compile_prompt(order)
        sections = validate_contract_prompt(prompt)

        execution_sec = sections["EXECUTION"]
        self.assertNotIn("This job requires a file modification", execution_sec)
        self.assertIn("This job does not require a file modification", execution_sec)

        # Also verify retry prompt when requires_modification=False
        retry_prompt = compile_prompt(order, retry=True)
        self.assertNotIn("completing the required modification", retry_prompt)
        self.assertIn("satisfying the acceptance criteria", retry_prompt)

    def test_03_requires_modification_true_preserves_strong_modification_instruction(self):
        order = WorkOrder.validate(self.make_order_data(requires_modification=True))
        prompt = compile_prompt(order)
        sections = validate_contract_prompt(prompt)

        execution_sec = sections["EXECUTION"]
        expected = (
            "This job requires a file modification. Do not stop until an authorized target was edited "
            "or a genuine blocker was discovered and explicitly reported."
        )
        self.assertIn(expected, execution_sec)

        # Verify retry prompt when requires_modification=True
        retry_prompt = compile_prompt(order, retry=True)
        self.assertIn("completing the required modification", retry_prompt)

    def test_04_every_acceptance_item_is_rendered(self):
        acceptance_checks = [
            {"type": "command", "argv": ["python", "-m", "unittest", "discover", "-v"]},
            {"type": "command", "argv": ["check-status", "--detail"], "expected_exit_code": 1},
            {"type": "file_exists", "path": "supervisor/prompt_contract.py"},
            {"type": "file_exact", "path": "supervisor/version.txt", "content": "1.0"},
            {"type": "changed_paths"},
            {"type": "no_unexpected_files"},
        ]
        order = WorkOrder.validate(self.make_order_data(acceptance=acceptance_checks))
        prompt = compile_prompt(order)
        sections = validate_contract_prompt(prompt)
        acceptance_sec = sections["ACCEPTANCE"]

        self.assertIn("python -m unittest discover -v", acceptance_sec)
        self.assertIn("check-status --detail", acceptance_sec)
        self.assertIn("exit code 1", acceptance_sec)
        self.assertIn("File exists: supervisor/prompt_contract.py", acceptance_sec)
        self.assertIn("File exact match: supervisor/version.txt", acceptance_sec)
        self.assertIn("Only authorized changed paths are modified", acceptance_sec)
        self.assertIn("No unexpected files created in workspace", acceptance_sec)

    def test_05_retrieved_evidence_remains_bounded(self):
        # Create 10 evidence items, one of which has a huge excerpt
        evidence = [
            {"evidence_id": f"doc-{i}", "excerpt": f"Short evidence {i}."}
            for i in range(1, 11)
        ]
        evidence[0]["excerpt"] = "A" * 3000

        order = WorkOrder.validate(self.make_order_data(retrieved_evidence=evidence))
        prompt = compile_prompt(order)
        sections = validate_contract_prompt(prompt)
        resource_sec = sections["RESOURCE RULES"]

        # Only at most 5 items should be included
        self.assertIn("[doc-1]", resource_sec)
        self.assertIn("[doc-5]", resource_sec)
        self.assertNotIn("[doc-6]", resource_sec)
        self.assertNotIn("[doc-10]", resource_sec)

        # Long excerpt should be capped at 1200 characters
        self.assertNotIn("A" * 1201, resource_sec)
        self.assertIn("A" * 1200, resource_sec)

    def test_06_targeted_worker_failure_guidance_can_be_inserted(self):
        failure_modes = [
            "Do not stop after only inspecting files without editing.",
            "Do not introduce dependencies outside standard library.",
        ]
        order = WorkOrder.validate(self.make_order_data(worker_failure_modes=failure_modes))
        prompt = compile_prompt(order)
        sections = validate_contract_prompt(prompt)
        guards_sec = sections["FAILURE GUARDS"]

        self.assertIn("Known worker failure modes to avoid:", guards_sec)
        for mode in failure_modes:
            self.assertIn(mode, guards_sec)

    def test_07_unsupported_prompt_contract_versions_fail_validation(self):
        # WorkOrder validation rejects unsupported version
        for bad_version in ("2.0", "0.9", "v1", "", "   "):
            with self.assertRaises(ValidationError):
                WorkOrder.validate(self.make_order_data(prompt_contract_version=bad_version))

        # Direct prompt contract version validator also rejects
        with self.assertRaises(ValueError):
            validate_contract_version("2.0")
        with self.assertRaises(ValueError):
            validate_contract_version("")

    def test_08_backward_compatibility_defaults_to_v1(self):
        raw = self.make_order_data()
        self.assertNotIn("prompt_contract_version", raw)
        order = WorkOrder.validate(raw)

        self.assertEqual(order.prompt_contract_version, PROMPT_CONTRACT_VERSION_V1)
        self.assertEqual(order.raw["prompt_contract_version"], DEFAULT_PROMPT_CONTRACT_VERSION)

        prompt = compile_prompt(order)
        sections = validate_contract_prompt(prompt)
        self.assertEqual(tuple(sections.keys()), CANONICAL_SECTIONS)

    def test_09_prompt_contract_parsing_detects_malformed_prompts(self):
        valid_sections = {sec: f"Content for {sec}" for sec in CANONICAL_SECTIONS}
        rendered = render_prompt_contract(valid_sections)
        self.assertEqual(tuple(validate_contract_prompt(rendered).keys()), CANONICAL_SECTIONS)

        # Missing section
        missing_sections = dict(valid_sections)
        del missing_sections["RECEIPTS"]
        with self.assertRaises(ValueError) as cm:
            render_prompt_contract(missing_sections)
        self.assertIn("RECEIPTS", str(cm.exception))

        rendered_missing = "\n\n".join(f"{k}\n{v}" for k, v in missing_sections.items())
        with self.assertRaises(ValueError) as cm:
            validate_contract_prompt(rendered_missing)
        self.assertIn("RECEIPTS", str(cm.exception))

        # Duplicate section
        dup_text = f"ROLE\nDuplicate role\n\n{rendered}"
        with self.assertRaises(ValueError) as cm:
            validate_contract_prompt(dup_text)
        self.assertIn("Duplicate", str(cm.exception))

        # Sections out of canonical order
        shuffled_blocks = [f"{sec}\n{valid_sections[sec]}" for sec in reversed(CANONICAL_SECTIONS)]
        shuffled_prompt = "\n\n".join(shuffled_blocks)
        with self.assertRaises(ValueError) as cm:
            validate_contract_prompt(shuffled_prompt)
        self.assertIn("canonical order", str(cm.exception))

    def test_10_retry_notice_preserves_canonical_contract(self):
        order = WorkOrder.validate(self.make_order_data(requires_modification=True))
        retry_prompt = compile_prompt(order, retry=True)

        parsed = parse_prompt_contract(retry_prompt)
        self.assertIn("__preamble__", parsed)
        self.assertIn("Your previous attempt stopped", parsed["__preamble__"])
        for sec in CANONICAL_SECTIONS:
            self.assertIn(sec, parsed)

    def test_11_resource_rules_and_receipt_instructions(self):
        order = WorkOrder.validate(self.make_order_data(
            resource_rules=["Only local CPU inference permitted.", "Memory bound 4GB."],
            receipt_instructions="Record hash of outputs to verifier.",
        ))
        prompt = compile_prompt(order)
        sections = validate_contract_prompt(prompt)

        # RESOURCE RULES
        resource_sec = sections["RESOURCE RULES"]
        self.assertIn("Local resources only. Do not use paid/cloud providers or download models.", resource_sec)
        self.assertIn("Only local CPU inference permitted.", resource_sec)
        self.assertIn("Memory bound 4GB.", resource_sec)

        # RECEIPTS
        receipts_sec = sections["RECEIPTS"]
        self.assertIn("The Supervisor executes acceptance and owns authoritative terminal status.", receipts_sec)
        self.assertIn("Record hash of outputs to verifier.", receipts_sec)

    def test_12_prompt_contract_class_interface(self):
        valid_sections = {sec: f"Content for {sec}" for sec in CANONICAL_SECTIONS}
        rendered = PromptContract.render(valid_sections)
        parsed = PromptContract.validate(rendered)
        self.assertEqual(tuple(parsed.keys()), CANONICAL_SECTIONS)
        self.assertEqual(PromptContract.version, "1.0")


if __name__ == "__main__":
    unittest.main(verbosity=2)