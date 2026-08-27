import io
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import types
from unittest.mock import patch

from josie import local_code as local


def events(command='python -m unittest', output='Ran 1 test\nOK'):
    return '\n'.join(json.dumps(e) for e in [
        {'type': 'tool_use', 'part': {'tool': 'bash', 'state': {'status': 'completed',
            'input': {'command': command}, 'output': output, 'metadata': {'exit': 0}}}},
        {'type': 'text', 'part': {'text': 'Executed and verified the task.'}},
        {'type': 'step_finish', 'part': {'reason': 'stop'}}])


class LocalCodeTests(unittest.TestCase):
    def test_parse_success(self):
        result = local.parse_events(events())
        self.assertTrue(result['final_observed'])
        self.assertEqual(result['actions_executed'], 1)
        self.assertEqual(result['tools'][0]['exit_code'], 0)

    def test_parse_text_only_is_not_execution(self):
        result = local.parse_events('{"type":"text","part":{"text":"I did it"}}')
        self.assertFalse(result['final_observed'])
        self.assertEqual(result['actions_executed'], 0)

    def test_parse_malformed_preserves_actual_work(self):
        result = local.parse_events(events() + '\ninvalid json')
        self.assertEqual(result['malformed_lines'], 1)
        self.assertEqual(result['actions_executed'], 1)

    def test_parse_missing_final_preserves_actual_work(self):
        result = local.parse_events(events().splitlines()[0])
        self.assertFalse(result['final_observed'])
        self.assertEqual(result['actions_executed'], 1)

    def test_malformed_event_shapes_fail_closed(self):
        result = local.parse_events('\n'.join(['{"type":[]}', '{"part":[]}',
            '{"type":"tool_use","part":{"state":"bad"}}']))
        self.assertEqual(result['malformed_lines'], 3)
        self.assertFalse(result['final_observed'])

    def test_explicit_authority_required(self):
        for text in ('Please code this', 'Delegate Local Code:', None):
            with self.assertRaises(ValueError):
                local.explicit_task(text)
        self.assertEqual(local.explicit_task('Delegate Local Code: run tests'), 'run tests')

    def setUp(self):
        policy_patch = patch.object(local, 'load_maintainer_policy', return_value={'write': {}})
        policy_patch.start()
        self.addCleanup(policy_patch.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'config').mkdir()
        config = {'enabled_providers': ['ollama'], 'model': 'ollama/test-local',
            'provider': {'ollama': {'options': {'baseURL': 'http://127.0.0.1:11434/v1'}}}}
        (self.root / 'config/opencode-local.json').write_text(json.dumps(config))
        self.job = 'local-test-0001'

    def request(self):
        return local.delegate_local_code('Write result.txt', 'Read back exact content',
            request_id=self.job, project_root=self.root)

    def test_missing_runtime_has_durable_truthful_failure(self):
        with patch.dict(os.environ, {'JOSIE_OPENCODE_EXE': str(self.root / 'missing.exe')}):
            result = self.request()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['actions_executed'], 0)
        self.assertTrue((self.root / f'data/private/local-code-jobs/{self.job}.json').exists())

    def test_ollama_unavailable(self):
        with patch.dict(os.environ, {'JOSIE_OPENCODE_EXE': sys.executable}), patch.object(local, 'urlopen', side_effect=OSError('offline')):
            result = self.request()
        self.assertIn('Ollama unavailable', result['error'])
        self.assertEqual(result['status'], 'failed')

    def test_missing_model(self):
        with patch.dict(os.environ, {'JOSIE_OPENCODE_EXE': sys.executable}), patch.object(local, 'urlopen', side_effect=[
            io.StringIO('{"version":"test"}'), io.StringIO('{"models":[]}')]):
            result = self.request()
        self.assertIn('model is unavailable', result['error'])

    def test_real_git_detects_change_to_already_dirty_file(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        target = self.root / 'fixture.txt'
        target.write_text('first')
        before = local.fingerprint(self.root)
        target.write_text('second')
        after = local.fingerprint(self.root)
        self.assertNotEqual(before['fixture.txt'], after['fixture.txt'])
        self.assertEqual(before['config/opencode-local.json'], after['config/opencode-local.json'])

    def invocation(self, timeout=False, event_text=None, exit_code=0):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Test', '-c', 'user.email=test@localhost',
            'commit', '--allow-empty', '-qm', 'fixture'], check=True)
        parent = self
        class Process:
            pid = 12345
            def __init__(self, args, **kwargs):
                parent.assertEqual(kwargs['cwd'], parent.root)
                parent.assertEqual(args[1:3], ['run', '--format'])
                self.returncode = None
                (parent.root / 'result.txt').write_text('verified')
                kwargs['stdout'].write(events() if event_text is None else event_text)
            def wait(self, timeout=None):
                if parent.timeout and self.returncode is None:
                    raise subprocess.TimeoutExpired('opencode', timeout)
                self.returncode = exit_code
                return exit_code
            def poll(self):
                return self.returncode
        self.timeout = timeout
        real_run = subprocess.run
        def run(args, **kwargs):
            if args[-1] == '--version':
                return subprocess.CompletedProcess(args, 0, '1.18.23', '')
            if args[0] == 'taskkill':
                self.timeout = False
                return subprocess.CompletedProcess(args, 0)
            return real_run(args, **kwargs)
        with patch.dict(os.environ, {'JOSIE_OPENCODE_EXE': sys.executable}), patch.object(local, 'urlopen', side_effect=[
            io.StringIO('{"version":"test"}'), io.StringIO('{"models":[{"name":"test-local"}]}')]), patch.object(
                local.subprocess, 'run', side_effect=run), patch.object(local.subprocess, 'Popen', Process):
            # Git runs before/after launch are real: avoid replacing its underlying Popen.
            with patch.object(local, 'git', side_effect=lambda root,*args: self.git_values(root,*args)), patch.object(
                local, 'fingerprint', side_effect=[{}, {'result.txt':'verified'}]):
                return self.request()

    def git_values(self, root, *args):
        if args == ('rev-parse', '--show-toplevel'): return str(root)
        if args == ('rev-parse', '--absolute-git-dir'): return str(root / '.git')
        if args == ('rev-parse', 'HEAD'): return 'a'*40
        return 'test'

    def test_success_receipt_and_file_write(self):
        result = self.invocation()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['changed_files'], ['result.txt'])
        self.assertEqual((self.root / 'result.txt').read_text(), 'verified')
        self.assertTrue(result['final_observed'])
        self.assertEqual(result['test_result'][0]['exit_code'], 0)

    def test_timeout_preserves_execution_evidence(self):
        result = self.invocation(timeout=True)
        self.assertTrue(result['timed_out'])
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['actions_executed'], 1)
        self.assertEqual(result['changed_files'], ['result.txt'])

    def test_text_without_tools_is_failed_even_with_final(self):
        result = self.invocation(event_text='\n'.join(events().splitlines()[1:]))
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['actions_executed'], 0)
        self.assertEqual(result['changed_files'], ['result.txt'])

    def test_process_failure_preserves_work(self):
        result = self.invocation(exit_code=7)
        self.assertEqual(result['exit_code'], 7)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['actions_executed'], 1)

    def test_missing_final_is_failed_with_activity_retained(self):
        result = self.invocation(event_text=events().splitlines()[0])
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['actions_executed'], 1)
        self.assertFalse(result['final_observed'])

    def test_idempotency_and_conflict(self):
        result = self.invocation()
        self.assertTrue(self.request()['cached'])
        with self.assertRaises(ValueError):
            local.delegate_local_code('Different', '', request_id=self.job, project_root=self.root)
        self.assertEqual(local.local_code_status(self.root, self.job)['response'], result['response'])

    def test_openapi_and_filter_keep_local_execution_separate(self):
        from josie.conversation_control import _openapi_spec
        paths = _openapi_spec(8790)['paths']
        self.assertEqual(paths['/v1/delegate/local-code']['post']['operationId'], 'delegate_local_code')
        self.assertEqual(paths['/v1/consult/codex']['post']['operationId'], 'consult_codex')
        source = Path(__file__).resolve().parents[1] / 'deploy/open-webui/exact-tool-response-filter.py'
        spec = importlib.util.spec_from_file_location('local_code_filter_test', source)
        module = importlib.util.module_from_spec(spec)
        stub = types.ModuleType('pydantic')
        stub.BaseModel = object
        stub.Field = lambda *, default: default
        with patch.dict(sys.modules, {'pydantic': stub}):
            spec.loader.exec_module(module)
        task = 'Delegate Local Code: inspect fixture and run its test'
        response = {'assistant_message': 'JOSIE LOCAL CODE — ACTUAL RESULT\nActual test evidence'}
        body = {'model': module.MODEL_ID, 'chat_id': 'local-test-chat', 'messages': [
            {'role': 'user', 'content': task}, {'role': 'assistant', 'content': 'unverified draft'}],
            'tool_ids': ['server:josie-subscription-seats']}
        emitted = []
        async def emit(event):
            emitted.append(event)
        with patch.object(module, '_record_history'), patch.object(module, '_control_post', return_value=response) as call:
            self.assertEqual(module.Filter().inlet(body)['tool_ids'], [])
            rendered = asyncio.run(module.Filter().outlet(body, __event_emitter__=emit))
        self.assertEqual(call.call_args.args[0], '/v1/delegate/local-code')
        self.assertEqual(call.call_args.args[1]['user_request'], task)
        self.assertEqual(rendered['messages'][-1]['content'], response['assistant_message'])
        self.assertEqual(emitted[-1]['data']['content'], response['assistant_message'])
        with patch.object(module, '_control_post', side_effect=TimeoutError()):
            message, _, route = module._authoritative_response(body, task)
        self.assertIn('RESULT UNAVAILABLE', message)
        self.assertIn('Delegate Local Code status:', message)

    def test_busy_does_not_overwrite_active_receipt(self):
        (self.root / '.git').mkdir()
        (self.root / '.git/josie-delegate.lock').write_text('other owner')
        with patch.dict(os.environ, {'JOSIE_OPENCODE_EXE': sys.executable}), patch.object(local, 'urlopen', side_effect=[
            io.StringIO('{"version":"test"}'), io.StringIO('{"models":[{"name":"test-local"}]}')]), patch.object(
                local, 'git', side_effect=lambda root,*args: self.git_values(root,*args)):
            result = self.request()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('active delegated job', result['error'])
        self.assertFalse((self.root / f'data/private/local-code-jobs/{self.job}.json').exists())
        self.assertEqual((self.root / '.git/josie-delegate.lock').read_text(), 'other owner')


if __name__ == '__main__':
    unittest.main()
