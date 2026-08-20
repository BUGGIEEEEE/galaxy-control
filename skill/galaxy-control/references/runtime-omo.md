# OmO Native runtime mapping

Use this canonical skill directly. Do not maintain a second OmO adapter.

## Fixed route workflow

1. On the first Galaxy task in the current OmO session, after an invalidation event, or after a
   bridge/ADB error, run the full read-only preflight:

   ```sh
   uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" all
   ```

2. If ADB is unavailable and `steady_adb_enabled: true`, try the profile's fixed `connect` once.
   Success is final only after serial, model, and current boot identity verification.
3. If the fixed endpoint is unavailable and the profile records the user's
   `enable-auto-reconnect --approved` opt-in, make one already-paired recovery attempt:

   ```sh
   uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_remote_adb.py" wireless-prepare --approved
   ```

   The executable enforces the persisted opt-in before any ADB call. The action reuses an existing
   verified transport before mDNS discovery. It never pairs or scans.
   If it returns `connection_port_required`, use healthy OpenMinis read-only observation to confirm
   Wi-Fi and read Android Settings → Wireless Debugging → IP address & port. Pass only the current
   port to `wireless-connect --port`; ask the user only when that read-only path is unavailable.
4. When `steady_adb_enabled: true`, treat the verified dynamic endpoint as bootstrap-only. Run
   `legacy-enable-from-wireless --port CURRENT_CONNECTION_PORT --approved`, then fixed `connect`
   and `galaxy_doctor.py adb`. The final selected endpoint must be the profile's `:5555` endpoint.
5. Run `galaxy_screen.py doctor` only after the profile's final ADB state is verified. Treat
   `preflight_ready` as no-launch
   compatibility evidence only; `launch_verified` remains false.
6. Classify the requested operation. For later tasks in the same valid session, run only the
   matching read-only preflight:

   ```sh
   uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" openminis
   uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" adb
   uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" scrcpy
   ```

7. Use `result.checked_paths`, `result.control_paths`, and `result.reuse`.
8. Reuse a successful preflight only in the current OmO agent session. Never write live readiness
   to disk. Invalidate it after a device reboot, network change, bridge or ADB error, or scrcpy
   process death.
9. Perform one minimum action through the selected fixed adapter.
10. Read the action adapter's `result.route`. If `result.route.verification_required` is true,
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
