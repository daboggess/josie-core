# CHAPTER 21: Containerization, Network Isolation, and Tailscale

> *"A sovereign AI assistant does not expose ports to the wild internet. She sits behind cryptographic wireguard mesh tunnels, binds to loopback interfaces, and treats external networks with unwavering zero-trust discipline."*  
> — Infrastructure Security Standard (`CON-0012`)

---

## § 21.1 The Localhost Binding Invariant

The first line of physical defense in Project Josie is the **Loopback Binding Invariant**. 

No runtime service—neither Ollama, nor the SQLite data layer, nor internal administrative webhooks—is permitted to bind to `0.0.0.0` (all network interfaces). Every listening daemon is strictly bound to `127.0.0.1` (localhost):

```
       [ LOCAL HOST BOUNDARY (127.0.0.1) ]
  +-----------------------------------------------+
  |  +----------------+     +------------------+  |       [ PUBLIC INTERNET ]
  |  | Ollama (11434) | <-> | Josie Core App   |  |              X
  |  +----------------+     +------------------+  |              |
  |          ^                      ^             |     NO DIRECT INGRESS
  |          |                      |             |     NO OPEN PORTS (80/443)
  |  +----------------+     +------------------+  |              |
  |  | SQLite Engine  | <-> | Tailscale Mesh   | <====== Encrypted WireGuard
  |  +----------------+     +------------------+  |       (Dustin's Devices Only)
  +-----------------------------------------------+
```

Any port scan directed against the physical machine from the local LAN or the wider internet detects zero open listening ports. The system is completely invisible to casual network reconnaissance.

---

## § 21.2 Docker Containerization and Worktree Jails

To prevent local models or sub-workers from executing arbitrary or destructive system calls on the host machine, external adapters and experimental tooling run within isolated containerized sandboxes:
- **Filesystem Isolation:** Containers mount only read-only scratch directories or explicitly passed repository worktrees. The host's root drive, personal documents, and live production databases are completely inaccessible.
- **Resource Limits:** Docker containers are configured with hard CPU quotas (`cpus: 4.0`) and RAM caps (`memory: 8g`), preventing rogue compilation loops or memory leaks from hanging the host operating system.
- **No Root Execution:** Containerized worker processes run under dedicated unprivileged system users (`uid=10001`), ensuring that container escape vulnerabilities cannot gain administrative privileges on the industrial host.

---

## § 21.3 Secure Remote Access via Tailscale Mesh Network

While Josie lives physically on the Advantech rig in the shop, Dustin requires secure access whether working in the office, traveling, or operating from mobile devices.

Rather than punching holes in shop routers using port forwarding or dynamic DNS—both of which invite continuous botnet scanning and brute-force attacks—Project Josie uses **Tailscale**.

Tailscale creates a secure, point-to-point WireGuard mesh network overlay:
1. **Mutual Cryptographic Identity:** Every node on the Tailscale mesh ("tailnet") possesses a unique cryptographic public/private keypair. Only Dustin's explicitly authenticated personal hardware (laptop, phone, workstation) can communicate with the Advantech host.
2. **End-to-End Encryption:** Traffic traveling between Dustin's mobile devices and Josie is encrypted using state-of-the-art WireGuard protocols. No intermediary server can intercept or inspect the data stream.
3. **MagicDNS Resolution:** The Advantech host is reachable securely via private domain names (`josie.internal.net`) without broadcasting internal hostnames to public DNS servers.
