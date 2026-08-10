# Phase 2 — Portable profile and onboarding

## Goal

Replace all private constants with one strictly parsed, private profile created from a live Galaxy.

## Planned interface

```text
galaxy_setup.py doctor
galaxy_setup.py plan
galaxy_setup.py enroll --approved
galaxy_setup.py apply --approved
galaxy_setup.py resume
galaxy_setup.py verify
galaxy_setup.py show-profile
```

`show-profile` must redact sensitive or device-identifying values by default.

## Tasks

1. Store the profile under `~/Library/Application Support/galaxy-control/device.json` with directory
   mode `0700` and file mode `0600`.
2. Enroll only an exactly selected, authorized live Galaxy. Prefer a single USB device for first
   enrollment and require an explicit serial when more than one device exists.
3. Read physical serial and model using fixed ADB property queries.
4. Discover the Galaxy Tailscale IPv4 address through a fixed, read-only interface query. Accept
   only a literal address in `100.64.0.0/10`.
5. Fix the OpenMinis package and default port in code; validate the live bridge before readiness.
6. Detect Homebrew, `uv`, ADB, scrcpy, Tailscale, Python, Codex desktop, and macOS permission
   blockers without changing state.
7. `plan` emits the exact missing items and intended changes. `apply --approved` may run only the
   reviewed installers listed in source and never updates an already-present tool.
8. Make setup resumable after user-mediated macOS or Galaxy security prompts.

## Tests

- Missing, malformed, symlinked, world-readable, oversized, and stale profiles
- Zero, one, multiple, unauthorized, offline, and mismatched devices
- Tailscale IPv4 parsing and non-tailnet rejection
- No pairing code, token, device profile, or command output persisted in the repository
- Exact installer allowlist; no shell string or arbitrary package input
- Stable `READY`, `NEEDS_USER_ACTION`, and `BLOCKED` JSON envelopes

## Exit gate

Fresh temporary home directories can run doctor, enroll against fakes, resume, and verify without
touching the private source skill.
