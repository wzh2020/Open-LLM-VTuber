# R0 Foundation Architecture Baseline v2: Execution & Acceptance

Revision: 2026-10-10  
Linked milestone: `R0-FOUNDATION-HARDENING-01`  
Status: **IN PROGRESS**. Existing G0-G7 acceptance gates remain binding; the batches below determine execution order.

| Batch | Implementation | Required automated evidence | Gate |
| --- | --- | --- | --- |
| R0.1 Runtime boundaries | explicit session/turn ownership, partial-init cleanup, task join, app shutdown | unique Agents/MCP state; cancellation finalizer; failure injection; close idempotence; 1000 reconnect loops | G1/G2 |
| R0.2 Turn protocol | typed turn events, generation and ordering, bounded queues/backpressure, frontend compatibility | interrupt during ASR/LLM/TTS; stale event discarded; playback lost/timeout; queue limit tests | G1/G2/G5 |
| R0.3 Security and configuration | canonical path containment, auth at WS/API, CORS, secrets, atomic role switching | symlink/prefix traversal; auth rejects before initialization; failed switch leaves old runtime usable | G4/G5 |
| R0.4 Storage and governance | SQLite repo, WAL, schema/version, JSON import/export, backups, delete | concurrent appends; rollback on crash; exact migration fields; export/reimport | G3/G5 |
| R0.5 Observability & quality | stage span IDs, redaction, process and task gauges, CI matrix | P50/P95 generated from traces; redaction tests; failure diagnostic IDs | G5/G6 |
| R0.6 Deploy/soak | source and Docker smoke, Windows/Linux compatibility, resource/leak tests | clean installation; 24-hour soak evidence, repeated disconnects, startup/rollback | G2/G7 |
| R0.7 Architecture exit | ADR closeout, exception register, upstream sync, acceptance report | G0-G7 PASS with commit/run links, risks and rollback procedure | G0-G7 |

## Evidence policy

`PASS` requires an actual test run or observable deployment result. Code-only changes are `IMPLEMENTED / NOT VERIFIED`. Mock/stub tests cannot establish integration or leak-free behavior. Missing CI results remain `UNVERIFIED`, not passing. Deviations require an ADR and explicit waiver.

## First R0.1 microbatch (this change set)

- [x] Define resource scope/lifecycle ADR and v2 baseline
- [x] Implement cleanup for MCP/Agent failures **before** registration
- [x] Await cancellation of real asyncio conversation tasks before closing session state
- [x] Add regression tests for those behaviors
- [ ] Verify GitHub Actions success and required style checks
- [x] Implement an explicit provisional resource registry / idempotent close
- [x] Add app-wide lifespan shutdown and adapter sharing audit (scope registration and server shutdown are implemented; provider-level concurrency audit is still pending)
- [ ] Run repeated connection/teardown leak tests

The first microbatch is not R0.1 completion. Next action after validated PR is lifecycle manager extraction and cancellation integration testing.
