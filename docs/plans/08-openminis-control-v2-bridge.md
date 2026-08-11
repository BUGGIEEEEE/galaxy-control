# Phase 8 — Portable OpenMinis Control v2 bridge

## Goal

Remove the assumption that every OpenMinis installation already exposes Control v2 on port `43129`.
Ship reviewed generic bridge source and let each user's Mac generate a private, content-addressed
installer from live enrolled identities without adding arbitrary network or shell inputs.

## Inputs

The builder derives all three values. The user does not type them into source code or CLI options.

1. Galaxy Tailscale IPv4 from the existing private enrolled `DeviceProfile`.
2. Mac Tailscale IPv4 from one exact successful `tailscale ip -4` result.
3. Control v2 port from the profile, normally `43129`.

Phone and Mac addresses must be distinct literals inside `100.64.0.0/10`. The port must be
`1..65535`. Missing, multiple, non-tailnet, identical, or malformed identities stop package creation.

## Build tasks

1. Keep the public runtime in `skill/galaxy-control/assets/openminis-control-v2/` with placeholders,
   fixed actions, bounded input/output, and no personal values.
2. Build a deterministic tar manifest from an exact reviewed file allowlist.
3. Embed that runtime and verified identities into one generated installer.
4. Name the installer by its complete SHA-256.
5. Write a new `0700` handoff directory and `0600` files without overwriting a target.
6. Generate `INSTALL.md`, `LIFECYCLE.md`, and `SHA256SUMS` alongside the artifact.
7. Accept only `doctor` and approved `build --output ABSOLUTE_NEW_DIRECTORY` profiles.

## Galaxy installation contract

The generated installer is attached only to the target Galaxy's Minis task. The generated
sealed-memory instruction validates regular-file identity, owner, link count, byte length, SHA-256,
Linux runtime, install mode, and approval binding before executing in memory.

The installer creates only the reviewed runtime and private state under:

```text
~/.local/share/openminis-bridge-control/
~/.openminis-bridge-control/
```

It generates the bridge token locally and does not print it. Existing install or state directories
cause a fail-closed stop. Lifecycle commands are limited to `status`, conditional `start`, and
identity-checked `stop`.

## Security gates

- no arbitrary host, IP, port, serial, executable, argv, or shell input
- no generic Shizuku `exec` endpoint
- fixed request-to-argv mapping only
- every subprocess explicitly uses `shell=False`
- bridge binds only the enrolled Galaxy Tailscale address
- direct requests are accepted only from the enrolled Mac Tailscale address; local requests need the
  private bearer value
- config, PID, command line, start identity, and exact executable are checked before stopping
- personal installer artifact is never committed or published as a GitHub release asset
- public current files and Git history pass the privacy scan before release

## Verification gates

1. Deterministic artifact and complete SHA-256 test.
2. Embedded archive and manifest in-memory verification.
3. Runtime config canonicalization and digest pinning test.
4. HTTP source authorization and fixed-request parsing tests.
5. Python 3.11 public project tests plus Python 3.12 bridge type target.
6. Ruff, BasedPyright, compile, privacy, skill-format, and Git diff checks.
7. Clean installed-skill package generation test.
8. A second user's real Minis installation, bridge lifecycle, Mac `health`, Accessibility, harmless
   action, and independent verification pilot.

Automated gates permit `PACKAGE_READY`. Only step 8 permits `PILOT_E2E_VERIFIED`; GitHub publication
alone does not.

## Rollback

The published `v0.1.3` tag remains immutable. Release this change as a new version. The user's private
skill is never changed. A generated artifact never overwrites an existing Galaxy bridge; any partial
install is inspected and removed only with an exact approved recovery plan.
