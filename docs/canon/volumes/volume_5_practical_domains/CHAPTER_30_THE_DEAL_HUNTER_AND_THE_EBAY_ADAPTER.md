# CHAPTER 30: The Deal Hunter and the eBay Adapter

> *"The machine may scour the marketplace day and night, calculating discounts, verifying seller reputations, and parsing catalog numbers. But when it comes to parting with real dollars, the machine has zero hands. It may only knock on the door and ask permission."*  
> — Dustin, Commercial Automation Policy (`CON-0018`)

---

## § 30.1 The Origins of the Deal Hunter

The Deal Hunter subsystem originated during the Hydra and D-Bot experimentation phases (recorded in History Message 14635). Dustin sought an automated assistant capable of continuously monitoring secondary marketplaces—primarily eBay—for industrial tools, shop equipment, server components, and rare retail inventory at steep discounts.

In commercial AI, autonomous shopping agents are often designed to automatically execute purchases, store credit card tokens, and bid on auctions autonomously. Dustin recognized this as an intolerable risk. An errant model parsing an eBay listing could misread a broken parts-only listing as a functioning tool, bid thousands of dollars on a typo, or exhaust bank accounts in minutes.

The Deal Hunter was therefore architected under an unbreachable rule: **Zero-Trust Autonomous Purchasing**.

---

## § 30.2 Mathematical Candidate Scoring

The Deal Hunter does not rely on vague LLM impressions to judge whether an item is a "good deal." It applies a deterministic mathematical scoring formula to rank candidate items:

$$	ext{Score} = w_1 \cdot \left(rac{P_{	ext{market}} - P_{	ext{listing}}}{P_{	ext{market}}}ight) + w_2 \cdot R_{	ext{seller}} + w_3 \cdot S_{	ext{condition}} - w_4 \cdot C_{	ext{shipping}}$$

Where:
- $P_{	ext{market}}$: Historical 90-day moving average sales price for the exact manufacturer model number.
- $P_{	ext{listing}}$: Current "Buy It Now" or current bid price.
- $R_{	ext{seller}}$: Normalized seller feedback percentage (heavily penalized if feedback count $< 50$ or rating $< 98\%$).
- $S_{	ext{condition}}$: Discrete condition score ($1.0$ for New/Open Box, $0.7$ for Tested Working, $0.0$ for For Parts/Not Working).
- $C_{	ext{shipping}}$: Normalized shipping cost penalty relative to item value.

Only listings that achieve $	ext{Score} \ge 0.75$ and pass negative-keyword filters (`"broken"`, `"parts only"`, `"untested"`, `"as-is"`, `"read description"`) are promoted into the `deal_candidates` table.

---

## § 30.3 The SQLite Zero-Trust Schema

The physical separation between discovery and financial execution is hardcoded into the SQLite schema via CHECK constraints:

```sql
CREATE TABLE deal_candidates (
    candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,                -- e.g., 'ebay'
    listing_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    price_cents INTEGER NOT NULL,
    shipping_cents INTEGER NOT NULL,
    market_price_cents INTEGER NOT NULL,
    score REAL NOT NULL,
    seller_feedback REAL,
    condition_class TEXT NOT NULL,
    listing_url TEXT NOT NULL,
    discovered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    purchase_authorized INTEGER NOT NULL DEFAULT 0,
    CHECK (purchase_authorized = 0)     -- Physically prevents automated authorization
);
```

The database engine itself forbids setting `purchase_authorized = 1` inside this table. If an automated script attempts an update like `UPDATE deal_candidates SET purchase_authorized = 1`, SQLite aborts the transaction with an invariant constraint failure.

---

## § 30.4 The Human Notification and Approval Protocol

When a high-scoring deal is discovered:
1. The Deal Hunter formats a structured markdown notification card:
   - Item Title, Photograph, and Direct Link
   - Listed Price vs. 90-Day Market Average
   - Net Savings Percentage
   - Seller Feedback & Return Policy Summary
2. The card is inserted into Dustin's **Decision Queue V2** with action type `COMMERCIAL_PURCHASE_PROPOSAL`.
3. Dustin receives a push notification on his secure Tailscale device.
4. Dustin clicks the link, inspects the listing with human eyes, and—if approved—completes the transaction using his own authenticated browser session and payment method.

The machine scouts; the human buys.
