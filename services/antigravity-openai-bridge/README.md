# Antigravity-to-Open-WebUI Bridge for Josie

## Overview

This host-side service provides an OpenAI-compatible API (`GET /v1/models`, `POST /v1/chat/completions`) backed directly by the official Google Antigravity CLI (`agy`) on Windows. It enables Open WebUI to interact with official authenticated Gemini models under Josie's existing Google AI Pro subscription without using LiteLLM, unofficial OAuth proxies, or paid API keys.

## Features & Constraints

- **Endpoints Supported:**
  - `GET /health`, `GET /v1/health`: Unauthenticated health check.
  - `GET /v1/models`, `GET /models`: Model discovery.
  - `POST /v1/chat/completions`, `POST /chat/completions`: Chat completions supporting both non-streaming (`stream: false`) and SSE streaming (`stream: true`).
- **Model Slugs:**
  - `josie-antigravity-flash` -> `gemini-3.8-flash-high`
  - `josie-antigravity-pro`   -> `gemini-3.1-pro-high`
- **Security & Sandboxing:**
  - Workspace directory is hardcoded to `D:\Josie`. Arbitrary cwd is forbidden.
  - Model selection is restricted to the two validated Josie models; arbitrary model names are rejected with HTTP 400.
  - Invokes only the official `agy.exe` executable.
  - Never uses `--dangerously-skip-permissions`.
  - Concurrency is strictly limited to 1 job. Overlapping requests are rejected with HTTP 429 (`busy`).
  - Paid credentials and API keys are scrubbed from the child environment (`GEMINI_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`, etc.).
  - Bounded prompt rendering: extracts the latest user prompt and minimal context, enforcing bounded size limits.
  - Binds strictly to `127.0.0.1:8792`. Docker Desktop's bridge allows Open WebUI containers to access it via `http://host.docker.internal:8792` without exposing the port to the LAN or Tailscale.

## Running

### Manual Execution:
```powershell
python D:\Josie\services\antigravity-openai-bridge\server.py --host 127.0.0.1 --port 8792
```

### Automated Testing:
```powershell
python D:\Josie\services\antigravity-openai-bridge\test_bridge.py
```
