"""Opt-in Qwen3 CPU/GPU comparison; reuse existing Windows metric helpers."""
import argparse
import hashlib
import json
import sys
import threading
import time
from pathlib import Path
from urllib.request import Request, ProxyHandler, build_opener

ROOT = Path('D:/Josie')
sys.path.insert(0, str(ROOT / 'scripts'))
from measure_pre_gpu import sample, paging

MODEL = 'josie-qual-qwen3:8b-32k'
PROMPT = 'Review this Python function: def add(a, b): return a + b. State what add(2, 3) returns and give one deterministic assert statement that tests it. Be concise. Do not use tools or claim to inspect files.'
# Match the engineering agent temperature and installed context. Seed and output
# cap make a bounded comparison, not a model configuration change.
OPTIONS = {'temperature': 0, 'seed': 42, 'num_ctx': 32768, 'num_predict': 256}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    if not parser.parse_args().run:
        print('No inference. Use --run only with no active chats/jobs.')
        return
    if (ROOT / '.git/josie-delegate.lock').exists():
        raise RuntimeError('Active delegation lock; stopped')
    opener = build_opener(ProxyHandler({}))
    base = 'http://127.0.0.1:11434'
    def get(path):
        with opener.open(base + path, timeout=5) as r:
            return json.load(r)
    if get('/api/ps')['models']:
        raise RuntimeError('Resident model; wait for normal expiry, do not evict')
    definition = next(m for m in get('/api/tags')['models'] if m['name'] == MODEL)
    page_before = paging()
    before = sample()
    samples = [before]
    stop = threading.Event()
    def monitor():
        while not stop.wait(.25):
            samples.append(sample())
    worker = threading.Thread(target=monitor, daemon=True)
    worker.start()
    first_content = first_event = None
    final = None
    content = []
    started_at = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    start = time.perf_counter()
    request = Request(base + '/api/chat', data=json.dumps({'model': MODEL,
        'messages': [{'role': 'user', 'content': PROMPT}], 'stream': True,
        'options': OPTIONS}).encode(), headers={'Content-Type': 'application/json'})
    error = None
    try:
        with opener.open(request, timeout=600) as response:
            for line in response:
                if time.perf_counter() - start > 600:
                    raise TimeoutError('600s bound exceeded')
                event = json.loads(line)
                if event.get('error'):
                    raise RuntimeError('Ollama inference error')
                message = event.get('message', {})
                if (message.get('thinking') or message.get('content')) and first_event is None:
                    first_event = time.perf_counter() - start
                if message.get('content'):
                    if first_content is None:
                        first_content = time.perf_counter() - start
                    content.append(message['content'])
                if event.get('done'):
                    final = event
                    break
    except Exception as exc:
        error = type(exc).__name__
    finally:
        elapsed = time.perf_counter() - start
        stop.set()
        worker.join(2)
    after = sample()
    samples.append(after)
    final = final or {}
    duration = final.get('eval_duration', 0) / 1e9
    ticks = after['total_cpu_ticks'] - before['total_cpu_ticks']
    result = dict(started_at=started_at, model=MODEL, model_digest=definition['digest'],
        model_bytes=definition['size'], prompt=PROMPT, options=OPTIONS,
        wall_response_seconds=elapsed, first_content_seconds=first_content,
        first_generated_chunk_seconds=first_event, output_tokens=final.get('eval_count'),
        tokens_per_second=final.get('eval_count', 0)/duration if duration else None,
        load_seconds=final.get('load_duration',0)/1e9,
        prompt_eval_seconds=final.get('prompt_eval_duration',0)/1e9,
        generation_seconds=duration, done_reason=final.get('done_reason'),
        ram_before_bytes=before['used_ram_bytes'],
        ram_peak_bytes=max(s['used_ram_bytes'] for s in samples),
        ram_after_bytes=after['used_ram_bytes'], sample_count=len(samples),
        cpu_average_percent=100*(1-(after['idle']-before['idle'])/ticks),
        pagefile_before=page_before, pagefile_after=paging(),
        resident_after=get('/api/ps')['models'], error=error,
        final_present=bool(final), response=''.join(content),
        response_sha256=hashlib.sha256(''.join(content).encode()).hexdigest())
    print(json.dumps(result, indent=2))
    if error or not final:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
