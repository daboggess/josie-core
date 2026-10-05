"""Unit tests for Josie Slack Relay (Manual Sophie Wake-Up Transport)."""

from __future__ import annotations

import ast
import json
import tempfile
import unittest
import uuid
from pathlib import Path

from josie.slack_relay import (
    DEFAULT_CHANNEL_ID,
    DEFAULT_DUSTIN_USER_ID,
    VALID_DISPOSITIONS,
    SlackConfig,
    SlackEnvelope,
    SlackRelayState,
    evaluate_inbound_message,
    format_outbound_message,
    load_slack_config,
    mask_token,
    parse_envelope,
)


class SlackRelayUnitTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.temp_dir.name)
        self.config = SlackConfig(
            bot_token="xoxb-dummy-test-token-12345",
            app_token="xapp-dummy-app-token-67890",
            channel_id=DEFAULT_CHANNEL_ID,
            dustin_user_id=DEFAULT_DUSTIN_USER_ID,
            state_dir=self.state_dir,
            bot_user_id="U_BOT_123",
        )
        self.state = SlackRelayState(self.state_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_token_masking(self):
        self.assertEqual(mask_token(None), "[NOT SET]")
        self.assertEqual(mask_token(""), "[NOT SET]")
        masked_bot = mask_token("xoxb-1234567890-abcdefghij")
        self.assertTrue(masked_bot.startswith("xoxb-1"))
        self.assertTrue(masked_bot.endswith("ghij (len=26)"))
        self.assertNotIn("1234567890-abcdef", masked_bot)

    def test_outbound_envelope_formatting(self):
        env = SlackEnvelope(
            from_party="ANTIGRAVITY",
            to_party="SOPHIE",
            mission="slack-relay-pilot-001",
            message_id="AG-PILOT-001",
            in_reply_to="NONE",
            msg_type="REVIEW_REQUEST",
            body="Antigravity Slack relay is online. This is a transport-only pilot. Perform no project mutation.",
            artifacts="None required.",
            tests="Relay test suite passed.",
            action_requested="Sophie: confirm receipt through Slack and reply with MISSION_COMPLETE if the communication path is healthy.",
        )
        formatted = format_outbound_message(env, sophie_needed=True, dustin_user_id=self.config.dustin_user_id)
        self.assertIn("FROM: ANTIGRAVITY", formatted)
        self.assertIn("TO: SOPHIE", formatted)
        self.assertIn("MISSION: slack-relay-pilot-001", formatted)
        self.assertIn("MESSAGE-ID: AG-PILOT-001", formatted)
        self.assertIn("IN-REPLY-TO: NONE", formatted)
        self.assertIn("TYPE: REVIEW_REQUEST", formatted)
        self.assertIn("BODY:\nAntigravity Slack relay is online.", formatted)
        self.assertIn("ARTIFACTS:\nNone required.", formatted)
        self.assertIn("TESTS:\nRelay test suite passed.", formatted)
        self.assertIn("ACTION REQUESTED:\nSophie: confirm receipt", formatted)
        self.assertIn(f"<@{DEFAULT_DUSTIN_USER_ID}> SOPHIE NEEDED — send relay in the AI Build ChatGPT conversation.", formatted)

    def test_josie_sender_abstraction(self):
        """Verify the envelope supports FROM: JOSIE without transport modifications."""
        env = SlackEnvelope(
            from_party="JOSIE",
            to_party="SOPHIE",
            mission="josie-continuity-001",
            message_id="JOSIE-001",
            body="Josie autonomous test.",
        )
        formatted = format_outbound_message(env, sophie_needed=False)
        self.assertIn("FROM: JOSIE", formatted)
        self.assertNotIn("SOPHIE NEEDED", formatted)

    def test_inbound_envelope_parsing_standard(self):
        raw = (
            "FROM: SOPHIE\n"
            "TO: ANTIGRAVITY\n"
            "MISSION: slack-relay-pilot-001\n"
            "MESSAGE-ID: SOPHIE-PILOT-001\n"
            "IN-REPLY-TO: AG-PILOT-001\n"
            "TYPE: RESULT\n"
            "DISPOSITION: MISSION_COMPLETE\n\n"
            "BODY:\n"
            "Receipt confirmed through Slack. Communication loop is healthy.\n\n"
            "ARTIFACTS:\n"
            "None.\n\n"
            "TESTS:\n"
            "Verified.\n\n"
            "ACTION REQUESTED:\n"
            "Close pilot mission."
        )
        parsed = parse_envelope(raw)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.from_party, "SOPHIE")
        self.assertEqual(parsed.to_party, "ANTIGRAVITY")
        self.assertEqual(parsed.mission, "slack-relay-pilot-001")
        self.assertEqual(parsed.message_id, "SOPHIE-PILOT-001")
        self.assertEqual(parsed.in_reply_to, "AG-PILOT-001")
        self.assertEqual(parsed.disposition, "MISSION_COMPLETE")
        self.assertIn("Receipt confirmed through Slack", parsed.body)

    def test_all_canonical_dispositions_recognized(self):
        for disp in VALID_DISPOSITIONS:
            raw = (
                f"FROM: SOPHIE\n"
                f"TO: ANTIGRAVITY\n"
                f"MISSION: test-mission\n"
                f"DISPOSITION: {disp}\n"
                f"BODY:\nEvaluating disposition {disp}."
            )
            parsed = parse_envelope(raw)
            self.assertIsNotNone(parsed)
            self.assertEqual(parsed.disposition, disp)

    def test_inbound_recipients_allowed(self):
        for recipient in ["ANTIGRAVITY", "JOSIE", "ALL"]:
            raw = (
                f"FROM: SOPHIE\n"
                f"TO: {recipient}\n"
                f"MISSION: m-001\n"
                f"BODY:\nOK\n"
                f"DISPOSITION: CONTINUE"
            )
            parsed = parse_envelope(raw)
            self.assertIsNotNone(parsed)
            self.assertEqual(parsed.to_party, recipient)

    def test_antigravity_ignores_own_messages(self):
        # By bot user ID
        own_msg_by_user = {
            "channel": self.config.channel_id,
            "ts": "100.001",
            "user": "U_BOT_123",
            "text": "FROM: ANTIGRAVITY\nTO: SOPHIE\nMISSION: m-001\nBODY:\nHello",
        }
        res = evaluate_inbound_message(own_msg_by_user, self.config, self.state)
        self.assertFalse(res.accepted)
        self.assertEqual(res.reason, "own_message_user_id")

        # By envelope sender header
        own_msg_by_header = {
            "channel": self.config.channel_id,
            "ts": "100.002",
            "user": "U_OTHER_USER",
            "text": "FROM: ANTIGRAVITY\nTO: SOPHIE\nMISSION: m-001\nBODY:\nHello",
        }
        res2 = evaluate_inbound_message(own_msg_by_header, self.config, self.state)
        self.assertFalse(res2.accepted)
        self.assertEqual(res2.reason, "own_message_envelope")

    def test_duplicate_events_ignored(self):
        evt_id = f"evt-{uuid.uuid4().hex[:8]}"
        msg = {
            "channel": self.config.channel_id,
            "ts": "101.001",
            "client_msg_id": evt_id,
            "user": "U_SOPHIE",
            "text": "FROM: SOPHIE\nTO: ANTIGRAVITY\nMISSION: m-dup\nMESSAGE-ID: MSG-D-1\nBODY:\nTest\nDISPOSITION: CONTINUE",
        }
        res1 = evaluate_inbound_message(msg, self.config, self.state)
        self.assertTrue(res1.accepted)
        self.state.record_receipt("INBOUND", evt_id, res1.envelope)

        # Second attempt must be rejected
        res2 = evaluate_inbound_message(msg, self.config, self.state)
        self.assertFalse(res2.accepted)
        self.assertEqual(res2.reason, "duplicate_event_id")

    def test_malformed_envelopes_ignored(self):
        bad_texts = [
            "Just a casual chat in Slack",
            "Hey Dustin, can you check this?",
            "FROM: NOBODY",
            "",
        ]
        for txt in bad_texts:
            msg = {
                "channel": self.config.channel_id,
                "ts": "102.001",
                "client_msg_id": f"evt-{uuid.uuid4().hex[:6]}",
                "user": "U_USER",
                "text": txt,
            }
            res = evaluate_inbound_message(msg, self.config, self.state)
            self.assertFalse(res.accepted)
            self.assertEqual(res.reason, "malformed_or_unrelated")

    def test_mission_correlation(self):
        msg = {
            "channel": self.config.channel_id,
            "ts": "103.001",
            "client_msg_id": f"evt-{uuid.uuid4().hex[:6]}",
            "user": "U_SOPHIE",
            "text": "FROM: SOPHIE\nTO: ANTIGRAVITY\nMISSION: other-mission-xyz\nBODY:\nWrong\nDISPOSITION: CONTINUE",
        }
        res = evaluate_inbound_message(msg, self.config, self.state, expected_mission="slack-relay-pilot-001")
        self.assertFalse(res.accepted)
        self.assertIn("mission_mismatch", res.reason)

    def test_zero_openai_and_chatgpt_api_guarantee(self):
        """Strictly verify no openai or chatgpt libraries/endpoints exist in the implementation."""
        relay_file = Path(__file__).resolve().parent.parent / "josie" / "slack_relay.py"
        source = relay_file.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    low = alias.name.lower()
                    self.assertNotIn("openai", low)
                    self.assertNotIn("chatgpt", low)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    low = node.module.lower()
                    self.assertNotIn("openai", low)
                    self.assertNotIn("chatgpt", low)


if __name__ == "__main__":
    unittest.main()
