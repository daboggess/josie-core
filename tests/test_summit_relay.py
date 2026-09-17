import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from josie.summit_browser import (
    deliver_josie_http,
    initialize_profile,
    load_browser_config,
    run_direct,
)
from josie.summit_relay import (
    AcceptanceRelay,
    ReceiptLog,
    format_envelope,
    load_relay_config,
)


ROOT = Path(__file__).resolve().parents[1]


def result_for(action, *, ok=True, text="", code="", detail=""):
    return {
        "action_id": action["action_id"],
        "ok": ok,
        "assistant_text": text,
        "tab_id": 101,
        "page_url": f"https://example.invalid/{action['worker']}/conversation",
        "page_title": f"{action['worker']} designated conversation",
        "error_code": code,
        "error_detail": detail,
    }


class SummitRelayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.receipt_path = Path(self.temp.name) / "receipts.jsonl"
        self.config = load_relay_config(ROOT)
        self.relay = AcceptanceRelay(self.config, ReceiptLog(self.receipt_path))

    def events(self):
        return [json.loads(line) for line in self.receipt_path.read_text(encoding="utf-8").splitlines()]

    def test_config_is_narrow_and_bounded(self):
        self.assertEqual(self.config["max_exchange_rounds"], 3)
        self.assertEqual(set(self.config["providers"]), {"sophie", "bernie", "josie"})
        self.assertEqual(self.config["binding"], "127.0.0.1")

    def test_envelope_preserves_attribution_and_exact_content(self):
        message = format_envelope(
            from_worker="Sophie", round_number="1", source="ChatGPT",
            content="exact payload", maximum=100,
        )
        self.assertIn("FROM: SOPHIE\nVIA: JOSIE\nROUND: 1\nSOURCE: ChatGPT", message)
        self.assertIn("<BEGIN EXACT RELAY CONTENT>\nexact payload\n<END EXACT RELAY CONTENT>", message)
        self.assertNotIn("FROM: DUSTIN", message)

    def test_harmless_acceptance_is_exactly_bounded_and_completes(self):
        action1 = self.relay.next_action()
        self.assertEqual(action1["worker"], "sophie")
        self.relay.submit_result(result_for(
            action1, text="Sophie relay test: Please respond with exactly BERNIE_RELAY_OK."
        ))
        action2 = self.relay.next_action()
        self.assertEqual((action2["worker"], action2["round"]), ("bernie", "2"))
        self.assertIn("FROM: SOPHIE", action2["payload"])
        self.relay.submit_result(result_for(action2, text="BERNIE_RELAY_OK"))
        action3 = self.relay.next_action()
        self.assertEqual((action3["worker"], action3["round"]), ("sophie", "3"))
        self.assertIn("FROM: BERNIE", action3["payload"])
        self.relay.submit_result(result_for(action3, text="SOPHIE_RELAY_OK"))
        receipt = self.relay.next_action()
        self.assertEqual((receipt["worker"], receipt["round"]), ("josie", "RECEIPT"))
        report = self.relay.submit_result(result_for(receipt, text="Receipt acknowledged."))
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["stop_reason"], "bounded_exchange_complete")
        self.assertIsNone(self.relay.next_action())
        self.assertEqual(len(self.relay.actions), 4)
        self.assertEqual(sum(a.round_number in {"1", "2", "3"} for a in self.relay.actions), 3)

    def test_authentication_failure_stops_without_next_action(self):
        action = self.relay.next_action()
        report = self.relay.submit_result(result_for(
            action, ok=False, code="authentication_required", detail="ChatGPT requires sign-in."
        ))
        self.assertEqual(report["status"], "stopped")
        self.assertIn("authentication_required", report["stop_reason"])
        self.assertIsNone(self.relay.next_action())

    def test_exact_response_mismatch_stops(self):
        action = self.relay.next_action()
        report = self.relay.submit_result(result_for(action, text="extra plausible text"))
        self.assertEqual(report["status"], "stopped")
        self.assertEqual(report["stop_reason"], "expected_exact_mismatch")
        self.assertIsNone(self.relay.next_action())

    def test_receipts_are_append_only_metadata_and_hashes(self):
        action = self.relay.next_action()
        self.relay.submit_result(result_for(action, text="wrong"))
        events = self.events()
        self.assertEqual(events[0]["event"], "job_started")
        self.assertTrue(any(event["event"] == "send_dispatched" for event in events))
        rejection = next(event for event in events if event["event"] == "response_rejected")
        self.assertEqual(len(rejection["payload_sha256"]), 64)
        serialized = json.dumps(events)
        self.assertNotIn("extra plausible text", serialized)
        self.assertNotIn("FROM: DUSTIN", serialized)

    def test_direct_browser_config_uses_installed_chrome_and_no_extension(self):
        config = load_browser_config(ROOT)
        self.assertEqual(config["transport"], "direct_playwright")
        self.assertTrue(config["headless"])
        self.assertTrue(config["chrome_executable"].endswith("chrome.exe"))
        self.assertEqual(set(config["providers"]), {"sophie", "bernie"})
        self.assertEqual(config["josie_http"]["base_url"], "http://127.0.0.1:3000")
        self.assertEqual(config["josie_http"]["tool_ids"], [])
        serialized = json.dumps(config)
        self.assertNotIn("chrome-extension://", serialized)
        self.assertNotIn("8792", serialized)

    def test_profile_initialization_creates_only_dedicated_empty_directory(self):
        test_root = Path(self.temp.name)
        (test_root / "config").mkdir()
        config = json.loads((ROOT / "config" / "summit-browser.json").read_text(encoding="utf-8"))
        config["profile_directory"] = "data/private/test-profile"
        (test_root / "config" / "summit-browser.json").write_text(json.dumps(config), encoding="utf-8")
        path = initialize_profile(project_root=test_root)
        self.assertEqual(path, test_root / "data" / "private" / "test-profile")
        self.assertEqual(list(path.iterdir()), [])

    def test_direct_runner_reuses_bounded_state_machine(self):
        class FakeBrowser:
            def __init__(self, **_kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def authentication(self):
                return {
                    worker: {"authenticated": True, "composer_found": True,
                             "login_visible": False, "url": "https://example.invalid"}
                    for worker in ("sophie", "bernie")
                }

            def send_and_capture(self, action):
                text = action["expected_exact"] or "Receipt acknowledged."
                return result_for(action, text=text)

        test_root = Path(self.temp.name)
        (test_root / "config").mkdir()
        (test_root / "data" / "summit-relay").mkdir(parents=True)
        (test_root / "config" / "summit-relay.json").write_text(
            (ROOT / "config" / "summit-relay.json").read_text(encoding="utf-8"), encoding="utf-8"
        )
        browser_config = json.loads((ROOT / "config" / "summit-browser.json").read_text(encoding="utf-8"))
        browser_config["profile_directory"] = "data/private/test-profile"
        (test_root / "config" / "summit-browser.json").write_text(json.dumps(browser_config), encoding="utf-8")
        def fake_http(action, _config):
            return result_for(action, text="Receipt acknowledged.")

        with patch("josie.summit_browser.DirectSummitBrowser", FakeBrowser), \
             patch("josie.summit_browser.verify_josie_http", return_value=True), \
             patch("josie.summit_browser.deliver_josie_http", side_effect=fake_http):
            report = run_direct(project_root=test_root, acceptance=True)
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["transport"], "direct_playwright")
        receipt = (test_root / "data" / "summit-relay" / "receipts.jsonl").read_text(encoding="utf-8")
        self.assertIn('"extension_involved": false', receipt)
        self.assertIn('"job_completed"', receipt)

    def test_josie_delivery_uses_local_non_tool_http_flow(self):
        config = load_browser_config(ROOT)["josie_http"]
        completion = json.dumps({"choices": [{"message": {"content": "raw ack"}}]})
        completed = json.dumps({"messages": [{"role": "assistant", "content": "Receipt acknowledged."}]})
        action = {
            "action_id": "receipt-action", "payload": "FROM: SUMMIT_RELAY\nVIA: JOSIE",
        }
        with patch("josie.summit_browser._openwebui_owner_token", return_value="private-short-lived-token"), \
             patch("josie.summit_browser._post_json", side_effect=[
                 ("application/json", completion), ("application/json", completed)
             ]) as post:
            result = deliver_josie_http(action, config)
        self.assertTrue(result["ok"])
        self.assertEqual(result["assistant_text"], "Receipt acknowledged.")
        first_body = post.call_args_list[0].args[2]
        self.assertEqual(first_body["tool_ids"], [])
        self.assertEqual(first_body["model"], "josie-qwen3-8b:1.0")
        self.assertNotIn("private-short-lived-token", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
