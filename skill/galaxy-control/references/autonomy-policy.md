# Autonomy policy

## R — automatic read-only

Run when needed for the user's task: health, versions, Accessibility status, Shizuku status, ADB
device list, identity, Tailscale online state, foreground/UI state, and post-action verification.

## L — current-request low risk

Run only when the current request clearly asks for Galaxy control: one fixed OpenMinis tap/input/key
or scroll, one harmless requested scrcpy gesture, or one
`wireless-prepare --approved` attempt to reconnect an already-paired enrolled Galaxy after the
first-session doctor reports ADB unavailable and the private profile records the user's separate
`enable-auto-reconnect --approved` opt-in. The reconnect uses only one enrolled mDNS candidate,
connects once, and verifies device identity. The stored opt-in and current-request low risk never
authorize pairing, Wireless Debugging changes, port scans, guessed ports, or fixed TCP ADB. Observe
before and verify after.

## A — explicit approval

Pairing, Wireless Debugging changes, `adb tcpip`, fixed ADB opt-in, network/Tailscale changes,
Shizuku or Accessibility permission changes, app/file changes, reboot, external communication,
payment, deletion, account, or security changes.

## X — forbidden

Generic remote shell, arbitrary Shizuku exec, arbitrary host/serial/ADB/scrcpy options, port scans,
pairing-code or token disclosure, root, broad process termination, user-data deletion, and any
OpenMinis install/update/activation/reconcile operation.

Do not restart a component already shown healthy. Do not silently downgrade a blocked operation to
an unverified success.
