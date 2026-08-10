---
name: "galaxy-control"
description: "Inspect, set up, and safely control an enrolled Samsung Galaxy from Codex on macOS using an existing compatible OpenMinis Control v2 bridge, fixed-profile scrcpy, and reviewed USB or wireless ADB paths. Use for Galaxy setup diagnosis, screen reading, Android navigation, verified UI changes, screen viewing/control/recording, ADB recovery, or independent result verification. Never install, update, activate, or reconcile OpenMinis."
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

## Set up a new user

Read [setup-and-enrollment.md](references/setup-and-enrollment.md) before any first-time setup,
missing dependency, or device enrollment. Start read-only:

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_setup.py" doctor
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_setup.py" plan
```

The setup adapter may install only its named missing Mac prerequisites after `--approved`. It does
not install or update OpenMinis. Tailscale login, macOS privacy dialogs, Galaxy unlock, Wireless
Debugging, ADB trust, Accessibility, and Shizuku are user-mediated security steps.

## Start every Galaxy task

Run the combined read-only doctor whenever path availability matters:

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py"
```

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

## Fixed command surfaces

OpenMinis:

```text
health | shizuku-status | device-info | battery | a11y-status | ui-info | ui-dump
input-key BACK|HOME|RECENTS|NOTIFICATIONS
tap-text TEXT | tap-xy X Y | input-text TEXT
scroll-xy X Y up|down|left|right DISTANCE
```

`input-text` enters text only. Never send, submit, post, or confirm unless the user explicitly asks.

scrcpy:

```text
doctor | view [--serial LIVE_SERIAL] | control [--serial LIVE_SERIAL]
record --output ABSOLUTE_NEW_MP4_OR_MKV [--serial LIVE_SERIAL] | stop
```

Read [scrcpy-policy.md](references/scrcpy-policy.md) before `control`, `record`, or `stop`.

ADB:

```text
doctor | status | connect | disconnect | recover
wireless-doctor | wireless-status
wireless-pair --port PAIRING_PORT --approved
wireless-connect|wireless-disconnect|wireless-recover --port CONNECTION_PORT
legacy-enable-from-wireless --port CONNECTION_PORT --approved
enable --approved | restore-usb --approved
```

Read [wireless-and-fixed-adb.md](references/wireless-and-fixed-adb.md) before pairing, dynamic-port
use, fixed TCP ADB, or transport recovery. Fixed TCP ADB is disabled in a new profile until the user
accepts its LAN-exposure warning.

## Approval boundary

Automatic read-only work includes doctor checks, identity verification, version checks, UI
observation needed for the request, and post-action verification.

The user's current Galaxy-control request authorizes only low-risk actions needed for that request.
It does not authorize sending, payment, deletion, account changes, security/permission changes,
pairing, `adb tcpip`, network changes, reboot, app installation/update, or file modification.

Read [autonomy-policy.md](references/autonomy-policy.md) when approval is uncertain. Never install,
update, activate, repair, or reconcile OpenMinis, and never delete its app data.

## Recovery

Read [manual-recovery.md](references/manual-recovery.md) after a Galaxy reboot or when Tailscale,
OpenMinis, Shizuku, Wireless Debugging, or ADB is unavailable. Diagnose each component separately;
restart or change only the component proven unavailable.
