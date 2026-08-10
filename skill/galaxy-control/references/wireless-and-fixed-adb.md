# Wireless and fixed ADB

Official Wireless Debugging and fixed TCP ADB have different roles.

## Official Wireless Debugging

- Pairing port and connection port are separate, dynamic values shown by Android.
- Pairing uses a six-digit code read from stdin only. Never put it in argv, JSON, environment,
  logs, files, or reports. Never retry automatically.
- A connection port is accepted only as decimal `1..65535`, excluding `5555`.
- The adapter fixes the host to the enrolled Tailscale IPv4 address and verifies physical serial,
  model, and boot session after connecting.
- Never scan or guess ports. A cached endpoint is valid only for its enrolled profile and boot.

## Optional fixed TCP ADB 5555

New profiles disable it. Enabling the preference requires:

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_setup.py" enable-steady-adb --approved
```

Changing the live transport is a separate approved command. It runs only after exact identity and,
for wireless bootstrap, boot-session verification.

Fixed TCP ADB may listen on more than the Tailscale interface. While Wi-Fi is enabled, devices on
the same LAN may attempt to reach port `5555`; ADB RSA authentication still matters. Tailscale ACLs
do not block direct LAN traffic, and changing the port is not a meaningful security boundary.

Prefer official Wireless Debugging unless the user explicitly accepts fixed TCP ADB's exposure and
needs a Wi-Fi-independent steady path. Never run `setprop`, force-restart adbd, root, Shizuku exec,
or an arbitrary `adb tcpip` fallback.
