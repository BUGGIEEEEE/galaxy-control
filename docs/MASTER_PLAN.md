# Galaxy Control Distribution Master Plan

## Outcome

Deliver a public, macOS-and-Samsung-Galaxy Codex skill that can diagnose prerequisites, guide or
apply approved setup, enroll exactly one user's Galaxy, connect through reviewed OpenMinis,
official Wireless Debugging, optional fixed TCP ADB, and fixed-profile scrcpy paths, then prove a
real requested result before continuing.

The existing private skill at `<PRIVATE_SKILL_PATH>` is an immutable source
baseline. It must never be edited, installed over, or used as the runtime of this distribution.

## Baseline

- Source commit: `0953916f1b263dc4e795114f31febd667d2ac09b`
- Source tests: `65 passed, 55 subtests passed`
- Protected wrapper SHA-256:
  `4e6c24c87bb80df65934ded31b31ef36e766f6fb3af825503eec4d050625e314`
- Source `SKILL.md` SHA-256:
  `8d0c2e9ead4bda439e301d9b2f71589c0ce8c348d5637ca62657a9bededa4c81`
- Source working tree: clean before distribution work

## Supported first release

- macOS on Apple Silicon or Intel
- Codex desktop with the required Computer Use capability and macOS permissions
- Samsung Galaxy with a compatible, already-installed OpenMinis Control v2 bridge
- Tailscale on both devices
- Android official Wireless Debugging
- ADB and scrcpy installed locally or installed after an explicit setup approval
- Python 3.11 or newer and `uv` for the bundled OpenMinis client

Other operating systems, non-Samsung Android devices, OpenMinis installation/update, unattended
Galaxy reboot recovery, root, and generic remote shell execution are outside version 1.

## Architecture

1. `scripts/bootstrap.py` installs only missing `uv` through an existing Homebrew after approval.
2. `galaxy_setup.py` diagnoses the Mac and enrolls one live Galaxy into a private per-user profile.
3. `galaxy_doctor.py` reports partial availability without changing state.
4. `openminis_client.py` exposes only reviewed OpenMinis actions against the enrolled literal
   Tailscale IPv4 address.
5. `galaxy_remote_adb.py` uses the enrolled identity and fixed profiles for USB, official Wireless
   Debugging, and optional approved TCP ADB `5555`.
6. `galaxy_screen.py` starts only fixed scrcpy profiles and stops only its owned process.
7. `SKILL.md` routes every task through observe, one minimum action, independent verification, and
   only then the next step.

User identity, device serial, model, Tailscale address, tokens, pairing codes, runtime state,
recordings, and screenshots never enter Git.

## Delivery phases

| Phase | Deliverable | Exit gate |
| --- | --- | --- |
| 1 | Protected baseline and clean-room repository | Original hashes and Git state unchanged |
| 2 | Portable profile and onboarding | Private `0600` profile; strict live enrollment |
| 3 | Portable control adapters | No personal constants or arbitrary command surfaces |
| 4 | Skill and user documentation | Valid skill metadata and explicit approval boundaries |
| 5 | Automated verification | Unit, integration-style CLI, static, secret, and regression tests pass |
| 6 | Clean Mac/Galaxy pilot | Another user's real screen, input, verification, and reconnect pass |
| 7 | GitHub release | Public repository, immutable tag, checksums, and install instructions |

Detailed execution files live in `docs/plans/` and are followed in numeric order.

## Approval and automation boundary

- Automatic: read-only diagnostics, version checks, live identity reads, profile validation,
  failure classification, and verification.
- One explicit setup approval: install named Mac prerequisites that are missing, create the private
  local profile, and perform the exact enrollment actions shown in the plan.
- User-mediated: macOS privacy prompts, Tailscale login/VPN approval, Galaxy unlock, Wireless
  Debugging toggle and pairing-code screen, ADB RSA prompt, Accessibility, and Shizuku permission.
- Separate explicit approval: pairing, `adb tcpip 5555`, network/security changes, reboot, or
  consequential Galaxy actions.
- Never: arbitrary host, serial, shell, ADB options, scrcpy options, port scan, pairing-code
  persistence, token output, root, broad process killing, OpenMinis install/update/reconcile.

## Completion verdicts

- `PACKAGE_READY`: plans, code, documentation, and automated tests pass.
- `PILOT_INSTALL_VERIFIED`: a clean second Mac completes installation and enrollment.
- `PILOT_E2E_VERIFIED`: a second user's Galaxy completes real screen, input, independent
  verification, stop, and reconnect.
- `DISTRIBUTION_READY`: security review, public GitHub tag, checksums, and supported-scope E2E all
  pass.
- `BLOCKED`: a required user permission, incompatible OpenMinis version, unreachable tailnet, or
  unsupported environment remains.

Code-only success may not be reported as `PILOT_E2E_VERIFIED` or `DISTRIBUTION_READY`.

## Rollback

- The private source skill remains untouched and is the immediate operational fallback.
- Distribution changes are atomic Git commits and may be reverted by commit.
- User setup writes only its private application-support and cache directories; removal
  instructions must name exact paths and never delete OpenMinis or Galaxy data.
- A fixed TCP ADB transition is reversible only through the reviewed adapter and explicit approval.
