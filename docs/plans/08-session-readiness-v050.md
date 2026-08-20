# Phase 8 — Session readiness and paired ADB recovery

## Goal

After the user has unlocked the enrolled Galaxy and prepared Tailscale, OpenMinis, the Control v2
bridge, and any required Shizuku permission, let Galaxy Control make one bounded attempt to restore
an already-paired ADB transport. Confirm scrcpy compatibility without starting a screen process.
Keep OpenMinis-only work available when ADB recovery is unavailable.

## Safety boundary

- Read the current ADB device list before discovery or connection.
- Require the separately approved private-profile auto-reconnect preference before any preparation
  ADB call.
- Reuse exactly one identity-verified enrolled transport without reconnecting it.
- Treat native ADB mDNS auto-connections as routing candidates only and exclude fixed TCP `5555`.
- Discover only `_adb-tls-connect._tcp` advertisements whose service instance names contain the
  enrolled physical serial.
- Treat mDNS data as routing information only. Build the endpoint from the enrolled Tailscale IPv4
  address and the validated discovered port.
- Connect once only after current-request approval. Never pair, scan ports, guess a port, enable
  Wireless Debugging, start Shizuku, or use fixed TCP ADB.
- Verify physical serial, model, and a canonical current boot UUID before saving boot-bound state.
- Disconnect a newly attached endpoint after failed identity verification. Reverify full identity
  before scrcpy preflight readiness and process start.
- Do not start scrcpy during readiness checks. Report `launch_verified: false`.
- If discovery or connection fails, preserve other healthy control paths and return an actionable
  degraded result.

## Tasks

### 1. Correct read-only readiness facts

Files:

- `tests/test_doctor.py`
- `skill/galaxy-control/scripts/galaxy_doctor_core.py`
- `tests/test_screen_session.py`
- `skill/galaxy-control/scripts/galaxy_screen_core.py`
- `skill/galaxy-control/scripts/galaxy_screen_session.py`

Tests first:

1. Reproduce the live OpenMinis `{ok, data, route}` wrapper and require
   `data.running=true`, including Shizuku authorization.
2. Require exactly one enrolled ADB transport for scrcpy preflight while ignoring unrelated devices.
3. Check required scrcpy options through `--help` without creating the app wrapper or launching a
   process.
4. Return `preflight_ready` and `launch_verified=false`.

### 2. Add bounded mDNS discovery and paired reconnect

Files:

- `tests/test_wireless_adb.py`
- `skill/galaxy-control/scripts/galaxy_adb.py`
- `skill/galaxy-control/scripts/galaxy_remote_adb_wireless.py`
- `skill/galaxy-control/scripts/galaxy_remote_adb.py`

Tests first:

1. Parse only exact `_adb-tls-connect._tcp` service rows and validated dynamic ports.
2. Reject zero or multiple registered-serial candidates without guessing.
3. Reuse one existing enrolled transport without running mDNS or `adb connect`.
4. Require request-level approval before a reconnect attempt.
5. Connect once to the enrolled Tailscale host and discovered port.
6. Verify serial, model, and canonical boot UUID before writing state.
7. Return explicit `connection_port_required` or `adb_connect_failed` failures without pairing.

### 3. Update session policy and recovery guidance

Files:

- `skill/galaxy-control/SKILL.md`
- `skill/galaxy-control/references/runtime-omo.md`
- `skill/galaxy-control/references/autonomy-policy.md`
- `skill/galaxy-control/references/wireless-and-fixed-adb.md`
- `skill/galaxy-control/references/manual-recovery.md`
- `README.md`
- `docs/releases/v0.5.0.md`
- `pyproject.toml`

Document one first-session readiness pass, later selective preflight, request-level approval for one
already-paired reconnect, non-blocking degraded paths, manual connection-port fallback, and the
difference between scrcpy preflight and a verified launch.

## Verification

Run once after implementation:

```sh
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv run pytest
```

Then install or atomically upgrade from the verified public release, preserve the enrolled private
profile, enable its explicit opt-in, and run the installed fixed commands:

```sh
python3 scripts/install_skill.py --upgrade --approved
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_setup.py" enable-auto-reconnect --approved
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" all
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_remote_adb.py" wireless-prepare --approved
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_screen.py" doctor
```

Do not claim an actual scrcpy launch unless a later requested `view`, `control`, or `record` command
starts successfully and its requested outcome is independently verified.
