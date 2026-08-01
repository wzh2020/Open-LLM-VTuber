# R0 Current-State Risk Register

## 1. Scope

This register captures risks observed in the Open-LLM-VTuber v1.2.1 baseline at commit `992309c0aa19845960228f880013d4685fde93b5`.

Risk ratings:

- Severity: Critical, High, Medium, Low
- Probability: High, Medium, Low
- Priority: P0, P1, P2, P3

## 2. Active Risks

| ID | Risk | Evidence area | Severity | Probability | Priority | Required treatment |
|---|---|---|---|---|---|---|
| R0-R01 | Independent clients may share the same mutable Agent instance and memory | `WebSocketHandler._init_service_context` passes the cached `agent_engine` by reference | Critical | High | P0 | Create a fresh Agent for every session; add identity and memory-isolation tests |
| R0-R02 | Disconnect cleanup may fail to close the session context | Client context is removed before it is retrieved for `close()` | High | High | P0 | Capture and close context before/while removing registry entries; enforce cleanup in `finally` |
| R0-R03 | MCP clients or subprocess resources may survive disconnect or failed initialization | Session MCP components have explicit close behavior but lifecycle is not guaranteed | High | Medium | P0 | Give every session resource an owner; close on disconnect, initialization failure, and server shutdown |
| R0-R04 | Character configuration path validation uses string-prefix comparison | `handle_config_switch` compares normalized path with `startswith` | High | Medium | P0 | Resolve both base and target paths and enforce `relative_to`/`commonpath` containment |
| R0-R05 | WebSocket and utility endpoints have no authentication | `/client-ws`, `/asr`, and `/tts-ws` accept unauthenticated clients | High | High for remote deployments | P0 | Add configurable token authentication and safe local defaults |
| R0-R06 | CORS is globally permissive while credentials are allowed | FastAPI middleware allows `*` origins, methods, and headers | High | Medium | P0 | Make allowed origins explicit and environment-configurable |
| R0-R07 | Chat history uses non-transactional JSON read-modify-write | `chat_history_manager.py` rewrites the complete JSON file | High | Medium | P1 | Add repository abstraction and SQLite backend with migration support |
| R0-R08 | Concurrent history writes can lose messages or corrupt files | No file locking, transaction, or atomic replace | High | Medium | P1 | Serialize writes transactionally; add concurrent-write tests |
| R0-R09 | Secrets are stored alongside general YAML configuration | Provider API keys are part of `conf.yaml` structure | High | Medium | P1 | Add environment/secret resolution and redacted configuration diagnostics |
| R0-R10 | Core behavior has insufficient automated regression coverage | Existing CI primarily covers Ruff and CodeQL | High | High | P0 | Add pytest infrastructure, stubs, unit tests, and lifecycle integration tests |
| R0-R11 | Provider dependencies are installed monolithically | Base project dependency set includes many mutually exclusive providers and Torch | Medium | High | P1 | Define installation profiles and optional dependency groups |
| R0-R12 | Runtime observability cannot isolate stage latency and session leaks | Logs do not consistently expose correlation IDs and lifecycle counters | Medium | High | P1 | Add session/conversation IDs, timing spans, and resource gauges |
| R0-R13 | Prompt-encoded actions couple behavior to unstructured model output | Live2D actions and thoughts are embedded in generated text | Medium | High | P2 | Introduce a structured response envelope after the foundation milestone |
| R0-R14 | Proactive-speak history behavior is inconsistent | User-side history skip and assistant-side persistence are not governed by one policy | Medium | Medium | P1 | Centralize persistence policy for synthetic/proactive events |
| R0-R15 | Static cache and model endpoints may expose more files than intended | Multiple directories are mounted directly by FastAPI | Medium | Medium | P1 | Define explicit file policies, cache identifiers, and access rules |
| R0-R16 | Server shutdown cleanup is incomplete for active sessions | `atexit` only clears cache; active session resources require async close | High | Medium | P1 | Add FastAPI lifespan shutdown management and close all active contexts |
| R0-R17 | Shared ASR/TTS engines have no declared concurrency contract | Engines are reused across sessions without capability metadata | High | Medium | P1 | Classify adapters as shareable, serialized, pooled, or session-scoped |
| R0-R18 | Upstream v2 is too immature to serve as the current product base | v2 branch is an alpha skeleton without a settled dependency/runtime implementation | Medium | High | P1 | Continue on hardened v1 while tracking and selectively adopting v2 protocols |

## 3. Initial Component Scope Rules

| Component | Initial scope decision | Rationale |
|---|---|---|
| Character configuration model | Session copy | A client may switch character independently |
| Agent instance | Session-scoped | Holds mutable memory, interrupt state, and tool behavior |
| MCP client/executor | Session-scoped | Contains client-specific send callback and execution lifecycle |
| Tool definitions/registry | Potentially shared, immutable | Discovery can be cached if mutation is removed or synchronized |
| Live2D model metadata | Shared, immutable | Model metadata is read-only after initialization |
| ASR engine | Shared only after adapter contract verification | Some implementations may not be thread-safe/reentrant |
| TTS engine | Shared only after adapter contract verification | Provider clients may be shareable; local engines may require serialization |
| Translator | Shared if stateless | Must be verified per implementation |
| Conversation task | Session/group-scoped | Must have one explicit cancellation owner |
| History selection | Session-scoped | Must never leak across clients |

## 4. Treatment Order

1. R0-R01 session isolation
2. R0-R02 and R0-R03 lifecycle cleanup
3. R0-R10 regression test foundation
4. R0-R04 path containment
5. R0-R05 and R0-R06 remote access boundary
6. R0-R07 and R0-R08 persistence
7. R0-R12 observability
8. remaining dependency, shutdown, and adapter-contract risks

## 5. Exit Rule

No risk may be marked resolved without:

- an implementation commit;
- a regression test or repeatable verification;
- documented compatibility impact;
- evidence recorded in the R0 acceptance report.
