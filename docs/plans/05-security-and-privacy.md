# Phase 5 — Security and privacy verification

## Goal

Prove that public distribution reveals no private identifiers or credentials and exposes no generic
execution surface.

## Tasks

1. Search tracked files and Git objects for the private username, home paths, device serial, model,
   Tailscale IP, observed dynamic ports, tokens, pairing codes, logs, screenshots, and recordings.
2. Review subprocess call sites for literal argv arrays, bounded output, timeouts, and `shell=False`.
3. Review setup mutation paths against the exact installer and ADB allowlists.
4. Verify profile/cache file type, ownership assumptions, size limits, and permissions.
5. Verify stable JSON envelopes and stderr separation.
6. Document fixed TCP ADB wildcard/LAN exposure, ADB RSA limits, Tailscale ACL scope, and the safer
   official Wireless Debugging default.
7. Add GitHub Actions for tests, type checking, lint/format, skill validation, and privacy scans.

## Exit gate

All security tests and repository/history scans pass. No public tracked artifact contains a private
user or device identifier, secret, personal screen content, or a broad command facility.
