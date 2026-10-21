# CHAPTER 31: Full Steam Vapor Teays Valley: Industrial Domain Operations

> *"Retail business operations are not theoretical exercises. Inventory on the shelf represents real working capital, payroll represents real families depending on honest accounting, and tax compliance represents legal accountability. Josie's retail domain must operate with the precision of a Swiss ledger."*  
> — Dustin, Full Steam Vapor Governance Charter

---

## § 31.1 The Retail Heritage and Commercial Context

Full Steam Vapor (FSV) in Teays Valley, West Virginia, is Dustin’s brick-and-mortar retail business. Operating in a highly regulated consumer industry, FSV requires meticulous inventory control, age-verification compliance, Point of Sale (POS) synchronization, supplier catalog auditing, and multi-channel customer communications.

During the design of Project Josie, FSV served as the primary proving ground for practical, non-academic AI utility. An AI assistant that cannot reliably audit a CSV inventory report or calculate wholesale gross margins is an expensive toy. Josie was required to prove her worth in the demanding crucible of real-world small business operations.

---

## § 31.2 POS Boundaries and Read-Only Ingestion

Point of Sale data contains sensitive customer transaction records, payment processor tokens, and confidential sales volume metrics. 

Under **Concept `CON-0028`** and **Decision `DEC-0003`**, Josie’s interface with FSV retail systems is strictly **Read-Only**:
- Daily transaction journals and inventory snapshots are exported from the POS into designated ingestion directories.
- The ingestion parser validates CSV schemas, normalizes SKU formats, and imports records into dedicated analytical tables within `data/josie.db`: `fsv_inventory`, `fsv_sales_summary`, and `fsv_reorder_alerts`.
- **Zero Ingress to Live POS:** Josie possesses no network access, API credentials, or database handles capable of modifying live POS prices, adjusting on-hand inventory counts, or issuing refunds.

---

## § 31.3 The Two-Click Confirmed Publishing Protocol (`CON-017`)

For customer-facing communications—such as marketing emails, social media announcements of new juice lines, or store holiday hours—Josie acts as a copywriter and layout designer, never a publisher.

Under **Protocol `CON-017`**:
1. **Draft Generation:** Josie drafts the proposed communication, verifying pricing against active SKU records and checking grammatical clarity.
2. **First Click (Staging):** The draft is rendered into an exact visual preview card in the administrative UI. A human manager reviews the visual rendering and clicks *"Stage for Publication"*.
3. **Second Click (Cryptographic Authorization):** A separate confirmation modal appears requiring Dustin's direct password or biometric confirmation (*"Publish to Public Channels"*). Only upon this explicit second confirmation is the payload transmitted to external social or email APIs.

No autonomous process, cron trigger, or background sub-worker can bypass the two-click gate. Public speech on behalf of the business remains an exclusively human responsibility.
