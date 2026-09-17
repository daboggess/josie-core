import asyncio
import json
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from josie.conversation_control import _local_delegation_task


class LocalPhonePathTests(unittest.TestCase):
    def test_native_shell_is_pinned_for_service_and_direct_jobs(self):
        config = json.loads((Path(__file__).resolve().parents[1] / 'config/opencode-local.json').read_text())
        self.assertEqual(config['shell'], 'C:/Program Files/Git/bin/bash.exe')
        self.assertEqual(config['enabled_providers'], ['ollama'])

    def test_short_alias_preserves_complete_task(self):
        task = 'Run Python.\nAcceptance: show actual output; do not edit.'
        self.assertEqual(_local_delegation_task('Delegate Local: ' + task), task)

    def test_legacy_alias_and_explicit_authority(self):
        self.assertEqual(_local_delegation_task('Delegate Local Code: inspect'), 'inspect')
        for request in (None, 'Please inspect', 'Delegate Codex: inspect', 'Delegate Local:'):
            with self.assertRaises(ValueError):
                _local_delegation_task(request)

    def load_filter(self):
        source = Path(__file__).resolve().parents[1] / 'deploy/open-webui/exact-tool-response-filter.py'
        spec = importlib.util.spec_from_file_location('phone_filter_test', source)
        module = importlib.util.module_from_spec(spec)
        stub = types.ModuleType('pydantic')
        stub.BaseModel = object
        stub.Field = lambda *, default: default
        with patch.dict(sys.modules, {'pydantic': stub}):
            spec.loader.exec_module(module)
        return module

    def test_short_alias_routes_actual_result_without_consultants(self):
        module = self.load_filter()
        task = 'Delegate Local: execute Python and report actual output'
        body = {'model': module.MODEL_ID, 'chat_id': 'phone-routing-test', 'messages': [
            {'role': 'user', 'content': task}, {'role': 'assistant', 'content': 'unverified draft'}],
            'tool_ids': ['server:josie-subscription-seats',
                         'server:josie-subscription-seats/delegate_local_code']}
        response = {'assistant_message': 'JOSIE LOCAL CODE — ACTUAL RESULT\nStatus: completed'}
        emitted = []
        async def emit(event): emitted.append(event)
        with patch.object(module, '_record_history'), patch.object(module, '_prefetch_consultations') as consult, patch.object(
            module, '_control_post', return_value=response) as call:
            inlet = module.Filter().inlet(body)
            rendered = asyncio.run(module.Filter().outlet(inlet, __event_emitter__=emit))
        consult.assert_not_called()
        self.assertEqual(inlet['tool_ids'], [])
        self.assertEqual(call.call_args.args, ('/v1/delegate/local-code', {
            'request_id': module._consultation_request_id(body, 'localcode', task), 'user_request': task}))
        self.assertEqual(rendered['messages'][-1]['content'], response['assistant_message'])
        self.assertEqual(emitted[-1]['data']['content'], response['assistant_message'])
        self.assertIn('PENDING', emitted[0]['data']['content'])
        self.assertFalse(emitted[0]['data']['done'])

    def test_full_raw_local_code_request_dispatches_once_without_xml(self):
        module = self.load_filter()
        raw = "\n".join((
            "Delegate Local Code:", "", r"Workspace: D:\fixture\repo", "",
            "Task:", "Preserve this task text exactly; no XML.", "",
            "Allowed changes:", "value.py", "", "Acceptance:",
            r"command: D:\Josie\.venv\Scripts\python.exe -m unittest -v",
        ))
        body = {
            'model': module.MODEL_ID,
            'chat_id': 'raw-ingress-test',
            'messages': [{'role': 'user', 'content': raw},
                         {'role': 'assistant', 'content': 'model draft'}],
            'tool_ids': ['server:josie-subscription-seats/delegate_local_code'],
        }
        response = {'assistant_message':
                    'JOSIE LOCAL CODE — ACTUAL RESULT\nLOCAL CODE RESULT: PASS'}
        with patch.object(module, '_record_history'), patch.object(
                module, '_control_post', return_value=response) as dispatch:
            inlet = module.Filter().inlet(body)
            rendered = asyncio.run(module.Filter().outlet(inlet))
        dispatch.assert_called_once()
        self.assertEqual(dispatch.call_args.args[0], '/v1/delegate/local-code')
        self.assertEqual(dispatch.call_args.args[1]['user_request'], raw)
        self.assertNotIn('<task>', dispatch.call_args.args[1]['user_request'])
        self.assertEqual(inlet['tool_ids'], [])
        self.assertEqual(rendered['messages'][-1]['content'], response['assistant_message'])

    def test_missing_required_details_returns_authoritative_rejection_once(self):
        module = self.load_filter()
        raw = 'Delegate Local Code:\n\nTask:\nInspect the repository.'
        response = {'assistant_message':
                    'JOSIE LOCAL CODE — ACTUAL RESULT\nLOCAL CODE RESULT: NEEDS_JOB_DETAILS'}
        body = {'model': module.MODEL_ID, 'chat_id': 'missing-details-test',
                'messages': [{'role': 'user', 'content': raw},
                             {'role': 'assistant', 'content': 'model draft'}],
                'tool_ids': ['server:josie-subscription-seats/delegate_local_code']}
        with patch.object(module, '_record_history'), patch.object(
                module, '_control_post', return_value=response) as dispatch:
            inlet = module.Filter().inlet(body)
            rendered = asyncio.run(module.Filter().outlet(inlet))
        dispatch.assert_called_once()
        self.assertEqual(inlet['tool_ids'], [])
        self.assertIn('NEEDS_JOB_DETAILS', rendered['messages'][-1]['content'])

    def test_short_status_alias_does_not_execute(self):
        module = self.load_filter()
        body = {'model': module.MODEL_ID, 'chat_id': 'phone-status-test',
                'messages': [{'role': 'user',
                              'content': 'Delegate Local status: phone-test-0001'},
                             {'role': 'assistant', 'content': 'draft'}]}
        with patch.object(module, '_control_post', return_value={
            'assistant_message': 'JOSIE LOCAL CODE — ACTUAL RESULT\nStatus: failed'}) as call:
            inlet = module.Filter().inlet(body)
            result = module._authoritative_response(
                inlet, 'Delegate Local status: phone-test-0001')
        self.assertEqual(call.call_args.args[0], '/v1/delegate/local-code/status')
        self.assertIn('Status: failed', result[0])

    def test_status_refresh_does_not_reuse_or_overwrite_submission_cache(self):
        module = self.load_filter()
        module._LOCAL_CODE_INGRESS_RESULTS.clear()
        job_id = 'phone-cache-test-0002'
        module._LOCAL_CODE_INGRESS_RESULTS[f'submit:{job_id}'] = {
            'assistant_message': 'JOSIE LOCAL CODE — ACTUAL RESULT\nLOCAL CODE RESULT: PASS'}
        body = {'model': module.MODEL_ID,
                'messages': [{'role': 'user',
                              'content': f'Delegate Local status: {job_id}'}]}
        fresh = {'assistant_message':
                 'JOSIE LOCAL CODE — ACTUAL RESULT\nLOCAL CODE RESULT: VALIDATION_FAIL'}
        with patch.object(module, '_control_post', return_value=fresh) as call:
            inlet = module.Filter().inlet(body)
            result = module._authoritative_response(
                inlet, f'Delegate Local status: {job_id}')
        call.assert_called_once()
        self.assertIn('VALIDATION_FAIL', result[0])
        self.assertIn(f'submit:{job_id}', module._LOCAL_CODE_INGRESS_RESULTS)
        self.assertEqual(module._LOCAL_CODE_INGRESS_RESULTS[f'status:{job_id}'], fresh)

    def test_local_drafts_are_suppressed_at_native_stream_boundary(self):
        module = self.load_filter()
        fake = {'choices': [{'delta': {'content': 'Invented successful output', 'tool_calls': [{}]}}]}
        for request in ('Delegate Local: inspect', 'Delegate Local Code: inspect',
                        'Delegate Local status: phone-test-0001'):
            body = {'model': module.MODEL_ID, 'messages': [{'role': 'user', 'content': request}]}
            self.assertIsNone(module.Filter().stream(fake, __body__=body))

    def test_stream_hook_preserves_normal_and_codex_conversations(self):
        module = self.load_filter()
        event = {'choices': [{'delta': {'content': 'ordinary conversation'}}]}
        for request in ('Hello', 'Delegate Codex: inspect', 'Consult Codex: advice'):
            body = {'model': module.MODEL_ID, 'messages': [{'role': 'user', 'content': request}]}
            self.assertIs(module.Filter().stream(event, __body__=body), event)

    def test_local_requests_use_filtered_stream_without_global_config_change(self):
        module = self.load_filter()
        with patch.object(module, '_record_history'):
            body = module.Filter().inlet({'model': module.MODEL_ID, 'stream': False,
                'messages': [{'role': 'user', 'content': 'Delegate Local: inspect'}]})
        self.assertTrue(body['stream'])

    def test_explicit_model_allowlist_includes_wrappers_and_raw_qwen_front_door(self):
        module = self.load_filter()
        self.assertEqual(module.MODEL_IDS, {
            'josie-local:1.0', 'josie-qwen3-8b:1.0', 'qwen3:14b',
            'gemma4:12b', 'josie-antigravity-flash', 'josie-antigravity-pro'})
        for model_id in module.MODEL_IDS:
            with patch.object(module, '_record_history'):
                body = module.Filter().inlet({'model': model_id, 'stream': False,
                    'messages': [{'role': 'user', 'content': 'Delegate Local: inspect'}]})
            self.assertTrue(body['stream'])
        raw = {'model': 'josie-qual-qwen3:8b-32k', 'stream': False,
            'messages': [{'role': 'user', 'content': 'Delegate Local: inspect'}]}
        self.assertIs(module.Filter().inlet(raw), raw)

    def test_ordinary_new_front_door_chat_does_not_trigger_local_execution(self):
        module = self.load_filter()
        body = {'model': 'josie-qwen3-8b:1.0',
            'messages': [{'role': 'user', 'content': 'Say hello in one sentence.'},
                         {'role': 'assistant', 'content': 'Hello.'}]}
        with patch.object(module, '_control_post') as execute:
            rendered = asyncio.run(module.Filter().outlet(body))
        execute.assert_not_called()
        self.assertEqual(rendered['messages'][-1]['content'], 'Hello.')
