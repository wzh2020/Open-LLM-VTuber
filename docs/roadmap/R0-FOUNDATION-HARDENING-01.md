# R0-FOUNDATION-HARDENING-01

## 1. Purpose

This milestone turns the current Open-LLM-VTuber v1 fork into a safe, testable, observable, and evolvable baseline for a long-lived personal AI companion.

The milestone deliberately prioritizes correctness and operational control over new user-facing features. Long-term memory, emotion simulation, plugin marketplace, 3D rendering, and cross-device synchronization must not be implemented on top of an unsafe session and persistence foundation.

## 2. Baseline

- Repository: `wzh2020/Open-LLM-VTuber`
- Development branch: `develop`
- Upstream-tracking branch: `main`
- Baseline commit: `992309c0aa19845960228f880013d4685fde93b5`
- Upstream repository: `Open-LLM-VTuber/Open-LLM-VTuber`
- Upstream baseline at milestone start: `992309c0aa19845960228f880013d4685fde93b5`
- Application version: `1.2.1`

`main` remains an upstream-compatible branch. Product hardening work is committed to `develop`.

## 3. Product Boundary

Open-LLM-VTuber is treated as the real-time embodiment and interaction layer of a future personal companion runtime.

The stable core responsibilities are:

1. real-time client/session lifecycle;
2. audio and multimodal input processing;
3. agent invocation and interruption;
4. ordered TTS and avatar output;
5. character configuration and history continuity;
6. controlled tool invocation;
7. observability, security, and recovery.

Model providers, ASR engines, TTS engines, external integrations, and future memory implementations remain replaceable adapters.

## 4. In Scope

### WP-01 Repository and architecture governance

- Preserve `main` for upstream synchronization.
- Use `develop` as the integration branch.
- Record architecture decisions and compatibility constraints.
- Establish an upstream comparison and intake process.

### WP-02 Session isolation

- Eliminate mutable Agent sharing between independent clients.
- Ensure session memory, interruption flags, tool state, and history selection are isolated.
- Define which heavyweight engines may be safely shared and which components must be session-scoped.

### WP-03 Lifecycle and resource cleanup

- Correct disconnect cleanup ordering.
- Close Agent and MCP resources reliably.
- Cancel conversation tasks and release client buffers.
- Prevent orphan subprocesses and stale session entries.

### WP-04 Persistence hardening

- Introduce a storage abstraction.
- Replace direct JSON read-modify-write as the primary history backend with SQLite.
- Provide migration/import compatibility for existing JSON histories.
- Use transactions, indexes, and deterministic identifiers.

### WP-05 Security baseline

- Add optional-but-supported WebSocket authentication.
- Restrict remote access defaults and CORS behavior.
- Harden character/config path resolution.
- Separate secrets from versioned configuration.
- Define MCP/tool risk levels and execution boundaries.

### WP-06 Automated verification

- Add unit tests for session creation, interruption, cleanup, configuration validation, and persistence.
- Add integration tests for WebSocket conversation lifecycle using stub engines.
- Add CI gates for formatting, linting, tests, and security scanning.

### WP-07 Observability and performance baseline

- Introduce structured correlation fields for session, conversation, provider, and tool call.
- Measure ASR, first-token, first-sentence, TTS, playback, and interruption latency.
- Record process memory and active session/resource counts.

### WP-08 Deployment reproducibility

- Verify source installation and Docker startup paths.
- Define Windows, Linux, and Docker smoke tests.
- Document required and optional dependencies by deployment profile.

## 5. Explicit Non-Goals

The following work is deferred until this milestone passes acceptance:

- semantic long-term memory;
- relationship or emotion engine;
- autonomous proactive behavior;
- plugin marketplace;
- full graphical configuration center;
- 3D/VRM renderer;
- mobile synchronization;
- enterprise multi-tenant SaaS support;
- replacement of the complete v1 codebase.

## 6. Hard Architectural Rules

1. No mutable Agent instance may be shared across unrelated client sessions.
2. Every allocated session resource must have an explicit owner and close path.
3. External tools may not bypass the capability and permission boundary.
4. Persistent user data must be stored transactionally and be exportable and deletable.
5. The role identity and user history must not be coupled to one LLM provider.
6. New provider integrations must depend on stable interfaces rather than conversation orchestration internals.
7. `main` must not receive product-specific changes directly.

## 7. Acceptance Gates

### G0 Repository baseline

- `main` matches the selected upstream baseline.
- `develop` is created from the verified baseline.
- Milestone contract and risk register exist.

### G1 Session isolation

- Two simultaneous clients receive different Agent instances.
- Memory written by one client is absent from the other client.
- Interrupting one conversation does not alter another session.
- Session-specific MCP clients and tool execution state are not shared.

### G2 Lifecycle stability

- Connect/disconnect loops leave no client context, buffer, task, or MCP resource behind.
- Cleanup remains effective when initialization or conversation processing fails.
- A 24-hour soak test shows no monotonic resource growth attributable to session leaks.

### G3 Persistence integrity

- Concurrent message writes do not corrupt or lose history.
- History list, create, read, append, rename, and delete operations are covered by tests.
- Existing JSON history can be imported without losing role, timestamp, name, or avatar fields.

### G4 Security baseline

- Invalid authentication is rejected before session initialization.
- Character path traversal and prefix-confusion attempts fail.
- Remote deployment guidance requires TLS and explicit origin/auth configuration.
- Secrets are not required to be stored in tracked YAML files.

### G5 CI and quality

- Unit and integration tests run on every push and pull request to `develop`.
- Ruff and tests pass.
- Critical conversation and lifecycle modules have regression coverage.

### G6 Observability baseline

- Every conversation has a traceable session and conversation identifier.
- Stage latency can be derived from logs or metrics.
- Active sessions, pending TTS tasks, and tool executions can be inspected.

### G7 Deployment baseline

- Documented smoke tests pass for source and Docker profiles.
- The default local profile starts without exposing an unauthenticated public service.

## 8. Definition of Done

R0 is complete only when all gates G0-G7 pass and an acceptance report records:

- implementation commits;
- automated test evidence;
- remaining known risks;
- compatibility impact;
- rollback procedure;
- approved entry conditions for the next milestone.

The next milestone may introduce the Character Kernel only after this foundation is accepted.
