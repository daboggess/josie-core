"""Thin, local-only OpenCode/Ollama adapter. No Codex runtime dependency."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.request import urlopen
from urllib.parse import urlparse
from .maintainer import load_maintainer_policy

TIMEOUT = 900
DEFAULT_EXE = Path('I:/Josie-Storage/apps/OpenCode/1.18.23/opencode.exe')
THERMAL_CONFIG = Path('config/local-code-thermal.json')
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{7,95}')
PREFIX = re.compile(r'\A\s*Delegate[ _]+Local[ _]+Code\s*:\s*', re.I)


def explicit_task(user_request):
    """The public bridge requires Dustin's explicit trigger, not model inference."""
    if not isinstance(user_request, str):
        raise ValueError('Explicit Delegate Local Code: instruction required')
    match = PREFIX.match(user_request)
    if not match or not user_request[match.end():].strip():
        raise ValueError('Explicit Delegate Local Code: <task> instruction required')
    return user_request[match.end():]


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True,
        capture_output=True, text=True, encoding='utf-8', timeout=30,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout.strip()


def fingerprint(root):
    """Hash only Git-visible regular files, never ignored production payloads."""
    names = git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard').split('\0')
    result = {}
    for name in names:
        if not name:
            continue
        path = root / name
        if path.is_file() and not path.is_symlink():
            result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def parse_events(text):
    tools, assistant, errors, types, malformed = [], [], [], {}, 0
    last_stop = False
    session = None
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError('event is not an object')
        except ValueError:
            malformed += 1
            continue
        kind = event.get('type', 'unknown')
        if not isinstance(kind, str) or not isinstance(event.get('part', {}), dict):
            malformed += 1
            continue
        types[kind] = types.get(kind, 0) + 1
        session = event.get('sessionID') or session
        part = event.get('part') or {}
        if kind == 'tool_use':
            state = part.get('state') or {}
            if not isinstance(state, dict) or not isinstance(state.get('metadata', {}), dict):
                malformed += 1
                continue
            tools.append({'tool': part.get('tool'), 'status': state.get('status'),
                'input': state.get('input'), 'output': str(state.get('output', ''))[-2000:],
                'exit_code': (state.get('metadata') or {}).get('exit'),
                'error': state.get('error')})
            assistant = []  # pre-tool commentary is not the final answer
            last_stop = False
        elif kind == 'text':
            assistant.append(str(part.get('text') or ''))
        elif kind == 'step_finish':
            last_stop = part.get('reason') == 'stop'
        elif kind == 'error':
            errors.append(event.get('error') or event)
    return {'tools': tools, 'response': '\n'.join(assistant)[-8000:],
            'final_observed': last_stop and bool(assistant), 'event_counts': types,
            'malformed_lines': malformed, 'event_errors': errors, 'session_id': session,
            'actions_executed': sum(t['status'] == 'completed' for t in tools)}


def environment(root, config):
    env = dict(os.environ)
    for key in list(env):
        if key.upper().startswith(('OPENAI_', 'ANTHROPIC_', 'GEMINI_', 'GOOGLE_API_')):
            env.pop(key)
    state = root / 'data/private/local-code-runtime'
    for kind in ('CONFIG', 'DATA', 'CACHE', 'STATE'):
        folder = state / kind.lower()
        folder.mkdir(parents=True, exist_ok=True)
        env['XDG_' + kind + '_HOME'] = str(folder)
    env['OPENCODE_CONFIG_CONTENT'] = json.dumps(config)
    env.update(OPENCODE_DISABLE_AUTOUPDATE='true', OPENCODE_DISABLE_MODELS_FETCH='true',
        OPENCODE_DISABLE_DEFAULT_PLUGINS='true', OPENCODE_DISABLE_LSP_DOWNLOAD='true',
        OPENCODE_DISABLE_CLAUDE_CODE='true', OPENCODE_GIT_BASH_PATH='C:/Program Files/Git/bin/bash.exe')
    return env


def load_thermal_policy(root):
    path = root / THERMAL_CONFIG
    policy = json.loads(path.read_text(encoding='utf-8'))
    numeric = ('warning_c', 'block_new_job_c', 'terminate_active_c', 'critical_c',
        'monitor_interval_seconds', 'sustained_over_limit_samples', 'hysteresis_c',
        'telemetry_failure_samples', 'query_timeout_seconds')
    if any(not isinstance(policy.get(key), (int, float)) for key in numeric):
        raise ValueError('Thermal safety configuration contains invalid numeric values')
    if not (0 < policy['warning_c'] < policy['block_new_job_c']
            < policy['terminate_active_c'] < policy['critical_c'] < 100):
        raise ValueError('Thermal safety thresholds must be strictly increasing and below 100 C')
    if not (5 <= policy['monitor_interval_seconds'] <= 15
            and 2 <= policy['sustained_over_limit_samples'] <= 6
            and 1 <= policy['hysteresis_c'] <= 10
            and 1 <= policy['telemetry_failure_samples'] <= 6
            and 1 <= policy['query_timeout_seconds'] <= 15):
        raise ValueError('Thermal safety timing or hysteresis values are outside safe bounds')
    if not isinstance(policy.get('gpu_index'), int) or policy['gpu_index'] < 0:
        raise ValueError('Thermal safety GPU index is invalid')
    return policy


def resolve_nvidia_smi(policy):
    configured = policy.get('nvidia_smi', 'auto')
    if configured != 'auto':
        candidates = [Path(configured)]
    else:
        windows = Path(os.environ.get('SystemRoot', 'C:/Windows'))
        candidates = [windows / 'System32/nvidia-smi.exe',
            Path('C:/Program Files/NVIDIA Corporation/NVSMI/nvidia-smi.exe')]
        discovered = shutil.which('nvidia-smi.exe') or shutil.which('nvidia-smi')
        if discovered:
            candidates.append(Path(discovered))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise RuntimeError('THERMAL TELEMETRY UNAVAILABLE: nvidia-smi executable not found')


def read_gpu_telemetry(policy):
    exe = resolve_nvidia_smi(policy)
    fields = ('name', 'temperature.gpu', 'utilization.gpu', 'memory.used',
        'memory.total', 'power.draw')
    command = [str(exe), f"--id={policy['gpu_index']}",
        '--query-gpu=' + ','.join(fields), '--format=csv,noheader,nounits']
    completed = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
        timeout=policy['query_timeout_seconds'],
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if completed.returncode:
        raise RuntimeError('THERMAL TELEMETRY UNAVAILABLE: nvidia-smi exit '
            + str(completed.returncode) + ': ' + completed.stderr.strip()[-500:])
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError('THERMAL TELEMETRY UNAVAILABLE: expected one GPU CSV row')
    values = [value.strip() for value in lines[0].split(',')]
    if len(values) != len(fields):
        raise RuntimeError('THERMAL TELEMETRY UNAVAILABLE: invalid GPU CSV field count')
    try:
        temperature = float(values[1])
        utilization = float(values[2])
        memory_used = float(values[3])
        memory_total = float(values[4])
        power_value = values[5].lower()
        power = None if 'n/a' in power_value or 'not supported' in power_value else float(values[5])
    except ValueError as exc:
        raise RuntimeError('THERMAL TELEMETRY UNAVAILABLE: non-numeric GPU CSV value') from exc
    if not (0 <= temperature < 120 and 0 <= utilization <= 100
            and 0 <= memory_used <= memory_total and memory_total > 0
            and (power is None or power >= 0)):
        raise RuntimeError('THERMAL TELEMETRY UNAVAILABLE: implausible GPU values')
    return {'timestamp': datetime.now(timezone.utc).isoformat(), 'gpu_name': values[0],
        'temperature_c': temperature, 'utilization_percent': utilization,
        'memory_used_mib': memory_used, 'memory_total_mib': memory_total,
        'power_draw_w': power, 'command': command}


def thermal_receipt(policy):
    return {'profile': policy.get('profile'), 'gpu_index': policy['gpu_index'],
        'warning_c': policy['warning_c'], 'block_new_job_c': policy['block_new_job_c'],
        'terminate_active_c': policy['terminate_active_c'], 'critical_c': policy['critical_c'],
        'monitor_interval_seconds': policy['monitor_interval_seconds'],
        'sustained_over_limit_samples': policy['sustained_over_limit_samples'],
        'hysteresis_c': policy['hysteresis_c'],
        'telemetry_failure_samples': policy['telemetry_failure_samples'],
        'preflight': None, 'samples': [], 'sample_count': 0, 'telemetry_failures': [],
        'start_temperature_c': None, 'max_temperature_c': None,
        'warning_observed': False, 'intervention': 'none', 'reason': None,
        'process_tree_termination_confirmed': None}


def record_thermal_sample(state, sample, *, phase):
    recorded = {**sample, 'phase': phase}
    state['samples'].append(recorded)
    state['sample_count'] = len(state['samples'])
    temperature = sample['temperature_c']
    if state['start_temperature_c'] is None:
        state['start_temperature_c'] = temperature
    state['max_temperature_c'] = max(
        temperature, state['max_temperature_c'] if state['max_temperature_c'] is not None else temperature)
    state['warning_observed'] = state['warning_observed'] or temperature >= state['warning_c']
    return recorded


def terminate_process_tree(process):
    killed = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
        capture_output=True, timeout=30)
    if killed.returncode:
        return False
    process.wait(timeout=10)
    return True


def _save(path, result):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, indent=2), encoding='utf-8')
    temporary.replace(path)


def public(result):
    result = dict(result)
    thermal = result.get('thermal_safety') or {}
    thermal_line = (
        f"Thermal safety: {thermal.get('intervention', 'unavailable')} | "
        f"Start: {thermal.get('start_temperature_c')} C | "
        f"Max: {thermal.get('max_temperature_c')} C | "
        f"Active limit: {thermal.get('terminate_active_c')} C\n"
    )
    result['assistant_message'] = (
        'JOSIE LOCAL CODE — ACTUAL RESULT\n'
        f"Job: {result['request_id']}\nStatus: {result['status']}\n"
        f"Runtime/model: OpenCode / {result.get('model', 'unavailable')}\n"
        f"Completed tool events: {result.get('actions_executed', 0)}\n"
        f"Exit: {result.get('exit_code')} | Timeout: {result.get('timed_out', False)}\n"
        f"Changed files: {', '.join(result.get('changed_files', [])) or 'none verified'}\n"
        f"{thermal_line}"
        f"Error: {result.get('error') or 'none'}\n\n"
        f"{result.get('response') or 'No final agent response.'}"
    )
    return result


def local_code_status(root, request_id):
    if not isinstance(request_id, str) or not ID.fullmatch(request_id):
        raise ValueError('Invalid local-code job ID')
    receipt = root / 'data/private/local-code-jobs' / (request_id + '.json')
    return public(json.loads(receipt.read_text()) if receipt.is_file() else
                  {'request_id': request_id, 'status': 'not_found'})


def delegate_local_code(task, acceptance_criteria, *, request_id, project_root):
    if not isinstance(task, str) or not 1 <= len(task.strip()) <= 16000:
        raise ValueError('Task must contain 1 to 16000 characters')
    if not isinstance(acceptance_criteria, str) or len(acceptance_criteria) > 4000:
        raise ValueError('Acceptance criteria must be text, at most 4000 characters')
    if not isinstance(request_id, str) or not ID.fullmatch(request_id):
        raise ValueError('Invalid local-code job ID')
    root = Path(project_root).resolve()
    receipts = root / 'data/private/local-code-jobs'
    receipts.mkdir(parents=True, exist_ok=True)
    receipt = receipts / (request_id + '.json')
    digest = hashlib.sha256((task + '\0' + acceptance_criteria).encode()).hexdigest()
    if receipt.exists():
        old = json.loads(receipt.read_text())
        if old.get('task_sha256') != digest:
            raise ValueError('Job ID already used for a different task')
        return public({**old, 'cached': True})
    result = {'request_id': request_id, 'task': task, 'acceptance_criteria': acceptance_criteria,
              'task_sha256': digest, 'repository': str(root), 'status': 'starting',
              'started_at': datetime.now(timezone.utc).isoformat(), 'actions_executed': 0,
              'timed_out': False, 'exit_code': None, 'changed_files': [],
              'test_result': 'not independently verified; inspect tool outputs', 'cloud_required': False}
    lock = None
    before = None
    process = None
    event_path = None
    stderr_path = None
    started = time.monotonic()
    save_receipt = True
    thermal_terminated = False
    try:
        exe = Path(os.environ.get('JOSIE_OPENCODE_EXE') or shutil.which('opencode') or DEFAULT_EXE)
        if not exe.is_file():
            raise RuntimeError('OpenCode is not installed')
        policy = load_maintainer_policy(root)
        config = json.loads((root / 'config/opencode-local.json').read_text())
        thermal_policy = load_thermal_policy(root)
        result['thermal_safety'] = thermal_receipt(thermal_policy)
        model = config['model']
        url = config['provider']['ollama']['options']['baseURL']
        parsed = urlparse(url)
        if config.get('enabled_providers') != ['ollama'] or not model.startswith('ollama/') or parsed.hostname not in {'localhost', '127.0.0.1', '::1'}:
            raise ValueError('This adapter requires a loopback Ollama-only provider')
        endpoint = url.rsplit('/v1', 1)[0]
        result.update(model=model, ollama_endpoint=endpoint)
        try:
            with urlopen(endpoint + '/api/version', timeout=5) as response:
                result['ollama_version'] = json.load(response)['version']
            with urlopen(endpoint + '/api/tags', timeout=5) as response:
                models = json.load(response)['models']
        except Exception as exc:
            raise RuntimeError('Ollama unavailable: ' + str(exc)) from exc
        if model.split('/', 1)[1] not in {m['name'] for m in models}:
            raise RuntimeError('Configured local model is unavailable')
        try:
            preflight = read_gpu_telemetry(thermal_policy)
        except Exception as exc:
            reason = 'THERMAL PREFLIGHT BLOCKED: ' + str(exc)
            result['thermal_safety'].update(intervention='preflight_blocked', reason=reason)
            raise RuntimeError(reason) from exc
        result['thermal_safety']['preflight'] = record_thermal_sample(
            result['thermal_safety'], preflight, phase='preflight')
        if preflight['temperature_c'] >= thermal_policy['block_new_job_c']:
            reason = ('THERMAL PREFLIGHT BLOCKED: GPU temperature '
                f"{preflight['temperature_c']} C reached the new-job limit "
                f"{thermal_policy['block_new_job_c']} C")
            result['thermal_safety'].update(intervention='preflight_blocked', reason=reason)
            raise RuntimeError(reason)
        if Path(git(root, 'rev-parse', '--show-toplevel')).resolve() != root:
            raise ValueError('Workspace must be the repository root')
        git_dir = Path(git(root, 'rev-parse', '--absolute-git-dir'))
        # Share the existing execution lock, without modifying the frozen Codex adapter.
        candidate = git_dir / 'josie-delegate.lock'
        try:
            handle = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            save_receipt = False  # never overwrite the active owner's receipt
            raise RuntimeError('Repository already has an active delegated job')
        lock = candidate
        with os.fdopen(handle, 'w') as stream:
            json.dump({'request_id': request_id, 'owner_pid': os.getpid(), 'runtime': 'opencode'}, stream)
        if receipt.exists():
            save_receipt = False
            previous = json.loads(receipt.read_text(encoding='utf-8'))
            if previous.get('task_sha256') != digest:
                raise ValueError('Job ID already used for a different task')
            return public({**previous, 'cached': True})
        before = fingerprint(root)
        result['before'] = {'branch': git(root, 'branch', '--show-current'),
                            'commit': git(root, 'rev-parse', 'HEAD'), 'status': git(root, 'status', '--short')}
        env = environment(root, config)
        result['runtime_version'] = subprocess.run([str(exe), '--version'], env=env,
            capture_output=True, text=True, timeout=30, check=True).stdout.strip()
        prompt = (task + '\nAcceptance criteria: ' + acceptance_criteria
            + '\nMaintainer authority: routine task-authorized repo edits and tests are allowed. '
            'No publishing, credential access, system changes or historical/canonical data changes. '
            'These protected paths require explicit task authorization: '
            + json.dumps(policy.get('write', {}).get('protected_paths', [])))
        event_path = receipts / (request_id + '.events.jsonl')
        stderr_path = receipts / (request_id + '.stderr.txt')
        result.update(status='running', event_log=str(event_path), stderr_log=str(stderr_path))
        _save(receipt, result)
        with event_path.open('w', encoding='utf-8') as out, stderr_path.open('w', encoding='utf-8') as err:
            process = subprocess.Popen([str(exe), 'run', '--format', 'json', '--agent', 'josie-local',
                '--model', model, prompt], cwd=root, env=env, stdin=subprocess.DEVNULL,
                stdout=out, stderr=err, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            result['pid'] = process.pid
            _save(receipt, result)
            deadline = time.monotonic() + TIMEOUT
            over_limit = 0
            telemetry_failures = 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    result['timed_out'] = True
                    if not terminate_process_tree(process):
                        lock = None  # retain the on-disk lock if termination was not confirmed
                    break
                try:
                    result['exit_code'] = process.wait(timeout=min(
                        thermal_policy['monitor_interval_seconds'], remaining))
                    break
                except subprocess.TimeoutExpired:
                    pass
                try:
                    sample = read_gpu_telemetry(thermal_policy)
                    record_thermal_sample(result['thermal_safety'], sample, phase='active')
                    telemetry_failures = 0
                except Exception as exc:
                    telemetry_failures += 1
                    result['thermal_safety']['telemetry_failures'].append({
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'consecutive': telemetry_failures, 'error': str(exc)[:500]})
                    if telemetry_failures < thermal_policy['telemetry_failure_samples']:
                        _save(receipt, result)
                        continue
                    reason = ('THERMAL SAFETY TERMINATED JOB: GPU telemetry failed '
                        f"{telemetry_failures} consecutive times")
                    result['thermal_safety'].update(intervention='terminated', reason=reason)
                    result['error'] = reason
                    thermal_terminated = True
                else:
                    temperature = sample['temperature_c']
                    if temperature >= thermal_policy['critical_c']:
                        reason = ('THERMAL SAFETY TERMINATED JOB: GPU temperature '
                            f"{temperature} C reached the critical limit "
                            f"{thermal_policy['critical_c']} C")
                        result['thermal_safety'].update(intervention='terminated', reason=reason)
                        result['error'] = reason
                        thermal_terminated = True
                    elif temperature >= thermal_policy['terminate_active_c']:
                        over_limit += 1
                        if over_limit >= thermal_policy['sustained_over_limit_samples']:
                            reason = ('THERMAL SAFETY TERMINATED JOB: GPU temperature remained at or above '
                                f"{thermal_policy['terminate_active_c']} C for {over_limit} samples")
                            result['thermal_safety'].update(intervention='terminated', reason=reason)
                            result['error'] = reason
                            thermal_terminated = True
                    elif temperature <= (thermal_policy['terminate_active_c']
                            - thermal_policy['hysteresis_c']):
                        over_limit = 0
                _save(receipt, result)
                if thermal_terminated:
                    termination_confirmed = terminate_process_tree(process)
                    result['thermal_safety']['process_tree_termination_confirmed'] = termination_confirmed
                    if not termination_confirmed:
                        lock = None
                        result['error'] += '; process-tree termination was not confirmed'
                    result['exit_code'] = process.poll()
                    break
        result.update(parse_events(event_path.read_text(encoding='utf-8', errors='replace')))
        result['stderr'] = stderr_path.read_text(encoding='utf-8', errors='replace')[-4000:]
        good = (result['exit_code'] == 0 and not result['timed_out'] and not thermal_terminated
                and result['final_observed']
                and result['actions_executed'] > 0 and not result['event_errors']
                and not result['malformed_lines']
                and all(t['status'] == 'completed' and t['exit_code'] in (None, 0) for t in result['tools']))
        result['status'] = 'completed' if good else 'failed'
        if not good and not result.get('error'):
            result['error'] = 'Runtime did not complete with successful tool activity and a final response; inspect events/stderr.'
    except Exception as exc:
        result.update(status='failed', error=str(exc)[:2000])
    finally:
        if event_path and event_path.is_file():
            result.update(parse_events(event_path.read_text(encoding='utf-8', errors='replace')))
            result['stderr'] = stderr_path.read_text(encoding='utf-8', errors='replace')[-4000:] if stderr_path.is_file() else ''
            result['test_result'] = [t for t in result['tools'] if
                re.search(r'\b(unittest|pytest)\b', str(t.get('input')))] or 'No test command observed'
        if before is not None:
            try:
                after = fingerprint(root)
                result['changed_files'] = sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))
                result['after'] = {'branch': git(root, 'branch', '--show-current'),
                                   'commit': git(root, 'rev-parse', 'HEAD'), 'status': git(root, 'status', '--short')}
            except Exception as exc:
                result.update(status='failed', error='Post-run inspection failed: ' + str(exc))
        result['duration_seconds'] = round(time.monotonic() - started, 2)
        if save_receipt:
            _save(receipt, result)
        if lock and (process is None or process.poll() is not None):
            lock.unlink(missing_ok=True)
    return public(result)
