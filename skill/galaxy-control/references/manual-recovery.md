# Manual recovery

After a Galaxy reboot, diagnose first. Do not assume every step is needed.

## User actions, only when reported unavailable

1. Unlock the Galaxy.
2. Confirm a trusted network and Tailscale; open Tailscale once only if it remains offline.
3. Confirm official Wireless Debugging if remote ADB is required.
4. Start Shizuku only if the task needs it and the user approves.
5. Open Minis if the bridge remains unavailable; use its documented local bridge start control only
   if status proves it stopped.
6. Read Android's current connection port when Wireless Debugging recovery is needed.

## Mac actions

1. Run `galaxy_doctor.py all`.
2. If the enrolled ADB transport is absent and the private profile records the user's explicit
   auto-reconnect opt-in, run `wireless-prepare --approved` once.
3. When `steady_adb_enabled: true`, try fixed `connect` before dynamic recovery.
4. If mDNS cannot identify one current port and OpenMinis is healthy, inspect Wi-Fi and Android's
   Wireless Debugging screen read-only. Run `wireless-connect --port CURRENT_CONNECTION_PORT`.
   Ask the user only when that observation path is unavailable.
5. If trust was lost, request separate approval and pair once using the displayed pairing port/code.
6. Verify serial, model, and the canonical current boot UUID.
7. For `steady_adb_enabled: true`, run the fixed `legacy-enable-from-wireless` profile, reconnect
   `:5555`, and verify ADB again. The dynamic port is not that profile's final state.
8. Run `galaxy_screen.py doctor`. Treat `preflight_ready` as compatibility evidence, not a verified
   scrcpy launch.
9. Start scrcpy only when the requested task needs a live view, control, or recording.
10. Verify OpenMinis health, Accessibility, and fresh UI state independently when semantic UI work is
   needed.

ADB or scrcpy recovery failure must not block a task that can still be completed and verified
through a healthy OpenMinis path. Report the unavailable path as degraded instead.

Official Wireless Debugging ports can change after Wi-Fi or reboot. Fixed TCP ADB normally closes
on reboot and requires a newly verified bootstrap. For an opted-in fixed profile, do not report
completion while it remains on the dynamic bootstrap endpoint. Neither behavior is an error to hide.
If USB becomes necessary, report that the USB-free recovery goal is blocked rather than claiming
success.
