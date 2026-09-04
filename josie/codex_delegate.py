"""Explicit repository engineering delegation, separate from advisory consultants.

Uses the standard Codex workspace sandbox, not a second Maintainer policy engine.
Receipts and an exclusive lock are separate from Josie's historical SQLite data.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
from datetime import datetime, timezone

from .conversation_control import (
    _CODEX_REMOVED_ENV, _clean_environment, _hidden_process_flags,
    _safe_error, _SECRET_MARKERS, find_codex_cli,
)
from .maintainer import load_maintainer_policy

TIMEOUT_SECONDS = 900
MAX_TASK = 24000
REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{7,95}")
PREFIX = re.compile(r"\A\s*Delegate[ _]+Codex\s*:\s*", re.I)
RECEIPT_SCHEMA_VERSION = 1
AUTHORITATIVE_MARKER = 'JOSIE CODEX DELEGATION — ACTUAL RESULT'
UNVERIFIED_MARKER = 'NO AUTHORITATIVE EXECUTOR RECEIPT — RESULT UNVERIFIED'
GIT_SHA = re.compile(r'[0-9a-f]{40}(?:[0-9a-f]{24})?')
SHA256 = re.compile(r'[0-9a-f]{64}')
TERMINAL_STATUSES = {'completed', 'failed', 'no_execution', 'timed_out'}


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ['git', '-C', str(root), *args], capture_output=True, text=True,
        encoding='utf-8', errors='replace', timeout=30, check=True,
        creationflags=_hidden_process_flags(),
    )
    return result.stdout.strip()


def _snapshot(root: Path) -> dict:
    return {'branch': _git(root, 'branch', '--show-current'),
            'commit': _git(root, 'rev-parse', 'HEAD'),
            'working_tree': _git(root, 'status', '--short', '--untracked-files=all')[:12000]}


def _save(path: Path, result: dict) -> None:
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, indent=2), encoding='utf-8')
    temporary.replace(path)


def _changed_files(before: dict, after: dict) -> list[str]:
    names = set()
    for snapshot in (before, after):
        for line in str(snapshot.get('working_tree') or '').splitlines():
            if len(line) >= 4:
                name = line[3:].split(' -> ')[-1].strip().strip('"')
                if name:
                    names.add(name)
    return sorted(names)


def _is_test_command(command: str) -> bool:
    lowered = command.lower()
    return any(token in lowered for token in ('pytest', 'unittest', ' test', 'tests/','tests\\'))


def _validate_receipt(result: object, *, root: Path | None = None,
                      request_id: str | None = None) -> dict:
    if not isinstance(result, dict):
        raise ValueError('Executor receipt is not an object')
    required = {
        'receipt_schema_version': int, 'receipt_id': str, 'job_id': str,
        'request_id': str, 'executor': str, 'repository': str, 'hostname': str,
        'before': dict, 'after': dict, 'command_tool_event_count': int,
        'changed_files': list, 'test_runs': list, 'output_locations': dict,
        'push_performed': bool, 'timestamp': str, 'status': str, 'worktree': str,
        'receipt_path': str,
        'task_sha256': str,
    }
    if any(not isinstance(result.get(key), kind) for key, kind in required.items()):
        raise ValueError('Executor receipt schema is incomplete')
    if result['receipt_schema_version'] != RECEIPT_SCHEMA_VERSION:
        raise ValueError('Executor receipt schema version is invalid')
    identifiers = (result['receipt_id'], result['job_id'], result['request_id'])
    if len(set(identifiers)) != 1 or not REQUEST_ID.fullmatch(identifiers[0]):
        raise ValueError('Executor receipt identity is invalid')
    if request_id is not None and result['request_id'] != request_id:
        raise ValueError('Executor receipt request ID mismatch')
    if result['executor'] != 'codex-cli' or result['status'] not in TERMINAL_STATUSES:
        raise ValueError('Executor receipt is not terminal')
    try:
        datetime.fromisoformat(result['timestamp'])
    except ValueError as exc:
        raise ValueError('Executor receipt timestamp is invalid') from exc
    if not SHA256.fullmatch(result['task_sha256']):
        raise ValueError('Executor receipt task hash is invalid')
    for snapshot in (result['before'], result['after']):
        if (not isinstance(snapshot.get('branch'), str)
                or not GIT_SHA.fullmatch(str(snapshot.get('commit') or ''))
                or not isinstance(snapshot.get('working_tree'), str)):
            raise ValueError('Executor receipt Git evidence is invalid')
    if root is not None:
        resolved = root.resolve(strict=True)
        if Path(result['repository']).resolve(strict=True) != resolved:
            raise ValueError('Executor receipt repository mismatch')
        if result['after']['commit'] != _git(resolved, 'rev-parse', 'HEAD'):
            raise ValueError('Executor receipt ending commit does not match Git state')
        if result['after']['branch'] != _git(resolved, 'branch', '--show-current'):
            raise ValueError('Executor receipt branch does not match Git state')
    if result['command_tool_event_count'] < 0:
        raise ValueError('Executor receipt event count is invalid')
    if result['push_performed'] is not False:
        raise ValueError('Executor receipt claims an unauthorized push')
    if result.get('created_commit_sha') is not None:
        created = result['created_commit_sha']
        if not isinstance(created, str) or not GIT_SHA.fullmatch(created):
            raise ValueError('Executor receipt created commit is invalid')
        if created != result['after']['commit'] or created == result['before']['commit']:
            raise ValueError('Claimed commit change does not match Git evidence')
    elif result['before']['commit'] != result['after']['commit']:
        raise ValueError('Executor receipt omitted its created commit')
    for evidence in result.get('file_evidence') or []:
        if not isinstance(evidence, dict) or not SHA256.fullmatch(str(evidence.get('sha256') or '')):
            raise ValueError('Executor receipt SHA-256 evidence is invalid')
    if not all(isinstance(item, str) for item in result['changed_files']):
        raise ValueError('Executor receipt changed-file evidence is invalid')
    for run in result['test_runs']:
        if (not isinstance(run, dict) or not isinstance(run.get('command'), str)
                or not isinstance(run.get('exit_code'), (int, type(None)))):
            raise ValueError('Executor receipt test evidence is invalid')
    return result


def _public(result: dict) -> dict:
    result = dict(result)
    try:
        _validate_receipt(result)
    except (OSError, ValueError):
        result['authoritative_receipt'] = False
        result['assistant_message'] = (
            f'{UNVERIFIED_MARKER}\nJob: {result.get("request_id", "unknown")}\n'
            f'Status: {result.get("status", "unverified")}\n'
            f'Error: {result.get("error") or "A valid terminal executor receipt does not exist."}'
        )
        return result
    result['authoritative_receipt'] = True
    after = result.get('after') or {}
    result['assistant_message'] = (
        f'{AUTHORITATIVE_MARKER}\n'
        f"Job: {result['request_id']}\nStatus: {result['status']}\n"
        f"Repository: {result.get('repository', 'not started')}\n"
        f"Branch: {after.get('branch', 'not verified')}\n"
        f"Commit: {after.get('commit', 'not verified')}\n"
        f"Executed command/file-change events: {result.get('actions_executed', 0)}\n"
        f"Error: {result.get('error') or 'none'}\n\n"
        f"{result.get('response') or 'No final Codex response.'}"
    )
    return result


def delegation_status(project_root: Path, request_id: str) -> dict:
    if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
        raise ValueError('Invalid delegation request ID')
    path = project_root / 'data/private/codex-delegations' / (request_id + '.json')
    if not path.is_file():
        return _public({'request_id': request_id, 'status': 'not_found'})
    payload = json.loads(path.read_text(encoding='utf-8'))
    _validate_receipt(payload, root=project_root, request_id=request_id)
    return _public(payload)


def delegate_codex(user_request: str, *, request_id: str, project_root: Path) -> dict:
    """Execute only an explicit complete 'Delegate Codex:' user instruction.

    The caller cannot override the repository, CLI, flags, timeout, or environment.
    Prompt directions preserve Maintainer authority; they are not an OS path ACL.
    """
    if not isinstance(user_request, str) or not 1 <= len(user_request) <= MAX_TASK:
        raise ValueError('Delegation must contain 1 to 24000 characters')
    match = PREFIX.match(user_request)
    if _SECRET_MARKERS.search(user_request):
        raise ValueError('Remove credentials from the delegated task')
    if not match or not user_request[match.end():].strip():
        raise ValueError('Explicit Dustin instruction required: Delegate Codex: <complete task>')
    if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
        raise ValueError('Invalid delegation request ID')
    root = project_root.resolve(strict=True)
    policy = load_maintainer_policy(root)
    if Path(_git(root, 'rev-parse', '--show-toplevel')).resolve() != root:
        raise ValueError('Configured root is not the repository root')
    git_dir = Path(_git(root, 'rev-parse', '--absolute-git-dir'))
    receipts = root / 'data/private/codex-delegations'
    receipts.mkdir(parents=True, exist_ok=True)
    receipt = receipts / (request_id + '.json')
    task_hash = hashlib.sha256(user_request.encode('utf-8')).hexdigest()
    lock = git_dir / 'josie-delegate.lock'
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return _public({'request_id': request_id, 'status': 'busy',
                        'error': 'Another delegation owns this working tree. Check its receipt; do not retry with a new ID.'})
    process = None
    release_lock = True
    started = time.monotonic()
    result = {'receipt_schema_version': RECEIPT_SCHEMA_VERSION,
              'receipt_id': request_id, 'job_id': request_id, 'request_id': request_id,
              'executor': 'codex-cli', 'task_sha256': task_hash,
              'repository': str(root), 'status': 'starting', 'actions_executed': 0,
              'worktree': str(root), 'receipt_path': str(receipt),
              'hostname': socket.gethostname(), 'timestamp': datetime.now(timezone.utc).isoformat(),
              'command_tool_event_count': 0, 'changed_files': [], 'test_runs': [],
              'output_locations': {}, 'created_commit_sha': None, 'push_performed': False,
              'invocation_attempted': False, 'api_key_used': False,
              'permission_mode': 'workspace-write; no escalation', 'response': ''}
    cached = False
    receipt_existed = receipt.exists()
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            json.dump({'request_id': request_id, 'owner_pid': os.getpid()}, handle)
        if receipt.exists():
            previous = json.loads(receipt.read_text(encoding='utf-8'))
            if previous.get('task_sha256') != task_hash:
                raise ValueError('Request ID already belongs to a different task')
            _validate_receipt(previous, root=root, request_id=request_id)
            cached = True
            return _public({**previous, 'cached': True})
        result['before'] = _snapshot(root)
        executable = find_codex_cli()
        if executable is None:
            result['after'] = _snapshot(root)
            result.update(status='failed', error='Authenticated local Codex CLI not found')
            return _public(result)
        result['status'] = 'running'
        _save(receipt, result)
        output = receipts / (request_id + '.final.txt')
        events = receipts / (request_id + '.events.jsonl')
        errors = receipts / (request_id + '.stderr.txt')
        result['output_locations'] = {
            'final_response': str(output), 'events': str(events), 'stderr': str(errors),
        }
        prompt = (
            'You are an execution-capable local engineering delegate for Dustin and Josie, '
            'not the advisory consult_codex seat. Perform the complete task below in this real '
            'repository, inspect files, edit code, use Git task branches and run development tests. '
            'Use a new maintenance/delegate- task branch before edits; preserve existing changes. '
            'Dustin authorized this task, not unrelated actions. Existing Maintainer Mode is the '
            'authority model; its policy is included below. The consultants_are_advisory_only '
            'rule still applies to consult_codex/consult_gemini, not this explicitly requested '
            'delegation. Never expand your own authority. Protected-path changes require explicit '
            'Dustin authorization in this task. No credential reads/exposure, production data '
            'deletion, historical imports, canonical memory changes, Phase 3, system-wide '
            'destructive commands, security changes, installs, network exposure, remote Git push, '
            'force operations, history rewriting, or recovery tag removal. Do not run nested '
            'delegations. Do not touch data/, logs/, .env files, or credentials. '
            'Do not access the delegation receipts or lock. Sandbox-denied operations must be '
            'reported, never bypassed. No paid API use; the current ChatGPT login is the only seat. '
            'Keep within the exact task. Final response: actions, files changed, tests with actual '
            'results, branch, commit, dirty state, and any failures. Never claim unexecuted work.\n\n'
            f'Repository: {root}\nInitial state: {json.dumps(result["before"])}\n'
            f'Maintainer policy: {json.dumps(policy)}\n\n'
            f'COMPLETE DUSTIN TASK (verbatim):\n{user_request}'
        )
        environment = _clean_environment(_CODEX_REMOVED_ENV)
        for name in list(environment):
            if name.upper().startswith(('OPENAI_', 'AZURE_OPENAI_')):
                environment.pop(name, None)
        args = [str(executable), 'exec', '--ephemeral', '--ignore-user-config',
                '--ignore-rules', '-c', 'default_permissions=":workspace"', '--cd', str(root),
                '--add-dir', str(git_dir), '-c', 'approval_policy="never"',
                '-c', 'forced_login_method="chatgpt"',
                '-c', 'windows.sandbox="elevated"',
                '-c', 'shell_environment_policy.inherit="core"',
                '--json', '--output-last-message', str(output), '-']
        with events.open('w', encoding='utf-8') as stdout, errors.open('w', encoding='utf-8') as stderr:
            process = subprocess.Popen(args, cwd=root, env=environment,
                stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, text=True,
                encoding='utf-8', shell=False, creationflags=_hidden_process_flags())
            result['invocation_attempted'] = True
            result['pid'] = process.pid
            _save(receipt, result)
            try:
                process.communicate(prompt, timeout=TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                # Kill the exact spawned process tree, never an executable-name wildcard.
                if os.name == 'nt':
                    killed = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                        capture_output=True, timeout=30, creationflags=_hidden_process_flags())
                    release_lock = killed.returncode == 0
                else:
                    process.kill()
                process.wait(timeout=15)
                result['status'] = 'timed_out'
                result['error'] = 'Delegation timed out; partial edits may remain. Inspect before retrying.'
                if not release_lock:
                    result['error'] += ' Process-tree termination was not confirmed; lock retained.'
            result['exit_code'] = process.returncode
        result['response'] = (_SECRET_MARKERS.sub('[credential redacted]',
            output.read_text(encoding='utf-8')[:12000]).strip() if output.is_file() else '')
        completed_turn = False
        event_failure = False
        command_events = []
        with events.open(encoding='utf-8') as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                completed_turn |= event.get('type') == 'turn.completed'
                event_failure |= event.get('type') in {'turn.failed', 'error'}
                item = event.get('item') or {}
                if event.get('type') == 'item.completed' and item.get('type') in {'command_execution', 'file_change'}:
                    result['actions_executed'] += 1
                    command_events.append({'type': item.get('type'), 'status': item.get('status'),
                                           'exit_code': item.get('exit_code'),
                                           'command': str(item.get('command') or '')[:400]})
        result['execution_events'] = command_events[-20:]
        result['command_tool_event_count'] = len(command_events)
        result['test_runs'] = [
            {'command': event['command'], 'exit_code': event['exit_code']}
            for event in command_events if event['type'] == 'command_execution'
            and _is_test_command(event['command'])
        ]
        if result['status'] != 'timed_out':
            result['status'] = ('completed' if process.returncode == 0 and completed_turn
                                and not event_failure and result['response'] else 'failed')
            if result['status'] == 'failed':
                result['error'] = _safe_error(errors.read_text(encoding='utf-8')[-1600:] or
                    'Codex did not complete a turn with a final response')
            elif result['actions_executed'] == 0:
                result['status'] = 'no_execution'
                result['error'] = 'Codex returned text but no command/file-change execution events; task success is not claimed.'
        result['after'] = _snapshot(root)
        result['changed_files'] = _changed_files(result['before'], result['after'])
        if result['before']['commit'] != result['after']['commit']:
            result['created_commit_sha'] = result['after']['commit']
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        result.update(status='failed', error=_safe_error(exc))
        if process is not None and process.poll() is None:
            release_lock = False
            result['error'] += '; process may still run, lock retained'
    finally:
        if not cached and not receipt_existed:
            if 'before' in result and 'after' not in result:
                try:
                    result['after'] = _snapshot(root)
                    result['changed_files'] = _changed_files(result['before'], result['after'])
                    if result['before']['commit'] != result['after']['commit']:
                        result['created_commit_sha'] = result['after']['commit']
                except (OSError, subprocess.SubprocessError) as exc:
                    result['error'] = f"{result.get('error') or 'Execution failed'}; final Git snapshot failed: {_safe_error(exc)}"
            result['duration_seconds'] = round(time.monotonic() - started, 2)
            _save(receipt, result)
        if release_lock:
            lock.unlink(missing_ok=True)
    return _public(result)
