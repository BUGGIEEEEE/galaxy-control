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

1. Run `galaxy_doctor.py`.
2. If pairing trust remains, run `wireless-connect --port CURRENT_CONNECTION_PORT`.
3. If trust was lost, request approval and pair once using the displayed pairing port/code.
4. Verify serial, model, and boot identity.
5. Start scrcpy only after ADB identity succeeds.
6. Verify OpenMinis health, Accessibility, and fresh UI state independently.

Official Wireless Debugging ports can change after Wi-Fi or reboot. Fixed TCP ADB normally closes
on reboot and requires a newly verified, approved bootstrap. Neither behavior is an error to hide.
If USB becomes necessary, report that the USB-free recovery goal is blocked rather than claiming
success.
