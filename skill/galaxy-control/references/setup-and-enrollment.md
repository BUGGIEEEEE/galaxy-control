# Setup and enrollment

Use this guide for first installation, a missing prerequisite, or a new Galaxy.

## Supported setup

- macOS and Codex desktop
- one Samsung Galaxy with OpenMinis installed; this distribution can package its compatible Control
  v2 local bridge separately after enrollment
- Tailscale signed into the intended tailnet on both devices
- Android Developer options and official Wireless Debugging when remote scrcpy is required

The setup adapter may install missing ADB, scrcpy, and `uv` through an existing Homebrew only after
the user reviews the exact plan and approves it. It never upgrades present tools. Tailscale is a
user-mediated install/login because macOS must approve its VPN/system extension. Do not install both
Mac App Store and standalone variants.

If `uv` is not installed yet, run the repository's standard-library bootstrap before using this
installed skill:

```sh
python3 scripts/bootstrap.py doctor
python3 scripts/bootstrap.py apply --approved
```

It installs only missing `uv` through an existing Homebrew. If Homebrew is also missing, it stops
for a user-managed installation instead of downloading or executing a remote installer.

## Safe sequence

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_setup.py" doctor
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_setup.py" plan
```

Explain every listed installer and user action. If accepted:

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_setup.py" apply --approved
```

Then ask the user to connect and unlock exactly one Galaxy, approve its ADB RSA prompt, and ensure
Tailscale is online. Enroll from live identity reads:

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_setup.py" enroll --approved
```

If more than one ADB device is present, show the live list without unrelated metadata and require an
exact choice:

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_setup.py" enroll --serial LIVE_SERIAL --approved
```

The private profile is stored under the user's macOS Application Support directory with `0700`
directory and `0600` file permissions. It contains the enrolled physical serial, model, literal
Tailscale IPv4 address, OpenMinis port, and fixed-ADB preference. Never commit, paste, or log it.

Finish with:

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_setup.py" verify
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py"
```

`READY` proves local diagnosed paths, not Computer Use permission or a real end-to-end control. A
harmless live screen/input/independent-verification pilot is still required for that claim.

If OpenMinis reports `network_error`, continue with
[openminis-bridge-distribution.md](openminis-bridge-distribution.md). The builder reads the enrolled
Galaxy Tailscale address and port plus the Mac's current Tailscale address. Do not type those values
into public source or accept arbitrary replacements on the command line.
