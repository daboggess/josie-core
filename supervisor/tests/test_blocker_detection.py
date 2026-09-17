from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from supervisor.run_job import detect_blocker, event_activity


class BlockerDetectionTests(unittest.TestCase):
    def test_01_blocked_none_inline_is_not_blocked(self):
        text = ["Blocked: none", "Status: active"]
        self.assertFalse(detect_blocker(text))

    def test_02_blocked_none_parenthetical_is_not_blocked(self):
        text = [
            "### Work State",
            "### Completed",
            "- (none)",
            "",
            "### Blocked",
            "- (none)",
            "",
            "## Next Move",
            "1. Retry editing the target file.",
        ]
        self.assertFalse(detect_blocker(text))

    def test_03_empty_blocked_section_is_not_blocked(self):
        text = [
            "### Blocked",
            "",
            "### Next Steps",
            "1. Inspect the codebase.",
        ]
        self.assertFalse(detect_blocker(text))

    def test_04_trivial_variations_are_not_blocked(self):
        for trivial in (
            "None", "none.", "- none", "* (none)", "- (none)", "- \"(none)\"",
            "- '(none)'", "\"(none)\"", "'none'", "N/A", "na", "nil",
            "no blockers", "false", ""
        ):
            text = [f"### Blockers\n{trivial}\n\n### Work Done\nInspected files."]
            self.assertFalse(detect_blocker(text), f"Failed for trivial value: {trivial}")

    def test_05_real_blocker_content_is_blocked(self):
        text = [
            "### Blocked",
            "- The failed `edit` operation due to the `oldString` not matching exactly in the file.",
            "",
            "## Next Move",
            "1. Re-examine the file.",
        ]
        self.assertTrue(detect_blocker(text))

    def test_06_inline_real_blocker_is_blocked(self):
        text = ["Blocked: missing dependency `requests` in runtime environment."]
        self.assertTrue(detect_blocker(text))

    def test_07_explicit_cannot_proceed_is_blocked(self):
        text = [
            "I cannot proceed because the required database port 5432 is unreachable.",
        ]
        self.assertTrue(detect_blocker(text))

    def test_08_explicit_unable_to_proceed_is_blocked(self):
        text = [
            "Unable to proceed due to permission denial on read-only configuration file.",
        ]
        self.assertTrue(detect_blocker(text))

    def test_09_casual_blocked_word_is_not_blocked(self):
        text = [
            "We unblocked the build pipeline and verified that the test suite runs cleanly.",
            "All checks passed without error.",
        ]
        self.assertFalse(detect_blocker(text))

    def test_10_negative_cannot_proceed_context_is_not_blocked(self):
        text = [
            "Do not stop and do not say cannot proceed until tools are used.",
            "Files inspected successfully.",
        ]
        self.assertFalse(detect_blocker(text))

    def test_11_event_activity_reads_log_and_detects_blocker_accurately(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".log") as handle:
            handle.write('{"type": "tool_use", "part": {"tool": "read", "state": {"status": "completed"}}}\n')
            handle.write('{"type": "text", "part": {"text": "### Blocked\\n- (none)\\n"}}\n')
            log_path = Path(handle.name)

        try:
            tools, blocker, events = event_activity(log_path)
            self.assertIn("read", tools)
            self.assertFalse(blocker, "Expected blocker to be False for template '### Blocked\\n- (none)'")
        finally:
            log_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
