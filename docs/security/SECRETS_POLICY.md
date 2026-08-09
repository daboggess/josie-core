# Secrets Policy

1. Secrets never enter Git, ordinary documentation, prompts, memory, vector
   stores, chat transcripts, screenshots, Discord, or unredacted crash logs.
2. `.env.example` documents names and safe defaults only.
3. Actual values live in ignored environment/secret files or the authenticated
   application that owns them.
4. Prefer an authenticated local environment over passing raw credentials to an
   LLM.
5. Logs record secret presence/configuration status, never values.
6. Browser workers receive only the minimum scoped credential/session required
   for an approved workflow; the current research pilot receives none.
7. Rotation, revocation, backup, and recovery procedures belong to the owning
   service and must not expose the value.
8. If exposure is suspected, stop the affected workflow, preserve a redacted
   audit trail, revoke/rotate through the provider, and verify Git/history/logs.
9. Codex must never ask Dustin to paste a password or product key into source
   merely for convenience.
