# Manual Sophie Wake-Up Relay (Phase 1 Operational Pilot)

**Status:** `IMPLEMENTED / OPERATIONAL HARNESS READY`  
**Date:** `2026-10-05`  
**Governing Documents:** [JOSIE_CODEX_MASTER_CONTEXT.md](../../JOSIE_CODEX_MASTER_CONTEXT.md), [JOSIE_MASTER_BUILD_STATE.yaml](../JOSIE_MASTER_BUILD_STATE.yaml), [JOSIE_CONTINUITY_AND_INTERFACE_DIRECTION_2026-10-05.md](../JOSIE_CONTINUITY_AND_INTERFACE_DIRECTION_2026-10-05.md)

---

## 1. Purpose & Immediate Objective

The immediate objective of this phase is to **remove Dustin from all copy/paste transport** between Antigravity/Josie and Sophie while avoiding:
- OpenAI API charges or programmatic API keys
- ChatGPT Work usage or subscriptions
- Automatic cloud-model triggers or uncontrolled web-agent loops

Dustin temporarily remains **only the manual wake-up switch** for Sophie.

> [!NOTE]
> This is explicitly an **interim step** toward removing even the manual wake-up later if an economical, account-native trigger becomes available.

---

## 2. Core Architecture Topology

| Layer | Role & Functionality |
| :--- | :--- |
| **Slack (`#josie`)** | **Visible collaboration transport:** Channel `C0C6QGLK1EZ` in `Josie-Team-Chat`. All decision-relevant exchanges are visibly posted and inspectable by Dustin. |
| **GitHub / Repository (`josie-core`)** | **Code and artifact record:** Large code diffs, receipts, logs, and artifacts live here, never dumped into Slack chat. |
| **Josie DB (`josie.db` / `state.json`)** | **Structured local authoritative state:** Replay prevention, message deduplication, and receipts. |
| **Dustin (`<@U0C6TSMKMQW>`)** | **Temporary one-word Sophie wake-up:** Receives Slack notification, sends `"relay"` in his existing ChatGPT conversation. Copies zero technical content. |
| **Sophie** | **Frontier reviewer:** Operates through Dustin's existing ChatGPT Plus/Pro conversation with native Slack workspace access, reads `#josie` directly, inspects artifacts, and responds into Slack. |

---

## 3. Communication Loop & Operating Sequence

```
1. Antigravity / Josie completes bounded local work.
2. If Sophie review is required, Antigravity formats an outbound message envelope.
3. Antigravity posts the complete message to Slack (#josie, C0C6QGLK1EZ) via Slack Web API.
4. Outbound message concludes with the notification mention:
   "<@U0C6TSMKMQW> SOPHIE NEEDED — send relay in the AI Build ChatGPT conversation."
5. Dustin's phone/desktop alerts him of the Slack mention.
6. Dustin opens his existing AI Build ChatGPT conversation and types exactly:
   "relay"
7. Sophie reads #josie directly via her connected workspace integration.
8. Sophie inspects repository artifacts / git commits if referenced.
9. Sophie formulates review and posts directly back into #josie.
10. Antigravity receives Sophie's response via Slack Socket Mode (no public inbound ports).
11. Antigravity validates envelope, checks mission correlation, records receipt, and continues local work.
```

**Zero Technical Content Transport:** Dustin never copies prompts, diffs, code, logs, or responses between browser tabs or windows.

---

## 4. Message Envelope Specifications

### Outbound Envelope (Antigravity/Josie -> Sophie)
```text
FROM: ANTIGRAVITY
TO: SOPHIE
MISSION: <stable mission ID>
MESSAGE-ID: AG-<unique ID>
IN-REPLY-TO: <message ID or NONE>
TYPE: RESULT | QUESTION | REVIEW_REQUEST | BLOCKER | STATUS

BODY:
<concise decision-relevant information>

ARTIFACTS:
<repository paths / GitHub commits / receipts>

TESTS:
<relevant test results>

ACTION REQUESTED:
<exactly what Sophie needs to evaluate or answer>

<@U0C6TSMKMQW> SOPHIE NEEDED — send relay in the AI Build ChatGPT conversation.
```

### Inbound Envelope (Sophie -> Antigravity/Josie)
```text
FROM: SOPHIE
TO: ANTIGRAVITY (or JOSIE or ALL)
MISSION: <matching mission ID>
MESSAGE-ID: <unique ID>
IN-REPLY-TO: <outbound message ID>
TYPE: RESULT | STATUS | REVIEW
DISPOSITION: CONTINUE | REVISE | BLOCKED_FOR_DUSTIN | MISSION_COMPLETE

BODY:
<guidance / review / decision>
```

---

## 5. Sophie Dispositions & Authority Model

| Disposition | Meaning & Local Response |
| :--- | :--- |
| **`CONTINUE`** | Proceed with the existing Dustin-authorized mission. |
| **`REVISE`** | Apply the requested bounded correction and report back to Sophie. |
| **`BLOCKED_FOR_DUSTIN`** | Stop immediately and tag Dustin with the specific decision required. |
| **`MISSION_COMPLETE`** | Stop the mission, persist completion state, and close. |

### Authority Bounds
Sophie's Slack response is **expert guidance inside the existing authorized mission**. It does **NOT** independently authorize:
- Financial actions, purchases, or bids
- Destructive file actions outside scope
- Privilege escalation or shell relaxation
- Credential disclosure or publication
- Constitutional or identity modification
- Material scope expansion

Those decisions remain strictly reserved for Dustin.

---

## 6. Josie Participation & Forward Continuity

The relay module (`josie/slack_relay.py`) is designed so **Antigravity is only the first local sender**.

The transport abstraction natively supports:
- `FROM: JOSIE`
- `TO: JOSIE`

without rewriting the transport layer. Once Josie's local continuity and orchestration layers are active, Josie can take over persistent project presence while Antigravity remains a focused coding worker.

---

## 7. Socket Mode Architecture (No Inbound Public Ports)

Outbound messages use `POST https://slack.com/api/chat.postMessage`.  
Inbound messages use **Slack Socket Mode**:
1. Host calls `POST https://slack.com/api/apps.connections.open` using `JOSIE_SLACK_APP_TOKEN` (`xapp-...`).
2. Slack returns a secure WebSocket URI (`wss://...`).
3. Local client connects via WebSocket, immediately acknowledges events (`{"envelope_id": ...}`), processes payload, and maintains reconnect backoff.
4. **No public IP, router port-forwarding, ngrok, or webhook exposure is required.**

---

## 8. CLI Interface

```powershell
# Check status, credentials, and connectivity
python -m josie.slack_relay status

# Run automated verification suite (11 unit/governance tests)
python -m josie.slack_relay test

# Run Socket Mode listener for a specific mission
python -m josie.slack_relay run --mission slack-relay-pilot-001

# Execute canonical pilot sequence
python -m josie.slack_relay pilot
```
