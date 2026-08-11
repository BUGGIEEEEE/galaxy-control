# OpenMinis Control v2 bridge distribution

Read this file when `health`, `a11y-status`, or `shizuku-status` on port `43129` returns
`network_error`, or when enrolling a new user whose Galaxy has only the regular OpenMinis app.

If an older `galaxy-control` skill is already installed, do not overwrite it merely to build the
bridge. A pinned `v0.2.1` repository checkout may run its own
`skill/galaxy-control/scripts/galaxy_bridge_package.py` directly. It reads the same private
Application Support profile and changes only the explicitly approved new output directory.

## What is public and what is private

The public skill contains reviewed generic bridge source under `assets/openminis-control-v2/`. It has
no user's IP, token, serial, pairing code, or ADB key. Never edit those assets with per-user values.

The Mac-side builder creates one private installer using exactly three values:

| Value | Verified source | Private destination |
| --- | --- | --- |
| Galaxy Tailscale IPv4 | enrolled `device.json` | generated installer, then Galaxy `bridge.json` |
| trusted Mac Tailscale IPv4 | exact `tailscale ip -4` result | generated installer, then Galaxy `bridge.json` |
| Control v2 port | enrolled `openminis_port`, normally `43129` | generated installer, then Galaxy `bridge.json` |

The builder accepts none of these as command-line input. If the values are wrong, repair enrollment or
Tailscale first; do not override the builder.

## Mac preparation

Run read-only diagnosis:

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_bridge_package.py" doctor
```

`READY` means the profile, distinct Tailscale peers, and public bridge assets are internally valid.
It does not prove that the Galaxy accepted installation or that port `43129` is reachable.

With approval, build into one absolute path that does not exist:

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_bridge_package.py" \
  build --output "$HOME/Desktop/openminis-control-v2-handoff" --approved
```

The directory and its files are private. Do not commit, upload, or paste the generated Python file.
Share it only as an attachment to the target Galaxy's Minis conversation.

## Galaxy installation through Minis

1. Attach the generated `openminis-control-v2-<SHA256>.py` to Minis.
2. Copy the exact command from the generated `INSTALL.md` into the same Minis task.
3. Ask Minis to execute it once and return only its JSON envelope.
4. If it fails, do not retry or invent a command. Report the error code to Codex.
5. On `INSTALLED_RUNNING`, use the generated `LIFECYCLE.md` `status` command.
6. Run `start` once only when `status` explicitly reports that the bridge is not running.
7. Run `status` again after `start`.

The installer creates only these private Galaxy locations:

```text
~/.local/share/openminis-bridge-control/
~/.openminis-bridge-control/
```

It does not install or update the OpenMinis APK, alter app data, enable Shizuku, change Accessibility,
modify Tailscale, or expose a generic shell endpoint. A new token is generated on the Galaxy and is
never returned.

## Independent Mac verification

After the Galaxy reports a running bridge, verify from the Mac:

```sh
"$GALAXY_SKILL_ROOT/scripts/galaxy_control.sh" health
"$GALAXY_SKILL_ROOT/scripts/galaxy_control.sh" a11y-status
"$GALAXY_SKILL_ROOT/scripts/galaxy_control.sh" shizuku-status
"$GALAXY_SKILL_ROOT/scripts/galaxy_control.sh" ui-info
```

Interpret the results separately:

- `health` success proves only HTTP bridge reachability.
- `a11y-status` proves whether semantic UI observation/control is available.
- `shizuku-status` proves whether reviewed system queries are available.
- fresh `ui-info` proves the current foreground semantic state without proving scrcpy.

Complete one harmless observe → act → independently verify pilot before claiming end-to-end control.

## Stop and rollback

Use only the exact `stop` command in `LIFECYCLE.md`. It verifies process identity before signalling.
Do not use `killall`, `pkill`, or a guessed PID.

The generated package never overwrites an existing install or state directory. If installation stops
after creating a partial directory, do not delete or retry automatically. Inspect the reported error
and obtain approval for an exact cleanup or recovery plan. Never delete the OpenMinis app or its data.
