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

The session applies this order:

1. Read `steady_adb_enabled`. If true, try the fixed profile `connect` once and accept it only after
   serial, model, and current boot UUID verification.
2. If unavailable, read the current ADB device list.
3. Reuse exactly one enrolled transport only after serial, model, and current boot UUID verification.
   Native ADB mDNS auto-connections are routing candidates, not identity evidence. Fixed TCP `5555`
   is excluded from the dynamic preparation action because it was already probed separately.
4. If none exists, run the fixed host command `adb mdns services`.
5. Accept only `_adb-tls-connect._tcp` rows whose service instance starts with the enrolled physical
   serial. Duplicate rows for one port are deduplicated; zero candidates returns
   `connection_port_required`; multiple ports returns `mdns_ambiguous`.
6. Treat the advertised port only as routing data. Construct the endpoint from the enrolled Galaxy
   Tailscale IPv4 address and connect once.
7. Persist boot-bound endpoint state only after exact identity verification succeeds.
8. If `steady_adb_enabled: true`, use that verified dynamic endpoint only to run the fixed
   `legacy-enable-from-wireless` profile, reconnect `:5555`, and verify serial, model, and boot UUID.

mDNS normally requires a multicast-capable shared LAN and may not cross Tailscale, routed networks,
VPN filters, or VLANs. Discovery failure never permits a scan, guessed port, stale pre-reboot port,
fixed port `5555`, or automatic pairing.

When `wireless-prepare` returns `connection_port_required`, use fresh evidence in this order:

1. Re-observe the current UI. If the Shizuku launcher output from the user's authorized Start action
   already shows `Starting with wireless adb in port PORT...`, use that displayed connection port.
2. Otherwise, with healthy OpenMinis plus Accessibility, inspect Wi-Fi and Android's Wireless
   Debugging settings read-only and use the displayed current `IP address & port`.
3. Ask the user only when neither healthy read-only path can provide the value.

Run exactly `wireless-connect --port CURRENT_CONNECTION_PORT`; `wireless-connect` does not accept
`--approved`. Never leave an explicit current port to search for another one, infer a hidden row
coordinate, or reuse launcher output from before a reboot or network change. Do not press Shizuku
Start just to redisplay a port when `shizuku-status` is already `READY`; Start can stop and restart
the existing server.

The `--approved` marker is valid only when the executable also reads the persisted private-profile
opt-in. Neither value approves a new trust relationship.

## Profile-selected fixed TCP ADB 5555

New profiles disable it. Enabling the preference requires:

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_setup.py" enable-steady-adb --approved
```

Changing the live transport is a separate approved command. It runs only after exact identity and,
for wireless bootstrap, boot-session verification.

For `steady_adb_enabled: true`, dynamic Wireless Debugging is bootstrap rather than the final state.
The session is ADB-ready only after `legacy-enable-from-wireless`, fixed `connect`, and a fresh ADB
doctor all succeed against the profile's `:5555` endpoint. Profiles with the setting disabled keep
the verified dynamic endpoint as their final state.

After fixed `:5555` succeeds, a known dynamic endpoint may remain registered locally as `offline`.
Remove only that endpoint with
`wireless-disconnect --port CURRENT_CONNECTION_PORT`, run fixed `connect` again, and then rerun the
ADB doctor. This is local transport cleanup, not permission to disconnect another endpoint.
Endpoint presence alone is not readiness; the exact fixed endpoint must return to `state: device`
and pass identity and current-boot verification.

If the requested result is only ADB or scrcpy readiness, Shizuku was bootstrap support and need not
remain running after fixed `:5555` is verified. Do not restart it merely to produce an unrelated
green status. When an explicitly requested operation depends on Shizuku, verify `shizuku-status`
again after the ADB transport changes.

Fixed TCP ADB may listen on more than the Tailscale interface. While Wi-Fi is enabled, devices on
the same LAN may attempt to reach port `5555`; ADB RSA authentication still matters. Tailscale ACLs
do not block direct LAN traffic, and changing the port is not a meaningful security boundary.

Prefer official Wireless Debugging for profiles without the fixed-path opt-in. Honor
`steady_adb_enabled: true` as the user's selected final ADB path. Never run `setprop`, force-restart
adbd, root, Shizuku exec, or an arbitrary `adb tcpip` fallback.
