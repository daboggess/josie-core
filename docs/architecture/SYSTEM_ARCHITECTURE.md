# System Architecture

```text
Dustin / private phone interface
        |
Authenticated Open WebUI (Tailscale only)
        |
Read-only status + record-only proposal bridge
        |
Josie Core: Constitution, authority, policy, memory, audit, routing
        |                         |
Local reasoning engine            Manual zero-spend witness/model handoffs
(replaceable Ollama model)         (Sophie / Bernie)
        |
Allowlisted jobs / n8n workflows / isolated read-only browser worker
        |
Verification, audit, memory proposal, human gate
```

The identity/control plane is conceptually above replaceable models and n8n.
No model connects directly to host shell execution. External content is
untrusted data. The current browser pilot is read-only, exact-URL allowlisted,
loopback-only, and unable to submit forms, persist downloads, upload files, use
authenticated cookies, or access private/Tailscale ranges.
