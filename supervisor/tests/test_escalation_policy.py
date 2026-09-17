from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.policy import ESCALATION_LADDER, TIER_DESCRIPTIONS, next_escalation_tier


class EscalationPolicyTests(unittest.TestCase):
    def test_01_escalation_ladder_order_is_authoritative(self):
        expected = [
            'deterministic_local',
            'primary_local_worker',
            'local_fallback_reviewer',
            'antigravity_flash',
            'antigravity_pro',
            'codex',
            'paid_api_authorized',
        ]
        self.assertEqual(ESCALATION_LADDER, expected)
        for tier in expected:
            self.assertIn(tier, TIER_DESCRIPTIONS)

    def test_02_sequential_escalation_through_ladder(self):
        tier, audit = next_escalation_tier(None)
        self.assertEqual(tier, 'deterministic_local')
        self.assertEqual(audit['paid_ai_credits'], 'OFF')

        tier, audit = next_escalation_tier('deterministic_local')
        self.assertEqual(tier, 'primary_local_worker')

        tier, audit = next_escalation_tier('primary_local_worker')
        self.assertEqual(tier, 'local_fallback_reviewer')

        tier, audit = next_escalation_tier('local_fallback_reviewer')
        self.assertEqual(tier, 'antigravity_flash')

        tier, audit = next_escalation_tier('antigravity_flash')
        self.assertEqual(tier, 'antigravity_pro')

        tier, audit = next_escalation_tier('antigravity_pro')
        self.assertEqual(tier, 'codex')

        # Codex without paid authorization halts safely
        tier, audit = next_escalation_tier('codex', paid_authorized=False)
        self.assertIsNone(tier)
        self.assertEqual(audit['status'], 'STOP_PAID_API_NOT_AUTHORIZED')

    def test_03_stronger_reasoning_escalates_to_pro_first(self):
        tier, audit = next_escalation_tier(
            'local_fallback_reviewer', task_requires_stronger_reasoning=True
        )
        self.assertEqual(tier, 'antigravity_pro')

    def test_04_antigravity_flash_quota_exhausted_falls_back_to_pro(self):
        tier, audit = next_escalation_tier(
            'local_fallback_reviewer',
            antigravity_flash_available=False,
            antigravity_flash_quota_exhausted=True,
        )
        self.assertEqual(tier, 'antigravity_pro')
        self.assertEqual(audit['skipped_tier'], 'antigravity_flash_exhausted_or_unavailable')

    def test_05_all_antigravity_exhausted_falls_forward_to_codex(self):
        tier, audit = next_escalation_tier(
            'local_fallback_reviewer',
            antigravity_flash_quota_exhausted=True,
            antigravity_pro_quota_exhausted=True,
        )
        self.assertEqual(tier, 'codex')
        self.assertIn('skipped_tier', audit)
        self.assertIn('skipped_tier_2', audit)

    def test_06_paid_api_never_silently_selected(self):
        tier, audit = next_escalation_tier('codex', paid_authorized=False)
        self.assertIsNone(tier)
        self.assertFalse(audit['paid_api_authorized'])

        tier, audit = next_escalation_tier('codex', paid_authorized=True)
        self.assertEqual(tier, 'paid_api_authorized')
        self.assertTrue(audit['paid_api_authorized'])

    def test_07_antigravity_pro_exhausted_falls_to_codex(self):
        tier, audit = next_escalation_tier(
            'antigravity_flash', antigravity_pro_quota_exhausted=True
        )
        self.assertEqual(tier, 'codex')
        self.assertEqual(audit['skipped_tier'], 'antigravity_pro_exhausted_or_unavailable')


if __name__ == '__main__':
    unittest.main()
