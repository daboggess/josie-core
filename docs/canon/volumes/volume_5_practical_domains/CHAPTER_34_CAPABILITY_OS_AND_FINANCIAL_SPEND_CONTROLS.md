# CHAPTER 34: Capability OS and Financial Spend Controls

> *"A machine with an open credit card is a financial suicide pact. Spend controls must not be soft policy guidelines; they must be hard, immutable circuit breakers embedded in the network transport layer."*  
> — Dustin, Financial Hardening Specification (`CON-0034`)

---

## § 34.1 The Myth of the Autonomous Corporate Buyer

In late 2024, various AI startups marketed "autonomous corporate agents" equipped with virtual credit cards, authorized to book travel, procure software licenses, and purchase cloud compute autonomously. 

Within Project Josie, this concept was recognized as an extreme anti-pattern. Machine learning models are probabilistic; they cannot be held legally liable, they cannot sign contracts, and they cannot experience the financial consequence of bankruptcy. Granting an AI autonomous payment capabilities is an abdication of fundamental financial stewardship.

---

## § 34.2 The Capability OS Boundary Model

To prevent unauthorized capability expansion, Josie’s architecture implements **Capability OS Boundaries** (`CON-0034`).

A worker or sub-agent does not operate with generalized ambient system authority. It is granted a temporary, cryptographically signed **Capability Token** that strictly defines:
1. Which directories it may read.
2. Which specific temporary worktree it may write to.
3. Which localhost ports it may contact.
4. **Zero Financial Authority:** The capability token schema contains no fields, flags, or methods for financial transactions.

```
       [ CAPABILITY OS TOKEN ]
  +--------------------------------------+
  | Subject: Worker-Coder-14B            |
  | ReadScope:  D:\josie-worktrees	ask1 |
  | WriteScope: D:\josie-worktrees	ask1 |
  | NetScope:   127.0.0.1:11434 ONLY     |
  | FinancialSpendLimit: $0.00 (HARD)    |
  | TokenExpires: 2026-10-21T14:00:00Z   |
  +--------------------------------------+
```

---

## § 34.3 Hard-Dollar Spending Circuit Breakers

Even in authorized cloud API usage (such as invoking frontier advisory models for complex code review), financial spend is strictly policed:
- **Monthly API Cap:** Hard-clamped at **$25.00 USD per month**.
- **Per-Task Hard Limit:** No single reasoning query may consume more than **$0.15 USD**.
- **Deterministic Token Counting:** The runtime calculates the exact input token count before issuing any external API request. If the projected cost exceeds the per-task threshold, the request is blocked and routed to the local resident generalist.
- **Hard Cloud Dashboard Kill-Switches:** At the cloud provider account level (Google Cloud / Anthropic / OpenAI), monthly billing hard-stops are configured to automatically revoke API keys if monthly spend reaches $30.00.

Josie’s operational sovereignty means that even under an extreme, rogue infinite-loop failure mode, total financial exposure is physically capped at the price of a restaurant lunch.
