# Foundation Architecture Baseline v2

Status: **PROPOSED / migration in progress**  
Milestone: `R0-FOUNDATION-HARDENING-01`  
Revision: 2026-10-10  
Based on: v1.2.1, fork `develop`. This document extends, not replaces, the existing R0 contract.

## 1. Product scope

Build a **local-first, single-user-oriented, modular-monolith companion runtime**. Do not add microservices, Kubernetes, a cloud message broker, multi-tenant SaaS, or a plugin marketplace in R0.

R0 must establish safe session boundaries, deterministic cancellation, storage integrity, access control, observability, and reproducible development. Long-term semantic memory, emotional dynamics, and autonomous actions remain out of scope.

## 2. Runtime boundaries and ownership

| Boundary | Owns | Does not own | Lifecycle |
| --- | --- | --- | --- |
| AppRuntime | process-wide config, immutable metadata, adapter factories, shared safe engines | client memory, session MCP client | FastAPI lifespan |
| SessionRuntime | session ID, connection, mutable Agent, MCP client, history selection, conversation state | global providers' infrastructure | connect to disconnect |
| ConversationTurn | turn ID, input, generation task, output queue, TTS work, cancellation scope | other turns' output | start to completed/cancelled |
| CharacterRuntime (R1) | validated character identity, versioned profile, proposed role switch | global mutable Agent | active role epoch |
| StorageRepository | durable users, profiles, sessions, events, histories and schema versions | transient audio buffers | process/service lifetime |
| CapabilityBoundary | tool permission decision, request validation, audit event | unrestricted operating system access | per invocation |

**Invariant I1:** no unrelated sessions share mutable Agent state or conversation memory.  
**I2:** every resource receives a single explicit owner immediately after allocation, including during partially failed initialization.  
**I3:** only immutable/reentrant components may be shared; provider adapters declare `SESSION`, `SHARED`, `SERIALIZED`, or `POOLED` concurrency policy. The current shared ASR/TTS/VAD references are grandfathered **only until audited**.  
**I4:** every turn has one cancellation scope and generation number; cancelled or superseded turns cannot emit user-visible late audio.  
**I5:** every persisted write is transactional, scoped and recoverable; legacy JSON import is reversible until accepted.  
**I6:** authorization precedes resource allocation or sensitive reads. MCP is a transport, not a permission decision.  
**I7:** switching character/configuration builds and validates candidates before replacing the active runtime; failed switches do not corrupt a healthy session.  
**I8:** observability never logs full private prompts, secrets, screenshots or raw audio by default.  
**I9:** backwards compatibility is explicit for existing frontend WebSocket message types and legacy chat histories.  
**I10:** all gates require executable evidence; a successful commit is not a passed integration test.

## 3. Migration boundaries

Keep `ServiceContext` as a compatibility façade during R0, but remove orchestration and resource ownership from it incrementally:

```text
FastAPI lifespan -> AppRuntime (shared assets)
  WebSocket auth -> SessionManager -> SessionRuntime (owned resources)
    ConversationRuntime -> TurnController (state, deadline, generation)
      Provider adapters: ASR, VAD, Agent, TTS, Avatar
      CapabilityGateway -> MCP / controlled plugins
  StorageRepository -> SQLite (with JSON import bridge)
```

Every refactor must be a small independently revertible change. Do not move modules for appearance alone; migrate ownership with tests. No additional production behavior may depend on proposed abstractions until an interface contract is approved.

## 4. Session and turn state machines

Session: `NEW -> INITIALIZING -> READY -> CLOSING -> CLOSED`; any initialization error enters `CLOSING`. Close is idempotent and best effort across independent owned resources.

Turn: `IDLE -> LISTENING -> THINKING -> SPEAKING -> COMPLETED`. `INTERRUPTING`, `CANCELLED`, `FAILED` are terminal/exit paths as defined in the protocol contract. A new turn supersedes the previous turn only after cancellation has been signalled; no stale turn may publish events after generation invalidation.

Cancellation order: mark generation invalid -> stop outgoing playback -> cancel generation and queued TTS -> await bounded cleanup -> close turn-owned resources -> persist interruption metadata (according to history policy). Session closes after active turns and session-owned resources. Timeouts must be observable.

## 5. Backpressure & quotas

Introduce documented configurable limits, with measured defaults before enforcement: max audio input duration/bytes, per-session pending events, active inference turns, queued TTS segments, MCP calls, tool duration, outbound event bytes, and idle connections. On overflow, return typed errors and degrade gracefully; never append indefinitely to unbounded NumPy arrays.

## 6. Security and privacy

Local loopback must remain usable without deploying a cloud identity provider. Non-loopback deployment requires explicit opt-in plus authentication and TLS at the proxy boundary. Protect WS as well as ASR/TTS, cache, avatar and configuration endpoints. Bound config paths using resolved containment at the file-read boundary, not only the WS entry. Protect against symlink escapes and case/prefix confusion. Secret resolution uses environment variables or private local storage, with sanitized logs.

Tool calls are separated from authorization. Read-only requests may be auto-approved by policy; file modification, outbound messages, deletion, payment and other consequential operations need explicit risk classification and user consent.

## 7. Storage baseline

Start with SQLite WAL mode and foreign keys; use a repository interface. Suggested stable IDs: `profile_id`, `session_id`, `turn_id`, `event_id`, `history_id`, `character_id`, and `schema_version`. Event records should include timestamp, actor, source, correlation IDs, payload version and privacy class. Design migrations, replay limits, backup/export/delete, and legacy JSON import before switching the write path. Do not promise semantic long-term memory in R0.

## 8. Observable quality

Collect redacted structured events for session startup/close, turn state transitions, ASR latency, first token, first sentence, first TTS audio, playback, interrupt latency, queue lengths, process RSS, connection count and tool duration. Distinguish P50/P95 and per-provider budgets. Failures must identify session/turn without exposing personal content.

## 9. Release and upgrade policy

`main` stays upstream-compatible; `develop` is the integration branch; each R0 microbatch has a feature branch and reviewable PR. Pin the baseline, maintain rollback instructions, do not migrate production data automatically without backups. Consult upstream v2 without adopting unstable modules as a foundation.

## 10. Proof of completion

R0 is not complete until all G0-G7 gates pass under the amended R0.1-R0.7 acceptance matrix in `docs/roadmap/R0-architecture-v2-acceptance.md`. Code, CI, integration, load and deployment evidence are separate claims. The next milestone (Character Kernel) is blocked until the foundation meets those gates.
