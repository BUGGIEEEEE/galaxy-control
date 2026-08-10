# Phase 4 — Skill and user contract

## Goal

Package a concise skill and repository-level user documentation that a new macOS/Galaxy user can
follow safely.

## Tasks

1. Keep `skill/galaxy-control/SKILL.md` below 500 lines and route details through one-level
   references.
2. Generate matching `agents/openai.yaml` metadata.
3. Document the verified loop: observe, select one path, perform one minimum action, independently
   verify, then continue.
4. Document setup states and exact user-mediated steps for macOS permissions, Tailscale, Wireless
   Debugging, ADB trust, Accessibility, and optional Shizuku.
5. Add repository-level `README.md`, `SECURITY.md`, MIT `LICENSE`, support matrix, install command,
   uninstall paths, and recovery instructions. Do not add README or changelog files inside the
   installed skill directory.
6. State that OpenMinis must already be installed and compatible. Never install, update, activate,
   or reconcile it from this distribution.

## Verification

- Codex `quick_validate.py` passes.
- `agents/openai.yaml` matches the skill description and default prompt names `$galaxy-control`.
- Every reference is linked directly from `SKILL.md` with a clear read condition.
- Commands in the repository documentation match `--help` and automated CLI tests.

## Exit gate

A new user can identify automatic steps, required physical actions, approval boundaries, support
limits, and rollback paths without reading source code.
