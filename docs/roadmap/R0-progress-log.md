# R0 Progress Log

## Baseline

- Milestone: `R0-FOUNDATION-HARDENING-01`
- Branch: `develop`
- Upstream-compatible branch: `main`
- Verified baseline: `992309c0aa19845960228f880013d4685fde93b5`
- Start date: 2026-08-01

## Completed

### Repository governance

- Verified that fork `main` and upstream `main` pointed to the same baseline commit at milestone start.
- Created `develop` from the verified baseline.
- Added the R0 milestone contract.
- Added the current-state risk register.

### Session isolation

- Replaced shared default Agent inheritance with per-session Agent initialization.
- Preserved sharing of the existing heavyweight engine references only where the current architecture already expects it.
- Added regression coverage proving that two client sessions receive distinct Agent objects and do not inherit the default Agent instance.

### Registered-session cleanup

- Corrected disconnect cleanup ordering so the ServiceContext is retained long enough to be closed.
- Added `finally`-based registry and buffer cleanup.
- Added cleanup of registered contexts when connection initialization fails after registration.
- Added regression coverage for task cancellation, context closure, and registry removal.

### Configuration-switch entry hardening

- Added cross-platform plain-file-name validation before a WebSocket request can switch character configuration.
- Rejected POSIX traversal, Windows traversal, absolute paths, nested paths, and non-YAML suffixes.
- Added regression coverage proving invalid names are rejected before the ServiceContext is called.

### Verification foundation

- Added dependency-isolated standard-library lifecycle tests.
- Added a GitHub Actions workflow for pushes and pull requests targeting `develop`.
- Current local regression result: 5 tests passed before the latest remote commit.

## Current Gate Status

| Gate | Status | Notes |
|---|---|---|
| G0 Repository baseline | PASS | Baseline, branch, contract, and risk register established |
| G1 Session isolation | PARTIAL PASS | Agent isolation covered; MCP/tool and shared-engine concurrency contracts remain |
| G2 Lifecycle stability | PARTIAL PASS | Registered contexts covered; pre-registration failures and server shutdown remain |
| G3 Persistence integrity | NOT STARTED | SQLite repository and JSON migration remain |
| G4 Security baseline | IN PROGRESS | Config-switch entry protected; authentication, CORS, secrets, and canonical containment remain |
| G5 CI and quality | FOUNDATION READY | Initial workflow and five tests added; broader coverage remains |
| G6 Observability baseline | NOT STARTED | Correlation IDs, stage timing, and resource gauges remain |
| G7 Deployment baseline | NOT STARTED | Windows/Linux/Docker smoke profiles remain |

## Next Execution Queue

1. Close temporary ServiceContext objects when Agent/MCP initialization fails before registration.
2. Await cancelled conversation tasks and normalize cancellation behavior.
3. Add FastAPI lifespan shutdown cleanup for every active session.
4. Move canonical path containment into the ServiceContext/config file resolver.
5. Define and implement the authentication and CORS configuration contract.
6. Introduce the history repository abstraction and SQLite schema.
7. Add structured lifecycle and latency observability.

## Known Limitation

The current path hardening protects the public WebSocket configuration-switch entry point. Canonical containment must still be enforced inside the underlying configuration resolver so future internal callers cannot bypass the boundary.
