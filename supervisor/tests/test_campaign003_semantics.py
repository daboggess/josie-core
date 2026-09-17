from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mission_manager.dispatcher import MissionManager
from supervisor.run_job import execute
from supervisor.work_order import WorkOrder


class Campaign003SemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = Path(__file__).parent / '.tmp_c003' / uuid.uuid4().hex
        cls.base.mkdir(parents=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(Path(__file__).parent / '.tmp_c003', ignore_errors=True)

    def setUp(self):
        self.workspace = self.base / uuid.uuid4().hex
        self.workspace.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.workspace)], check=True)
        self.receipts = self.base / 'receipts' / self.workspace.name
        self.receipts.mkdir(parents=True, exist_ok=True)

    def order(self, objective='allowed', acceptance=None, allowed=None, timeout=10):
        acc = acceptance or [
            {'type': 'file_exact', 'path': 'allowed.txt', 'content': 'OK'},
            {'type': 'changed_paths'},
            {'type': 'no_unexpected_files'},
        ]
        return {
            'schema_version': '1',
            'job_id': uuid.uuid4().hex,
            'objective': objective,
            'workspace': str(self.workspace),
            'harness': 'mock',
            'harness_executable': sys.executable,
            'model': 'mock/exact',
            'allowed_changed_paths': allowed or ['allowed.txt'],
            'timeout_seconds': timeout,
            'max_attempts': 1,
            'acceptance': acc,
            'prompt_profile': 'test',
            'receipt_destination': str(self.receipts),
        }

    def execute_order(self, data):
        path = self.workspace / 'order.json'
        data['allowed_changed_paths'] = list(data['allowed_changed_paths']) + ['order.json']
        path.write_text(json.dumps(data), encoding='utf-8')
        return execute(path)[0]

    def test_a_concurrent_josie_db_change_does_not_violate_scope(self):
        data = self.order(objective='allowed_and_db')
        receipt = self.execute_order(data)
        self.assertEqual(receipt['final_status'], 'PASS')
        self.assertEqual(receipt['reason'], 'PASS')
        self.assertIn('data/josie.db', receipt['observed_changed_paths'])
        self.assertNotIn('data/josie.db', receipt['changed_files'])
        self.assertNotIn('data/josie.db', receipt['scope_violations'])
        changed_check = next(c for c in receipt['acceptance_results'] if c['type'] == 'changed_paths')
        self.assertTrue(changed_check['passed'])
        no_unexpected_check = next(c for c in receipt['acceptance_results'] if c['type'] == 'no_unexpected_files')
        self.assertTrue(no_unexpected_check['passed'])

    def test_b_concurrent_wal_and_shm_treated_same_way(self):
        data = self.order(objective='allowed_and_wal_shm')
        receipt = self.execute_order(data)
        self.assertEqual(receipt['final_status'], 'PASS')
        self.assertEqual(receipt['reason'], 'PASS')
        self.assertIn('data/josie.db-wal', receipt['observed_changed_paths'])
        self.assertIn('data/josie.db-shm', receipt['observed_changed_paths'])
        self.assertNotIn('data/josie.db-wal', receipt['changed_files'])
        self.assertNotIn('data/josie.db-shm', receipt['changed_files'])
        self.assertNotIn('data/josie.db-wal', receipt['scope_violations'])
        self.assertNotIn('data/josie.db-shm', receipt['scope_violations'])
        changed_check = next(c for c in receipt['acceptance_results'] if c['type'] == 'changed_paths')
        self.assertTrue(changed_check['passed'])

    def test_c_unrelated_database_file_remains_detectable_scope_violation(self):
        data = self.order(objective='allowed_and_unrelated_db')
        receipt = self.execute_order(data)
        self.assertEqual(receipt['final_status'], 'FAIL')
        self.assertEqual(receipt['reason'], 'FAIL_SCOPE')
        self.assertIn('data/unrelated.db', receipt['changed_files'])
        self.assertIn('data/unrelated.db', receipt['scope_violations'])
        changed_check = next(c for c in receipt['acceptance_results'] if c['type'] == 'changed_paths')
        self.assertFalse(changed_check['passed'])

    def test_d_worker_direct_unauthorized_modification_to_josie_db_prohibited(self):
        data = self.order(objective='worker_targeted_db')
        receipt = self.execute_order(data)
        self.assertEqual(receipt['final_status'], 'FAIL')
        self.assertEqual(receipt['reason'], 'FAIL_SCOPE')
        self.assertIn('data/josie.db', receipt['scope_violations'])

    def test_e_acceptance_pass_cannot_be_overturned_by_blocked_prose(self):
        data = self.order(objective='blocked_prose_after_pass')
        receipt = self.execute_order(data)
        self.assertEqual(receipt['final_status'], 'PASS')
        self.assertEqual(receipt['reason'], 'PASS')

    def test_f_genuine_blocker_when_acceptance_not_satisfied_produces_blocked(self):
        data = self.order(objective='genuine_blocker_fail')
        receipt = self.execute_order(data)
        self.assertEqual(receipt['final_status'], 'BLOCKED')
        self.assertEqual(receipt['reason'], 'WORKER_BLOCKED')

    def test_f2_step_limit_without_acceptance_classified_as_harness_step_limit(self):
        data = self.order(objective='step_limit_fail')
        receipt = self.execute_order(data)
        self.assertEqual(receipt['final_status'], 'FAIL')
        self.assertEqual(receipt['reason'], 'HARNESS_STEP_LIMIT')

    def test_g_running_predecessor_does_not_return_dependency_deadlock(self):
        plan = {
            'mission_id': 'test-running-mission',
            'title': 'Running Test',
            'objective': 'Prove running does not deadlock',
            'jobs': [
                {
                    'job_id': 'job-1',
                    'title': 'First Job',
                    'department': 'coding',
                    'objective': 'Do first step',
                    'workspace': str(self.workspace),
                    'allowed_changes': ['out1.txt'],
                    'acceptance': [{'type': 'file_exists', 'path': 'out1.txt'}],
                    'dependencies': [],
                },
                {
                    'job_id': 'job-2',
                    'title': 'Second Job',
                    'department': 'coding',
                    'objective': 'Do second step',
                    'workspace': str(self.workspace),
                    'allowed_changes': ['out2.txt'],
                    'acceptance': [{'type': 'file_exists', 'path': 'out2.txt'}],
                    'dependencies': ['job-1'],
                },
                {
                    'job_id': 'job-3',
                    'title': 'Third Job',
                    'department': 'coding',
                    'objective': 'Do third step',
                    'workspace': str(self.workspace),
                    'allowed_changes': ['out3.txt'],
                    'acceptance': [{'type': 'file_exists', 'path': 'out3.txt'}],
                    'dependencies': ['job-2'],
                },
            ],
        }
        manager = MissionManager(self.base / 'missions', receipt_directory=self.receipts, work_order_directory=self.base / 'orders')
        mission = manager.create(plan)
        # In a live mission, when a job is running, mission status is ACTIVE and job-1 is RUNNING
        mission['status'] = 'ACTIVE'
        mission['jobs'][0]['status'] = 'RUNNING'
        manager.store.save(mission)

        outcome = manager.continue_until_stop('test-running-mission')
        self.assertNotEqual(outcome['stop_reason'], 'DEPENDENCY_DEADLOCK')
        self.assertEqual(outcome['stop_reason'], 'RUNNING')
        self.assertEqual(outcome['mission']['status'], 'ACTIVE')

    def test_h_genuine_dependency_deadlock_returns_dependency_deadlock(self):
        plan = {
            'mission_id': 'test-deadlock-mission',
            'title': 'Deadlock Test',
            'objective': 'Prove genuine deadlock is reported',
            'jobs': [
                {
                    'job_id': 'job-1',
                    'title': 'First Job',
                    'department': 'coding',
                    'objective': 'Do first step',
                    'workspace': str(self.workspace),
                    'allowed_changes': ['out1.txt'],
                    'acceptance': [{'type': 'file_exists', 'path': 'out1.txt'}],
                    'dependencies': [],
                },
                {
                    'job_id': 'job-2',
                    'title': 'Second Job',
                    'department': 'coding',
                    'objective': 'Do second step',
                    'workspace': str(self.workspace),
                    'allowed_changes': ['out2.txt'],
                    'acceptance': [{'type': 'file_exists', 'path': 'out2.txt'}],
                    'dependencies': ['job-1'],
                },
            ],
        }
        manager = MissionManager(self.base / 'missions', receipt_directory=self.receipts, work_order_directory=self.base / 'orders')
        mission = manager.create(plan)
        # Create a genuine circular dependency deadlock where job-1 waits on job-2 and job-2 waits on job-1
        mission['jobs'][0]['dependencies'] = ['job-2']
        mission['dependency_graph']['job-1'] = ['job-2']
        manager.store.save(mission)

        outcome = manager.continue_until_stop('test-deadlock-mission')
        self.assertEqual(outcome['stop_reason'], 'DEPENDENCY_DEADLOCK')


if __name__ == '__main__':
    unittest.main(verbosity=2)
