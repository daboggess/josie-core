# eBay Source Review

Status: `SELECTED / STAGED / NOT ACTIVE`

Decision date: 2026-08-14

Authority: Dustin selected eBay as Josie Deal Hunter's first live source. This
selects the source; it does not create an account, accept an agreement, create a
key, store a credential, or activate live calls.

## Verified official facts

- The official [Browse API](https://developer.ebay.com/api-docs/buy/api-browse.html)
  supports keyword/category searches for active item summaries and item-detail
  retrieval.
- Browse methods require an Application access token obtained through the
  client-credentials flow; a user token and Dustin's buyer login are not needed
  for ordinary search. See eBay's [Browse API page](https://developer.ebay.com/develop/api/buy/browse_api)
  and [authorization guide](https://developer.ebay.com/develop/guides-v2/authorization).
- eBay's [API call-limit table](https://developer.ebay.com/develop/get-started/api-call-limits)
  listed a default 5,000 Browse calls/day on 2026-08-14. Josie's staged local
  ceiling is only 100/day, 2/minute, and one request at a time.
- eBay requires a developer account, API License Agreement acceptance, and an
  application keyset. Its current getting-started guide says account approval
  may take about one business day. See [Getting started with eBay APIs](https://developer.ebay.com/develop/guides-v2/get-started-with-ebay-apis).
- eBay's call-limit page marks Buy APIs as requiring an additional license.
  Production activation therefore remains blocked until Dustin verifies the
  account's actual Browse/Buy access and applicable license terms.

These facts are time-sensitive and must be rechecked before activation.

## Staged boundary

The repository currently contains only:

- a fail-closed eBay source policy;
- environment-variable names with no values;
- offline normalization of a supplied Browse-shaped response;
- exact `www.ebay.com`/`ebay.com` item-link validation;
- within-batch deduplication by `itemId`;
- a bounded local fixture inbox with cross-run `itemId` deduplication;
- first-seen, last-seen, and observation-count persistence for normalized items;
- seller/condition/shipping normalization;
- untrusted-listing labeling and description exclusion.

The adapter deliberately reports `scoring_ready: false`. Browse data supplies
price, shipping, seller, condition, and stable IDs, but sales tax remains
unknown before checkout and the listing does not reliably establish a hardware
model's benchmark, VRAM, power, or compatibility. The adapter therefore records
price-plus-shipping but does not claim a total acquisition cost. A later
deterministic hardware-profile match and explicit cost completion must supply
the missing facts before scoring.

## Closed activation gates

1. Dustin creates or signs into the eBay developer account.
2. Dustin reads and accepts the API License Agreement.
3. Dustin verifies the additional Buy API license/access requirement for this
   private read-only use.
4. Dustin creates the application keyset.
5. Credentials are stored directly in `C:\Josie\.env`, never chat, Git, logs,
   screenshots, or memory.
6. Codex reviews the final connector and tests token redaction, request budgets,
   exact endpoints, timeouts, deduplication, and failure behavior.
7. Dustin explicitly approves live read-only activation.

Even after activation, seller messages, user authentication, offers, bids,
orders, checkout, purchases, and payments remain prohibited.
