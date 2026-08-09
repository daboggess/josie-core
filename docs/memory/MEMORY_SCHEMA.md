# Memory Schema

Memory layers are separate even if an early implementation shares SQLite.

| Layer | Purpose | Default trust | Change control |
|---|---|---:|---|
| Constitutional | Identity, purpose, authority, boundaries | ratified only | Dustin + versioned decision |
| Genesis / Identity | Reconciled origin and stable self-knowledge | confirmed claims | Genesis protocol |
| Dustin / Relationship | Relevant continuity and preferences | provenance-dependent | privacy review |
| Project State | Current verified facts | current evidence | canonical state update |
| Episodic | What happened and when | observed/provenance | append; supersede, do not erase |
| Semantic | Learned knowledge | confidence-scored | correction/supersession |
| Working | Current task context | temporary | expire after task |
| Procedural | Approved workflow instructions | tested/versioned | code/policy review |
| Decisions | What was decided and why | signed record | decision log |
| Superseded Decisions | Historical decisions no longer current | historical only | immutable link |

Durable records should support: stable ID, layer, content, source, source type,
captured and effective timestamps, confidence, status, related entities,
evidence links, contradictions, `supersedes`, `superseded_by`, sensitivity,
retention class, authority, reviewer, and audit link.

Deletion is soft by default. A memory must never gain execution authority merely
because it was retrieved.
