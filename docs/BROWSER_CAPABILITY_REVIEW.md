# Read-only research pilot

## Approved decision

Dustin approved a bounded Advantech research pilot on 2026-08-09. It expires
automatically after 2026-09-08 unless reviewed and deliberately renewed.

This is not general browser automation. It is an authenticated, local-only
official-source connector with two exact hosts and two exact document paths:

- `www.advantech.com/en-us/support/details/manual`
- `advdownload.advantech.com/productfile/Downloadfile4/1-1E13MJV/AIMB-205_User_Manual_Ed.1.pdf`

The HTML support page can be extracted. The PDF is an approved destination,
but its content type is intentionally rejected by the current HTML-only worker;
the worker does not save it as a download.

## Enforced boundary

- HTTPS port 443 only; default deny everywhere else.
- Exact full-URL, host, path, and query checks before the connection and after
  every redirect; arbitrary query text cannot be sent.
- DNS is resolved by the connector and loopback, private, link-local,
  documentation, multicast, and Tailscale/CGNAT ranges are rejected.
- One request at a time and no more than six requests per minute.
- One MiB response limit, 20,000-character output limit, and 15-second timeout.
- HTML, plain text, and XHTML only.
- Scripts, forms, hidden blocks, frames, embedded objects, and markup are
  removed before text is returned.
- All returned page content remains explicitly untrusted.
- No JavaScript, cookies, website credentials, login, form entry, download
  storage, upload, purchase, message, or model-direct access.
- The connector is bound to `127.0.0.1:3010`, requires a protected bearer
  credential stored outside Git on D:, runs read-only with all Linux
  capabilities dropped, and has CPU, memory, and process limits.

The local model and Open WebUI have no route to this connector. An attended
local operator must invoke the bounded CLI command. Output is not automatically
added to memory or treated as instructions.

## Start, stop, and recovery

Start and revalidate the pilot:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Josie\scripts\Start-JosieResearchPilot.ps1
```

Emergency stop:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Josie\scripts\Stop-JosieResearchPilot.ps1
```

Check the policy without network activity:

```powershell
C:\Josie\.venv\Scripts\python.exe C:\Josie\core.py browser status
```

The pilot fails closed if its policy, protected credential, container, expiry,
DNS validation, allowlist, or response limits are unavailable.

## Expansion rule

Adding any hostname, path, login, credential, file type, retained content,
form, message, upload, download, or model access requires a new human decision.
The current approval cannot be reused to expand the scope.
