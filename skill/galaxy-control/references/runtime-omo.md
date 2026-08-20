# OmO Native runtime mapping

Use this canonical skill directly. Do not maintain a second OmO adapter.

## Fixed route workflow

1. On the first Galaxy task in the current OmO session, after an invalidation event, or after a
   bridge/ADB error, run the full read-only preflight:

   ```sh
   uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" all
   ```

2. If the enrolled ADB transport is unavailable and the private profile records the user's
   `enable-auto-reconnect --approved` opt-in, make one already-paired recovery attempt:

   ```sh
   uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_remote_adb.py" wireless-prepare --approved
   ```

   The executable enforces the persisted opt-in before any ADB call. The action reuses an existing
   verified transport before mDNS discovery. It never pairs or scans.
   If it returns `connection_port_required`, ask for Android's currently displayed connection port.
   Do not block an OpenMinis-only task when ADB remains unavailable.
3. Run `galaxy_screen.py doctor` after ADB becomes available. Treat `preflight_ready` as no-launch
   compatibility evidence only; `launch_verified` remains false.
4. Classify the requested operation. For later tasks in the same valid session, run only the
   matching read-only preflight:

   ```sh
   uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" openminis
   uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" adb
   uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" scrcpy
   ```

5. Use `result.checked_paths`, `result.control_paths`, and `result.reuse`.
6. Reuse a successful preflight only in the current OmO agent session. Never write live readiness
   to disk. Invalidate it after a device reboot, network change, bridge or ADB error, or scrcpy
   process death.
7. Perform one minimum action through the selected fixed adapter.
8. Read the action adapter's `result.route`. If `result.route.verification_required` is true,
   freshly verify through one of `result.route.verify_with`; prefer a different path when it
   materially improves confidence.

| Task shape | Preflight | Adapter |
| --- | --- | --- |
| Visible text, buttons, typing, global keys, simple scroll | `openminis` | `galaxy_control.sh` |
| Package, file, process, or system fact | `adb` | `galaxy_remote_adb.py` |
| Live motion, drag, rotation, or compound gesture | `scrcpy` | `galaxy_screen.py` |

The `scrcpy` preflight includes ADB identity because scrcpy uses ADB as its transport. It does not
start scrcpy or prove a video stream, window, or Computer Use permission. Starting scrcpy `control`
does not itself operate the window. If OmO exposes no desktop-control tool, use OpenMinis for
supported actions and report unsupported visual gestures as blocked.

Do not turn the fixed adapters into a generic ADB, shell, scrcpy, HTTP, host, or port surface.
