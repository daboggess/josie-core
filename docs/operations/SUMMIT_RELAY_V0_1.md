# Summit Relay v0.1 — direct Playwright transport

Summit Relay uses Python Playwright and installed Google Chrome directly. The
earlier unpacked-extension transport is abandoned and is not part of this path.

`josie/summit_relay.py` remains the deterministic state machine: attributed
envelopes, exactly three strategic rounds, exact-response checks, safe stop,
TEAM ALIGNED result, and append-only receipts. `josie/summit_browser.py` owns
browser launch, authentication checks, DOM send/capture for ChatGPT and Gemini,
and final Josie delivery through Open WebUI's verified loopback HTTP interface.
Open WebUI is never browser-automated.

The browser runs headless with a dedicated profile at
`data/private/summit-browser-profile`. It never inspects, copies, decrypts, or
automates Dustin's primary Chrome profile. The initializer creates only a clean
dedicated directory. Chrome launches with extensions disabled.

## Remote commands

From `C:\Josie`:

```powershell
scripts\Manage-JosieSummitRelay.ps1 -Action InitializeProfile
scripts\Manage-JosieSummitRelay.ps1 -Action Probe
scripts\Manage-JosieSummitRelay.ps1 -Action RunAcceptance
```

`InitializeProfile` creates an empty dedicated Chrome data directory. `Probe`
opens ChatGPT and Gemini headlessly, verifies the local Josie API, reports authentication/composer
state, sends nothing, and writes a minimized preflight receipt. `RunAcceptance` is the only command
that sends; it runs the fixed harmless ChatGPT → Gemini → ChatGPT → Open WebUI
exchange and then exits.

The Josie handoff uses `http://127.0.0.1:3000/api/chat/completions` followed by
`/api/chat/completed`, model `josie-qwen3-8b:1.0`, the existing exact-response
filter, an empty tool list, and the existing short-lived owner-token mechanism.
Tokens are held only in process memory and are never logged.

Any login page, missing composer/send control, timeout, response mismatch, or
browser/API failure stops the run. There is no extension, CORS service, CDP,
database, scheduler, authentication workaround, model-based transport, or
autonomous routing.

If the dedicated profile is not authenticated, the run stops with
`AUTH_REQUIRED: CHATGPT`, `AUTH_REQUIRED: GEMINI`, or both. The only supported
bootstrap is one human interactive login directly in that dedicated profile.
