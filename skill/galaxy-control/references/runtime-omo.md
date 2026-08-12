# OmO Native runtime mapping

Use this canonical skill directly. Do not maintain a second OmO adapter.

## Fixed route workflow

1. Classify the requested operation before probing the phone.
2. Run only the matching read-only preflight:

   ```sh
   uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" openminis
   uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" adb
   uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" scrcpy
   ```

3. Use `result.checked_paths`, `result.control_paths`, and `result.reuse`.
4. Reuse a successful preflight only in the current OmO agent session. Never write live readiness
   to disk. Invalidate it after a device reboot, network change, bridge or ADB error, or scrcpy
   process death.
5. Perform one minimum action through the selected fixed adapter.
6. Read the action adapter's `result.route`. If `result.route.verification_required` is true,
   freshly verify through one of `result.route.verify_with`; prefer a different path when it
   materially improves confidence.

| Task shape | Preflight | Adapter |
| --- | --- | --- |
| Visible text, buttons, typing, global keys, simple scroll | `openminis` | `galaxy_control.sh` |
| Package, file, process, or system fact | `adb` | `galaxy_remote_adb.py` |
| Live motion, drag, rotation, or compound gesture | `scrcpy` | `galaxy_screen.py` |

The `scrcpy` preflight includes ADB identity because scrcpy uses ADB as its transport. Starting
scrcpy `control` does not itself operate the window. If OmO exposes no desktop-control tool, use
OpenMinis for supported actions and report unsupported visual gestures as blocked.

Do not turn the fixed adapters into a generic ADB, shell, scrcpy, HTTP, host, or port surface.
