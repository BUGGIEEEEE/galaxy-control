# Phase 6 — Automated and real-user pilot verification

## Goal

Separate package correctness from proof that another user's Mac and Galaxy can be controlled.

## Automated gates

1. Unit tests for config, parsing, routing, errors, and security boundaries.
2. CLI integration tests in temporary home directories with fake ADB, scrcpy, Tailscale, and
   OpenMinis endpoints.
3. One end-to-end simulated onboarding narrative and one failure narrative.
4. Ruff, BasedPyright, Python compile, no-excuse audit, skill validators, `git diff --check`, and
   repository privacy scan.
5. Re-run the private source's original tests and verify its commit, hashes, and clean worktree.

## Real-user pilot

1. Install from the GitHub tag on a clean second Mac user account.
2. Run read-only doctor and review the exact setup plan.
3. Apply only approved missing prerequisites.
4. Enroll the second user's live Galaxy and confirm its physical serial, model, and Tailscale IP
   without printing them in the report.
5. Verify OpenMinis health, protocol compatibility, Accessibility, and fresh UI state.
6. Pair official Wireless Debugging if required; disconnect USB.
7. Display scrcpy, issue one harmless Computer Use input, and independently verify via OpenMinis.
8. Restore state, stop only the managed process, disconnect, and reconnect.
9. If fixed TCP ADB is explicitly chosen, repeat the warning and run its separate approved test.
10. Record whether reboot recovery is automatic, guided, blocked, or not tested.

## Exit gate

Automated completion is `PACKAGE_READY`. Only real second-user evidence can advance to
`PILOT_INSTALL_VERIFIED` and `PILOT_E2E_VERIFIED`.
