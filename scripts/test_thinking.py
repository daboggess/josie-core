import json
import sys
from urllib.request import build_opener, ProxyHandler, Request

opener = build_opener(ProxyHandler({}))

experiments = [
    ("Default (no flags)", {}),
    ("options.think = False", {"options": {"think": False}}),
    ("options.thinking = False", {"options": {"thinking": False}}),
    ("think = False (root)", {"think": False}),
    ("system: Do not think. Output directly.", {
        "messages": [
            {"role": "system", "content": "You are a direct operational model. Do not include thinking or internal monologue. Output final response directly."},
            {"role": "user", "content": "What is 2 + 2? Answer with only the number."}
        ]
    })
]

for label, extra in experiments:
    payload = {
        "model": "qwen3.5:9b",
        "messages": extra.get("messages", [{"role": "user", "content": "What is 2 + 2? Answer with only the number."}]),
        "stream": False,
        "options": {"temperature": 0, "num_predict": 128}
    }
    if "options" in extra:
        payload["options"].update(extra["options"])
    for k, v in extra.items():
        if k not in ("options", "messages"):
            payload[k] = v
            
    req = Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        res = json.loads(opener.open(req, timeout=30).read().decode("utf-8"))
        msg = res.get("message", {})
        has_thinking = bool(msg.get("thinking"))
        content = msg.get("content", "").strip()
        thinking_len = len(msg.get("thinking", ""))
        print(f"[{label}]")
        print(f"  Content: {repr(content)}")
        print(f"  Has thinking: {has_thinking} (len: {thinking_len})")
        print(f"  Eval tokens: {res.get('eval_count')}")
    except Exception as e:
        print(f"[{label}] ERROR: {e}")
