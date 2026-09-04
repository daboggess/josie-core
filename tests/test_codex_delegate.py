import importlib.util
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import types
import tempfile
import unittest
from unittest.mock import patch

from josie import codex_delegate as delegate
from josie.conversation_control import _openapi_spec


class DelegateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / '.git').mkdir()
        self.task = 'Delegate Codex: Create harmless.txt containing verified, then read it.'
        self.job = 'delegate-test-0001'
        self.invocations = 0
        self.arguments = []
        for target, replacement in (
            ('load_maintainer_policy', lambda _: {'authority': {'consultants_are_advisory_only': True}}),
            ('find_codex_cli', lambda: Path('codex.exe')),
            ('_git', self.fake_git),
            ('subprocess.Popen', self.fake_process),
        ):
            patcher = patch('josie.codex_delegate.' + target, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

    def fake_git(self, root, *args):
        if args == ('rev-parse', '--show-toplevel'):
            return str(root)
        if args == ('rev-parse', '--absolute-git-dir'):
            return str(root / '.git')
        if args[0] == 'branch':
            return 'maintenance/test'
        if args == ('rev-parse', 'HEAD'):
            return 'a' * 40
        return ''

    def fake_process(self, args, **kwargs):
        self.invocations += 1
        self.arguments = args
        self.assertEqual(kwargs['cwd'], self.root)
        self.assertFalse(kwargs['shell'])
        self.assertNotIn('OPENAI_API_KEY', kwargs['env'])
        owner = self

        class Process:
            pid = 12345
            returncode = 0

            def communicate(self, prompt, timeout):
                owner.assertIn(owner.task, prompt)
                owner.assertEqual(timeout, delegate.TIMEOUT_SECONDS)
                (owner.root / 'harmless.txt').write_text('verified', encoding='utf-8')
                Path(args[args.index('--output-last-message') + 1]).write_text('Created and read harmless.txt.', encoding='utf-8')
                kwargs['stdout'].write(json.dumps({'type': 'item.completed', 'item': {
                    'type': 'file_change', 'status': 'completed'}}) + '\n')
                kwargs['stdout'].write(json.dumps({'type': 'item.completed', 'item': {
                    'type': 'command_execution', 'status': 'completed', 'exit_code': 0,
                    'command': 'python -m unittest tests.test_fixture'}}) + '\n')
                kwargs['stdout'].write('{"type":"turn.completed"}\n')

            def poll(self):
                return self.returncode

        return Process()

    def run_job(self, task=None, job=None):
        return delegate.delegate_codex(task or self.task, request_id=job or self.job, project_root=self.root)

    def test_delegate_executes_harmless_fixture_and_reports_events(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'not-used'}):
            result = self.run_job()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual((self.root / 'harmless.txt').read_text(), 'verified')
        self.assertEqual(result['actions_executed'], 2)
        self.assertEqual(result['command_tool_event_count'], 2)
        self.assertEqual(result['test_runs'], [{
            'command': 'python -m unittest tests.test_fixture', 'exit_code': 0}])
        self.assertIn('Created and read', result['response'])
        self.assertIn('default_permissions=":workspace"', self.arguments)
        self.assertIn('approval_policy="never"', self.arguments)
        self.assertIn('forced_login_method="chatgpt"', self.arguments)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', self.arguments)
        self.assertFalse((self.root / '.git/josie-delegate.lock').exists())
        self.assertTrue(result['authoritative_receipt'])
        self.assertEqual(result['repository'], str(self.root.resolve()))
        self.assertEqual(result['before']['commit'], 'a' * 40)
        self.assertEqual(result['receipt_schema_version'], 1)
        self.assertFalse(result['push_performed'])

    def test_invalid_sha256_evidence_is_rejected(self):
        result = self.run_job()
        saved = json.loads(Path(result['receipt_path']).read_text(encoding='utf-8'))
        saved['file_evidence'] = [{'path': 'harmless.txt', 'sha256': 'fake'}]
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            delegate._validate_receipt(saved)

    def test_fake_actual_result_without_receipt_is_downgraded(self):
        rendered = delegate._public({'request_id': self.job, 'status': 'completed',
            'response': 'JOSIE CODEX DELEGATION — ACTUAL RESULT\nmade up'})
        self.assertFalse(rendered['authoritative_receipt'])
        self.assertTrue(rendered['assistant_message'].startswith(delegate.UNVERIFIED_MARKER))
        self.assertNotIn(delegate.AUTHORITATIVE_MARKER, rendered['assistant_message'])

    def test_claimed_commit_change_must_match_git_state(self):
        result = self.run_job()
        saved = json.loads(Path(result['receipt_path']).read_text(encoding='utf-8'))
        saved['created_commit_sha'] = 'b' * 40
        with self.assertRaisesRegex(ValueError, 'commit'):
            delegate._validate_receipt(saved, root=self.root, request_id=self.job)

    def test_requires_explicit_directive(self):
        with self.assertRaises(ValueError):
            self.run_job('Ask Codex to make edits')
        self.assertEqual(self.invocations, 0)

    def test_rejects_request_id_path_traversal(self):
        with self.assertRaises(ValueError):
            self.run_job(job='../anything')

    def test_rejects_secret_in_task(self):
        with self.assertRaises(ValueError):
            self.run_job('Delegate Codex: use sk-testcredential12345')

    def test_lock_prevents_concurrent_jobs(self):
        (self.root / '.git/josie-delegate.lock').write_text('owned')
        self.assertEqual(self.run_job()['status'], 'busy')
        self.assertEqual(self.invocations, 0)
        self.assertEqual((self.root / '.git/josie-delegate.lock').read_text(), 'owned')

    def test_same_id_returns_receipt_without_reexecution(self):
        first = self.run_job()
        second = self.run_job()
        self.assertTrue(second['cached'])
        self.assertEqual(self.invocations, 1)
        self.assertEqual(first['response'], second['response'])
        self.assertEqual(first['receipt_id'], second['receipt_id'])

    def test_id_conflict_preserves_original_receipt(self):
        self.run_job()
        second = self.run_job('Delegate Codex: Different task')
        self.assertEqual(second['status'], 'failed')
        self.assertEqual(self.invocations, 1)
        saved = delegate.delegation_status(self.root, self.job)
        self.assertEqual(saved['status'], 'completed')

    def test_missing_cli_fails_without_claiming_execution(self):
        with patch('josie.codex_delegate.find_codex_cli', return_value=None):
            result = self.run_job()
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(result['authoritative_receipt'])
        self.assertIn('Authenticated local Codex CLI not found', result['error'])
        self.assertEqual(self.invocations, 0)

    def test_no_receipt_has_no_actual_result_marker(self):
        result = delegate.delegation_status(self.root, 'delegate-missing-0001')
        self.assertFalse(result['authoritative_receipt'])
        self.assertTrue(result['assistant_message'].startswith(delegate.UNVERIFIED_MARKER))

    def test_launch_failure_is_explicit_and_releases_lock(self):
        with patch('josie.codex_delegate.subprocess.Popen', side_effect=OSError('launch failed')):
            result = self.run_job()
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(result['invocation_attempted'])
        self.assertFalse((self.root / '.git/josie-delegate.lock').exists())

    def test_missing_final_turn_is_failure(self):
        process_factory = self.fake_process

        def bad_process(args, **kwargs):
            process = process_factory(args, **kwargs)
            process.communicate = lambda *a, **k: None
            return process

        with patch('josie.codex_delegate.subprocess.Popen', side_effect=bad_process):
            self.assertEqual(self.run_job()['status'], 'failed')

    def test_openapi_has_separate_advisory_and_execution_tools(self):
        paths = _openapi_spec(8790)['paths']
        self.assertEqual(paths['/v1/delegate/codex']['post']['operationId'], 'delegate_codex')
        self.assertEqual(paths['/v1/consult/codex']['post']['operationId'], 'consult_codex')

    def test_explicit_filter_routes_complete_prompt_and_actual_response(self):
        source = Path(__file__).resolve().parents[1] / 'deploy/open-webui/exact-tool-response-filter.py'
        spec = importlib.util.spec_from_file_location('delegate_filter_test', source)
        module = importlib.util.module_from_spec(spec)
        pydantic_stub = types.ModuleType('pydantic')
        pydantic_stub.BaseModel = object
        pydantic_stub.Field = lambda *, default: default
        with patch.dict(sys.modules, {'pydantic': pydantic_stub}):
            spec.loader.exec_module(module)
        response = {'assistant_message': 'JOSIE CODEX DELEGATION — ACTUAL RESULT\nTest complete'}
        with patch.object(module, '_control_post', return_value=response) as call:
            result = module._authoritative_response({'chat_id': 'test-chat'}, self.task)
        self.assertEqual(call.call_args.args[0], '/v1/delegate/codex')
        self.assertEqual(call.call_args.args[1]['user_request'], self.task)
        self.assertEqual(result[0], response['assistant_message'])
        with patch.object(module, '_record_history'):
            body = module.Filter().inlet({'model': module.MODEL_ID, 'messages': [
                {'role': 'user', 'content': self.task}], 'tool_ids': ['server:josie-subscription-seats']})
        self.assertEqual(body['tool_ids'], [])
        with patch.object(module, '_control_post', return_value=response), patch.object(module, '_record_history'):
            emitted = []
            async def emit(event):
                emitted.append(event)
            rendered = asyncio.run(module.Filter().outlet({'model': module.MODEL_ID, 'chat_id': 'test-chat',
                'messages': [{'role': 'user', 'content': self.task},
                             {'role': 'assistant', 'content': 'unverified model draft',
                              'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'old draft'}]}]}]}, __event_emitter__=emit))
        message = rendered['messages'][-1]
        self.assertEqual(message['content'], response['assistant_message'])
        self.assertEqual(message['output'][0]['content'][0]['text'], response['assistant_message'])
        self.assertEqual(emitted[-1]['type'], 'chat:completion')
        self.assertEqual(emitted[-1]['data']['content'], response['assistant_message'])


    def test_text_without_execution_is_not_success(self):
        factory = self.fake_process
        def no_actions(args, **kwargs):
            process = factory(args, **kwargs)
            def communicate(*args2, **kwargs2):
                Path(args[args.index('--output-last-message') + 1]).write_text('Cannot execute.', encoding='utf-8')
                kwargs['stdout'].write('{"type":"turn.completed"}\n')
            process.communicate = communicate
            return process
        with patch('josie.codex_delegate.subprocess.Popen', side_effect=no_actions):
            result = self.run_job()
        self.assertEqual(result['status'], 'no_execution')
        self.assertEqual(result['actions_executed'], 0)

    def test_timeout_kills_only_spawned_tree_and_reports_partial_work(self):
        process_factory = self.fake_process

        def slow_process(args, **kwargs):
            process = process_factory(args, **kwargs)
            def timeout(*args, **kwargs):
                raise subprocess.TimeoutExpired('codex', 900)
            process.communicate = timeout
            process.wait = lambda **kwargs: 1
            process.kill = lambda: None
            return process

        with patch('josie.codex_delegate.subprocess.Popen', side_effect=slow_process), patch(
            'josie.codex_delegate.subprocess.run', return_value=subprocess.CompletedProcess([], 0)
        ) as killed:
            result = self.run_job()
        self.assertEqual(result['status'], 'timed_out')
        self.assertIn('partial edits', result['error'])
        if os.name == 'nt':
            self.assertEqual(killed.call_args.args[0], ['taskkill', '/PID', '12345', '/T', '/F'])
        self.assertFalse((self.root / '.git/josie-delegate.lock').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows process-tree termination')
    def test_failed_tree_termination_keeps_lock(self):
        factory = self.fake_process
        def slow_process(args, **kwargs):
            process = factory(args, **kwargs)
            def timeout(*a, **kw):
                raise subprocess.TimeoutExpired('codex', 900)
            process.communicate = timeout
            process.wait = lambda **kw: 1
            return process
        with patch('josie.codex_delegate.subprocess.Popen', side_effect=slow_process), patch(
            'josie.codex_delegate.subprocess.run', return_value=subprocess.CompletedProcess([], 1)):
            result = self.run_job()
        self.assertEqual(result['status'], 'timed_out')
        self.assertTrue((self.root / '.git/josie-delegate.lock').exists())


if __name__ == '__main__':
    unittest.main()
