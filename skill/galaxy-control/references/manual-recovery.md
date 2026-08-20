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
3. If mDNS cannot identify one current port, ask for Android's displayed connection port and run
   `wireless-connect --port CURRENT_CONNECTION_PORT`.
4. If trust was lost, request separate approval and pair once using the displayed pairing port/code.
5. Verify serial, model, and the canonical current boot UUID.
6. Run `galaxy_screen.py doctor`. Treat `preflight_ready` as compatibility evidence, not a verified
   scrcpy launch.
7. Start scrcpy only when the requested task needs a live view, control, or recording.
8. Verify OpenMinis health, Accessibility, and fresh UI state independently when semantic UI work is
   needed.

ADB or scrcpy recovery failure must not block a task that can still be completed and verified
through a healthy OpenMinis path. Report the unavailable path as degraded instead.

Official Wireless Debugging ports can change after Wi-Fi or reboot. Fixed TCP ADB normally closes
on reboot and requires a newly verified, approved bootstrap. Neither behavior is an error to hide.
If USB becomes necessary, report that the USB-free recovery goal is blocked rather than claiming
success.
