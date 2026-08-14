# Deal Hunter — Local Design Boundary

Status: `WORKING LOCAL SCORER + MANUAL UI + STAGED EBAY ADAPTER / LIVE DISCOVERY DISABLED`

The first useful Josie 0.99 workflow will evaluate hardware opportunities by
price per performance. Current approved work is local schema, scoring, test
fixtures, and review proposals only.

The deterministic scorer accepts manually supplied price, shipping, tax,
required platform cost, benchmark index, VRAM, power, compatibility, condition,
seller risk, source kind, and evidence timestamp. It returns total acquisition
cost, a transparent heuristic score, uncertainty, evidence status, and a local
recommendation.

Price performance contributes at most 40 points; VRAM 20; compatibility 20;
condition 10; and verified evidence 10. Seller and power risks subtract points.
Incompatibility always rejects a candidate. Missing or insufficient current
listing evidence always produces `verify_before_review`, regardless of score.
These weights are a versioned heuristic, not market truth.

Example local-only input:

```powershell
.\.venv\Scripts\python.exe .\core.py research score-deal `
  --title "Manually supplied GPU candidate" `
  --source-reference "manual note" --source-kind user_supplied `
  --observed-at "2026-08-09T21:00:00-04:00" `
  --ask-price 200 --shipping 0 --tax 0 --required-platform-cost 100 `
  --benchmark-index 100 --vram-gb 12 --power-watts 170 `
  --compatibility needs_review --condition used_good --seller-risk medium `
  --notes "Research only; no purchase authority."
```

This records a local research candidate. It performs no browsing, messaging,
login, bid, purchase, payment, or external activity.

The Josie desktop window also has a **Deals** tab. Select **New candidate** to
open the manual entry screen, paste or type a listing, and choose **Score & Save
Locally**. Every entry from this screen is forcibly recorded as
`user_supplied`, even when its reference is a URL. The URL is stored as text and
is never opened. The screen cannot select a more authoritative source type and
does not expose the scorer to the local model.

Not authorized: account creation, login, scraping or navigation of unapproved
sources, CAPTCHA/anti-bot bypass, saved downloads, uploads, seller contact,
bids, purchases, Discord posting, contracts, wallet activity, or payments.
`config/opportunity-sources.json` remains default-deny. eBay Browse API is the
one selected source, but it is `staged_not_active`: no account is connected, no
credential is present, and no live call is authorized. The offline adapter can
normalize a supplied API-shaped fixture and remove duplicate `itemId` values;
it contains no network client. See `EBAY_SOURCE_REVIEW.md` for the activation
gates and verified official documentation.
