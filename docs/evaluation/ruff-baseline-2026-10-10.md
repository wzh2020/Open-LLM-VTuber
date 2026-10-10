# Ruff lint baseline and ratchet policy (2026-10-10)

## Incident

The first R0 architecture v2 pull-request run passed Foundation Tests but failed the inherited `Ruff` workflow. The workflow originally called the unscoped `ruff check` action and surfaced **931 repository-wide findings** with Ruff 0.17.0. This includes inherited issues outside the eight-file R0 change set and some issues within the already existing WebSocket handler.

Largest observed finding families: `UP006` (300), `UP045` (150), `I001` (104), `UP035` (104), `BLE001` (104), and `RUF013` (41). These counts are a single CI snapshot, not an assertion of zero risk.

## Decision

Avoid changing hundreds of unrelated upstream source files in the R0.1 lifecycle fix.

1. Pin Ruff to version **0.17.0** for reproducibility.
2. **Required / blocking:** `ruff check --select E4,E7,E9,F` across the complete repository. These cover important syntax/import/undefined-name/correctness checks.
3. **Advisory / nonblocking:** full `ruff check --statistics .`; keep the result visible to CI reviewers instead of suppressing it from output.
4. New or touched code must not increase the number of full-rule findings intentionally. Future R0.5 work will establish a machine-readable baseline and a changed-lines lint ratchet, then eliminate debt in focused PRs.
5. The R0 acceptance report must explicitly distinguish the required correctness gate from advisory full-rule findings.

This is a transitional measure for inherited lint debt, **not** acceptance of current repository-wide lint quality as clean. No unrestricted `--fix` over the upstream codebase should be committed as part of this microbatch.

## Follow-up acceptance

- [ ] Required correctness lint green on PR.
- [ ] Foundation Tests green on same PR head.
- [ ] Full-rule debt count recorded and trend tracked across later PRs.
- [ ] Explicit changed-file/changed-lines style gate agreed and added before R0 closeout.
- [ ] Remove advisory exemption once repo debt reaches zero.
