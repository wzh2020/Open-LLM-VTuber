# ADR 0001: Explicit runtime scopes and resource ownership

- Date: 2026-10-10
- Status: **Accepted for R0 target architecture; migration incomplete**
- Decision owners: fork maintainers
- Supersedes: implicit sharing behavior in ServiceContext where it conflicts with session isolation

## Context

The current WebSocket session constructs a ServiceContext from cached engine references. Mutable Agent state was previously shared, disconnect cleanup occurred after registry removal, and partially initialized resources could be lost before registration. These are ownership failures, not just individual bugs. Character switches can also replace engines without an explicit rollback boundary.

## Decision

Use a modular monolith with three nested ownership scopes: app, session, turn. App owns immutable metadata, infrastructure and carefully audited reusable engines; session owns Agent, MCP client and mutable role/session state; turn owns active tasks, audio segments and cancellation. Resource acquisition must register a close callback before further fallible steps. Closing shall be idempotent, bounded and resilient to independent teardown failures. A resource with no documented concurrency policy is **session-scoped by default** or serialized until it is proven safe to share.

Keep ServiceContext as an adapter temporarily. Do not introduce a containerized microservice mesh or distributed state storage.

## Ordering and failure semantics

1. Authenticate before allocating a session.
2. Create a provisional session scope, then acquire resources individually.
3. Publish the session into the active registry only once initialization is successful.
4. On any error/cancellation, close provisional resources in reverse acquisition order.
5. On disconnect, stop output, cancel and await turn tasks with a bounded deadline, then close session-owned resources.
6. On application shutdown, prevent new connections and close all active sessions before shared engines.
7. Close errors are logged with correlation ID and never prevent attempted release of remaining owned resources.

## Consequences

Positive: no memory cross-contamination, predictable cleanup, safer upgrades, testable failure paths.  
Costs: more explicit lifecycle code, adapter concurrency audits, additional state-machine integration tests, and careful handling of async cancellation.

## Required tests

- Two clients have different Agent and MCP session state.
- Initialization failure before registration closes acquired resources.
- Disconnect waits for real task finalizers, not just `cancel()`.
- Repeated close is safe.
- A failing closer cannot suppress all other closers.
- Active conversation output cannot be emitted after cancellation.
- Shared-engine concurrency contract is verified before reuse.

## Rollout

First patch pre-registration cleanup and awaited cancellation; next introduce scoped registry and app lifespan, then formalize provider scope declarations. Status stays migration-incomplete until all above tests and CI are available.
