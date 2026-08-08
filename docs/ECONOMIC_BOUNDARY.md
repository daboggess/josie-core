# Economic and wallet boundary

Josie's economic subsystem is accounting-only. `config/economic-policy.json`
is machine-readable and fail-closed:

- spending is disabled;
- wallet capability is disabled;
- single, daily, monthly, wallet-balance, and debt limits are zero cents;
- Josie may not modify these limits herself;
- autonomous debt, contracts, money movement, wallet transfers, limit changes,
  and human impersonation are forbidden;
- tax, contracting, identity verification, regulated business actions,
  purchases, subscriptions, bids, and financial transfers are human-controlled;
- the Upgrade Fund ledger records facts only and has no payment or wallet API.

Inspect the effective boundary locally:

```powershell
cd C:\Josie
.\.venv\Scripts\python.exe .\core.py economics status
```

Expected status is `locked`, with both capabilities false, every limit zero,
zero transactions executed, and zero external activity.

Future wallet evaluation is not authorization to install or connect one. It
requires a new attended design review covering custody, revocation, identity,
tax, jurisdiction, transaction confirmation, per-action scope, breach recovery,
and limits stored somewhere Josie cannot alter. Until then, no wallet exists.
