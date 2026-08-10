# Phase 3 — Portable control adapters

## Goal

Preserve the proven OpenMinis, Wireless Debugging, fixed TCP ADB, and scrcpy safety contracts while
loading the enrolled user's identity at runtime.

## Tasks

1. Bundle a reviewed OpenMinis Mac client with only the fixed command set. Trust only loopback or
   the profile's literal Tailscale IPv4. Read an optional compatibility token only from the process
   environment and never print it.
2. Replace the private absolute wrapper with a location-independent launcher derived from the
   installed skill directory.
3. Make ADB profiles consume the immutable parsed profile. Do not accept host, model, physical
   serial, final TCP port, ADB option, or shell input on operational commands.
4. Keep pairing and dynamic connection ports separate, decimal, and in `1..65535`. Read a six-digit
   pairing code from stdin only and never retry automatically.
5. Keep fixed TCP ADB `5555` optional, explicitly approved, boot-scoped, and accurately described as
   potentially LAN-reachable.
6. Make scrcpy select only a profile-matching device, use fixed view/control/record options, and
   stop only a saved process whose full identity matches.
7. Move runtime bundles, process state, stderr, and wireless boot state to private user cache
   directories outside the installed skill and Git working tree.

## Tests

- Every current private-skill safety behavior expressed against two different fake profiles
- No arbitrary host, serial, model, port, ADB option, scrcpy option, or shell execution
- `shell=False` for every subprocess
- Pairing code absent from argv, environment, files, JSON, and logs
- Device model normalization without silently accepting a different live identity
- Previous boot/port cache rejection and exact endpoint retirement
- Owned scrcpy stop and unmanaged-process rejection
- OpenMinis response and command-envelope validation

## Exit gate

The adapters pass the full automated suite with no Buggie-specific identifier or absolute private
path in tracked files or Git history.
