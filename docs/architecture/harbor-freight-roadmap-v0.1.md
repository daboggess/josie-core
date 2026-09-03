# JOSIE Harbor Freight Roadmap v0.1

## Canonical architecture principles

- Josie is the durable locally owned system.
- Everything else is replaceable.
- Many tools; few daemons; few state owners.
- Nothing gets tenure; everything keeps earning its seat.
- Authority flows down from Dustin.
- Compute flows up from whichever authorized tool earns the job.
- Pass the butter with the cheapest reliable tool capable of passing the butter.
- D-bot uses Seal / Ring / Scroll:
  - Seal = cryptographic identity.
  - Ring = machine-readable delegated authority.
  - Scroll = signed mission, constraints, acceptance criteria, and receipt requirements.
- Economic routing:
  - L0 = deterministic.
  - L1 = owned local.
  - L2 = free/open external.
  - L3 = already-paid capacity.
  - L4 = cheap metered commodity.
  - L5 = premium frontier.
- Capability implementations are replaceable and sit behind stable contracts and acceptance tests.
- Integration risk will eventually be represented as Green / Amber / Red.
- Target criticality will eventually be represented separately.
- External effects will eventually be represented separately.
- Updates follow: discover -> sandbox -> acceptance test -> promote -> observe -> rollback.
- The self-maintenance system may repair or replace ordinary components.
- The self-maintenance system may **not** independently rewrite or approve changes to root authority, recovery policy, or the rules governing its own authority.
- Open WebUI, current orchestration tools, databases, models, coding harnesses, and providers are candidates, not permanent architecture.
- Existing infrastructure remains in place until a replacement proves itself.

## Phase boundary

Phase 0A is inventory and preservation only. This document does not select replacements, migrate state, implement D-bot, create a component registry, run capability races, or authorize later phases.
