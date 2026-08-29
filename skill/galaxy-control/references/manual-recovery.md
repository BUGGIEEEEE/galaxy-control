# Manual recovery

After a Galaxy reboot, diagnose first. Do not assume every step is needed.

## User actions, only when reported unavailable

1. Unlock the Galaxy.
2. Confirm a trusted network and Tailscale; open Tailscale once only if it remains offline.
3. Confirm official Wireless Debugging if remote ADB is required.
4. Check `shizuku-status` before Start. Start Shizuku only if the task needs it, it is not already
   `READY`, and the user approves. Never restart a ready server merely to redisplay its ADB port.
5. Open Minis if the bridge remains unavailable; use its documented local bridge start control only
   if status proves it stopped.
6. Read Android's current connection port when Wireless Debugging recovery is needed.

## Mac actions

1. Run `galaxy_doctor.py all`.
2. When `steady_adb_enabled: true`, try fixed `connect` before dynamic recovery.
3. If the enrolled ADB transport is still absent and the private profile records the user's explicit
   auto-reconnect opt-in, run `wireless-prepare --approved` once.
4. If mDNS cannot identify one current port, re-observe the current UI first. Use a fresh Shizuku
   launcher line `Starting with wireless adb in port PORT...` when it is already visible. Otherwise,
   when OpenMinis is healthy, inspect Wi-Fi and Android's Wireless Debugging screen read-only.
   Run exactly `wireless-connect --port CURRENT_CONNECTION_PORT`; do not append `--approved`.
   Ask the user only when neither observation path is available.
5. If trust was lost, request separate approval and pair once using the displayed pairing port/code.
6. Verify serial, model, and the canonical current boot UUID.
7. For `steady_adb_enabled: true`, run the fixed `legacy-enable-from-wireless` profile, reconnect
   `:5555`, and verify ADB again. The dynamic port is not that profile's final state.
8. If that leaves the known dynamic endpoint listed as `offline`, remove only it with
   `wireless-disconnect --port CURRENT_CONNECTION_PORT`, run fixed `connect` again, and verify ADB
   again. Do not treat an `offline` fixed endpoint as connected merely because it is listed.
9. Run `galaxy_screen.py doctor`. Treat `preflight_ready` as compatibility evidence, not a verified
   scrcpy launch.
10. Start scrcpy only when the requested task needs a live view, control, or recording.
11. Verify OpenMinis health, Accessibility, and fresh UI state independently when semantic UI work is
    needed.

ADB or scrcpy recovery failure must not block a task that can still be completed and verified
through a healthy OpenMinis path. Report the unavailable path as degraded instead.

Official Wireless Debugging ports can change after Wi-Fi or reboot. Fixed TCP ADB normally closes
on reboot and requires a newly verified bootstrap. For an opted-in fixed profile, do not report
completion while it remains on the dynamic bootstrap endpoint. Neither behavior is an error to hide.
When the requested end state is ADB or scrcpy only, do not make Shizuku readiness an extra completion
condition or restart it after fixed `:5555` succeeds. Require fresh Shizuku readiness only for an
operation that explicitly depends on Shizuku.
If USB becomes necessary, report that the USB-free recovery goal is blocked rather than claiming
success.
