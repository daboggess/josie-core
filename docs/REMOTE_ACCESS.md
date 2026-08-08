# Private phone and laptop access

Open WebUI is available only to devices signed into Dustin's Tailscale network:

`https://refurb.tail0ab4d2.ts.net/`

On a phone or laptop, install the official Tailscale client, sign in to the same
tailnet, then open the HTTPS address and use the local Open WebUI owner account.
The Open WebUI password is not the Tailscale or Google password.

## Boundaries

- Tailscale reports the mapping as `tailnet only`.
- Public Tailscale Funnel is disabled.
- Only Open WebUI (`127.0.0.1:3000`) is proxied.
- n8n (`127.0.0.1:5678`) remains available only on Josie.
- The browser worker (`127.0.0.1:3010`) remains local and execution-locked.
- Open WebUI sign-ups and cloud-provider APIs are disabled.

## Verify

`C:\Program Files\Tailscale\tailscale.exe serve status`

The output must contain `tailnet only` and proxy only to
`http://127.0.0.1:3000`.

## Disable immediately

`C:\Program Files\Tailscale\tailscale.exe serve --https=443 off`

This removes private remote access without deleting Open WebUI data.
