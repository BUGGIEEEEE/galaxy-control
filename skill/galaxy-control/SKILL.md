---
name: "galaxy-control"
description: "Inspect, set up, and safely control an enrolled Samsung Galaxy from Codex on macOS using a personalized fixed OpenMinis Control v2 bridge, fixed-profile scrcpy, and reviewed USB or wireless ADB paths. Use for Galaxy setup diagnosis, private bridge packaging, screen reading, Android navigation, verified UI changes, One UI app-drawer or folder evidence, screen viewing/control/recording, ADB recovery, or independent result verification. Never install, update, activate, or reconcile the OpenMinis app."
---

# Galaxy Control

Control one enrolled Galaxy through the narrowest suitable path. For every state change: observe,
perform one minimum action, independently verify the result, and only then continue.

## Locate the skill

Set `GALAXY_SKILL_ROOT` to this installed skill directory. Under the default Codex layout it is:

```sh
GALAXY_SKILL_ROOT="${CODEX_HOME:-$HOME/.codex}/skills/galaxy-control"
```

Do not use a development checkout or another user's profile.

Under OmO Native, first read [runtime-omo.md](references/runtime-omo.md).

## Set up a new user

Read [setup-and-enrollment.md](references/setup-and-enrollment.md) before any first-time setup,
missing dependency, or device enrollment. Start read-only:

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_setup.py" doctor
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_setup.py" plan
```

The setup adapter may install only its named missing Mac prerequisites after `--approved`. It does
not install or update the OpenMinis app. Tailscale login, macOS privacy dialogs, Galaxy unlock, Wireless
Debugging, ADB trust, Accessibility, and Shizuku are user-mediated security steps.

If OpenMinis health on port `43129` returns `network_error`, read
[openminis-bridge-distribution.md](references/openminis-bridge-distribution.md). Do not copy another
user's bridge artifact or edit public source IP constants. Build a private artifact from the enrolled
Galaxy profile and the Mac's current Tailscale identity:

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_bridge_package.py" doctor
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_bridge_package.py" \
  build --output /ABSOLUTE/NEW/PRIVATE_DIRECTORY --approved
```

The build changes only the named Mac output directory. Installing the generated artifact changes
the Galaxy's local Minis files and requires the user's approval. Follow its exact `INSTALL.md` once,
then use `LIFECYCLE.md` for fixed `status`, conditional `start`, and `stop` only.

## Start every Galaxy task

For the first Galaxy task in the current agent session, after reboot/network changes, or after a
bridge/ADB error, run the read-only full doctor once:

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" all
```

If that report has no verified ADB transport, read the private profile. When
`steady_adb_enabled: true`, first make one fixed-profile `connect` attempt. A successful fixed
connection must verify serial, model, and current boot identity and is the final ADB state.

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_remote_adb.py" connect
```

If the fixed endpoint is unavailable and the profile has `auto_reconnect_adb_enabled: true`, make
one bounded attempt to reuse or restore an already-paired official Wireless Debugging transport:

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_remote_adb.py" wireless-prepare --approved
```

This fixed action first reuses an existing identity-verified transport. Otherwise it reads only
`adb mdns services`, accepts one enrolled `_adb-tls-connect._tcp` port, connects once to the enrolled
Tailscale host, and verifies serial, model, and current boot identity. ADB may natively auto-connect
an already-paired mDNS service before the explicit connect; that transport is accepted only after
the same full identity check. The action never pairs, scans, guesses a port, changes Wireless
Debugging, or enables fixed TCP ADB.

If it returns `connection_port_required`, re-observe the current UI before navigating away. Fresh
Shizuku launcher output from the user's authorized Start action may already contain
`Starting with wireless adb in port PORT...`; use that displayed connection port directly. Do not
press Start merely to reveal a port when `shizuku-status` is already `READY`, because Start can stop
and restart the existing Shizuku server. Otherwise, when OpenMinis health plus Accessibility are
available, inspect Wi-Fi status and open Android's Wireless Debugging settings read-only. Read only
the current `IP address & port` value. In either case, run exactly
`wireless-connect --port CURRENT_CONNECTION_PORT`; this command does not accept `--approved`.
Never toggle Wireless Debugging, tap a pairing control, infer a hidden row coordinate, or reuse a
port observed before a reboot or network change. Ask the user to read the port only when neither
healthy read-only path can inspect it.

For a profile with `steady_adb_enabled: true`, the verified dynamic endpoint is bootstrap-only.
Apply the already-approved steady preference, reconnect the enrolled fixed endpoint, and verify it:

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_remote_adb.py" \
  legacy-enable-from-wireless --port CURRENT_CONNECTION_PORT --approved
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_remote_adb.py" connect
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" adb
```

Do not report ADB readiness for that profile until the selected endpoint is the profile's fixed
`:5555` endpoint with matching serial, model, and a current boot-session hash. A failed ADB
preparation must not block a healthy OpenMinis-only task.

If the verified fixed connection leaves the known dynamic endpoint listed as `offline`, remove only
that endpoint from the Mac ADB server with
`wireless-disconnect --port CURRENT_CONNECTION_PORT`, run fixed `connect` again, and then rerun the
ADB doctor. Do not disconnect another endpoint or trust endpoint presence without `state: device`.
When the requested end state is ADB or scrcpy only, Shizuku is bootstrap support, not a final
requirement; do not restart it after fixed `:5555` is verified. If the requested task actually uses
Shizuku, freshly verify `shizuku-status` after every ADB transport change.

After ADB preparation, run the no-launch scrcpy compatibility preflight:

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_screen.py" doctor
```

`preflight_ready: true` with `launch_verified: false` proves only the enrolled ADB target, installed
scrcpy, and required safe options. It does not prove that a scrcpy process, video stream, window, or
macOS Computer Use permission works.

For later tasks in the same valid session, classify the task and run only the matching read-only
preflight:

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" openminis
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" adb
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" scrcpy
```

The scrcpy target includes its ADB dependency. Reuse a successful result only in the current agent
session and invalidate it on any event listed in `result.reuse.invalidate_on`; live readiness is
never persisted.

Before semantic UI control, require fresh OpenMinis health and Accessibility evidence:

```sh
"$GALAXY_SKILL_ROOT/scripts/galaxy_control.sh" health
"$GALAXY_SKILL_ROOT/scripts/galaxy_control.sh" a11y-status
"$GALAXY_SKILL_ROOT/scripts/galaxy_control.sh" ui-info
```

Do not expose unrelated messages, notifications, accounts, tokens, pairing codes, or screen text in
logs or reports.

## Choose one input path

| Request | First input path |
| --- | --- |
| Understand text, buttons, selection, or foreground UI | OpenMinis `ui-info`/`ui-dump` |
| Tap text, type, use global keys, or directionally scroll | OpenMinis fixed command |
| Watch motion, rotate, drag, or perform a complex gesture | scrcpy `control` + Computer Use |
| Read packages, processes, files, hashes, or system facts | A reviewed fixed ADB/Shizuku query only |

Read [task-routing.md](references/task-routing.md) when more than one path is plausible. Never add a
generic shell, arbitrary ADB command, arbitrary host, port scan, or arbitrary scrcpy option.

For Samsung One UI app-drawer inventory, folder creation, or app moves, read both
[oneui-launcher.md](references/oneui-launcher.md) and
[oneui-folder-picker.md](references/oneui-folder-picker.md) before acting. A single folder picker is
not a complete app inventory, a selected-count label proves quantity but not app identity, and every
layout coordinate becomes stale after a launcher change. Use the local artifact checkers below to
validate saved evidence; they never select, move, or otherwise control the phone. `replay` and
`union` write only their explicitly named new Mac output directory, while `check` writes nothing.

## Apply the verification loop

1. Observe immediately before acting.
2. Choose one path and perform one minimum authorized action.
3. If execution is confirmed false, another suitable path may try once.
4. If execution is unclear, do not repeat the action; change only the observation path.
5. Verify the requested end state, preferably through a different path.
6. Continue only when the result is proven.

Read [verification.md](references/verification.md) for every state-changing or consequential task.
Opening scrcpy, receiving an HTTP 200, or returning an ADB success code is not proof of the user's
requested outcome.

After performing an action through OpenMinis, ADB, or scrcpy, read that adapter result's
`result.route` to report the actual controller and transport. When
`result.route.verification_required` is true, freshly verify through an appropriate entry in
`result.route.verify_with`.

For multi-app One UI work, also maintain an item-level selection ledger and progress log. Do not
repeat an uncertain `Done` or move action. Re-observe the destination and source instead.

## Fixed command surfaces

OpenMinis Mac client:

```text
health | shizuku-status | device-info | battery | a11y-status | ui-info | ui-dump
input-key BACK|HOME|RECENTS|NOTIFICATIONS
tap-text TEXT | tap-xy X Y | input-text TEXT
scroll-xy X Y up|down|left|right DISTANCE
```

`input-text` enters text only. Never send, submit, post, or confirm unless the user explicitly asks.

OpenMinis bridge package:

```text
doctor | build --output ABSOLUTE_NEW_PRIVATE_DIRECTORY --approved
```

It accepts no host, IP, port, token, shell command, or arbitrary installer option.

scrcpy:

```text
doctor | view [--serial LIVE_SERIAL] | control [--serial LIVE_SERIAL]
record --output ABSOLUTE_NEW_MP4_OR_MKV [--serial LIVE_SERIAL] | stop
```

Read [scrcpy-policy.md](references/scrcpy-policy.md) before `control`, `record`, or `stop`.

Saved One UI evidence (phone-read-only local artifact profiles):

```text
oneui_inventory.py replay --input ABSOLUTE_JSONL --output ABSOLUTE_NEW_DIRECTORY \
  --capture-session SAFE_ID --source SAFE_ID
oneui_inventory.py union --input ABSOLUTE_TSV --input ABSOLUTE_TSV \
  --output ABSOLUTE_NEW_DIRECTORY
oneui_ledger.py check --manifest ABSOLUTE_TSV --ledger ABSOLUTE_TSV \
  --progress ABSOLUTE_TSV --selected-count N
```

These profiles expose no OpenMinis, ADB, scrcpy, shell, selection, or completion action. `replay`
and `union` create only the named new local output directory; do not run them when the user forbids
all Mac file writes. A successful artifact check proves internal consistency, not current Galaxy
state, unless the referenced observations were independently captured and verified.

ADB:

```text
doctor | status | connect | disconnect | recover
wireless-doctor | wireless-status
wireless-prepare --approved
wireless-pair --port PAIRING_PORT --approved
wireless-connect|wireless-disconnect|wireless-recover --port CONNECTION_PORT
legacy-enable-from-wireless --port CONNECTION_PORT --approved
enable --approved | restore-usb --approved
```

Only command forms that display `--approved` accept it. In particular,
`wireless-connect --port CONNECTION_PORT --approved` is invalid.

Read [wireless-and-fixed-adb.md](references/wireless-and-fixed-adb.md) before pairing, dynamic-port
use, fixed TCP ADB, or transport recovery. Fixed TCP ADB is disabled in a new profile until the user
accepts its LAN-exposure warning.

## Approval boundary

Automatic read-only work includes doctor checks, identity verification, version checks, UI
observation needed for the request, and post-action verification.

The user's current Galaxy-control request authorizes only low-risk actions needed for that request.
One `wireless-prepare --approved` attempt is allowed only after the user separately enabled the
private profile preference with `galaxy_setup.py enable-auto-reconnect --approved`. When the same
profile also has the separately approved `steady_adb_enabled: true`, a current Galaxy-control
request authorizes one exact, boot-verified promotion through
`legacy-enable-from-wireless --port CURRENT_CONNECTION_PORT --approved` and one fixed `connect`.
These persisted opt-ins never authorize pairing, port scanning, Wireless Debugging changes, or
arbitrary `adb tcpip`.
It does not authorize sending, payment, deletion, account changes, other security/permission
changes, pairing, a fixed-ADB preference change, network changes, reboot, app installation/update,
or file modification.

Read [autonomy-policy.md](references/autonomy-policy.md) when approval is uncertain. Never install,
update, activate, repair, or reconcile the OpenMinis app, and never delete its app data. The reviewed
Control v2 bridge runtime may be installed only from the locally generated content-addressed artifact
after approval; this is separate from APK installation or app update.

## Recovery

Read [manual-recovery.md](references/manual-recovery.md) after a Galaxy reboot or when Tailscale,
OpenMinis, Shizuku, Wireless Debugging, or ADB is unavailable. Diagnose each component separately;
restart or change only the component proven unavailable.
