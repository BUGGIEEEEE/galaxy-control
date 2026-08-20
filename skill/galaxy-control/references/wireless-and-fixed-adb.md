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

### First-session paired reconnect

After the user has prepared Wireless Debugging and an existing pairing trust, enable the private
profile preference once:

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_setup.py" enable-auto-reconnect --approved
```

The user may revoke it with `disable-auto-reconnect --approved`. While enabled, a Galaxy-control
request may make one bounded preparation attempt:

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_remote_adb.py" wireless-prepare --approved
```

The adapter applies this order:

1. Read the current ADB device list.
2. Reuse exactly one enrolled transport only after serial, model, and current boot UUID verification.
   Native ADB mDNS auto-connections are routing candidates, not identity evidence. Fixed TCP `5555`
   is excluded.
3. If none exists, run the fixed host command `adb mdns services`.
4. Accept only `_adb-tls-connect._tcp` rows whose service instance starts with the enrolled physical
   serial. Duplicate rows for one port are deduplicated; zero candidates returns
   `connection_port_required`; multiple ports returns `mdns_ambiguous`.
5. Treat the advertised port only as routing data. Construct the endpoint from the enrolled Galaxy
   Tailscale IPv4 address and connect once.
6. Persist boot-bound endpoint state only after exact identity verification succeeds.

mDNS normally requires a multicast-capable shared LAN and may not cross Tailscale, routed networks,
VPN filters, or VLANs. Discovery failure never permits a scan, guessed port, stale pre-reboot port,
fixed port `5555`, or automatic pairing. Ask the user for Android's displayed current connection
port and use the existing `wireless-connect --port` command.

The `--approved` marker is valid only when the executable also reads the persisted private-profile
opt-in. Neither value approves a new trust relationship.

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
