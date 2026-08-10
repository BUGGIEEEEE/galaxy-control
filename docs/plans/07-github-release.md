# Phase 7 — GitHub release

## Goal

Publish an auditable, immutable installation target after package gates pass.

## Tasks

1. Keep the GitHub repository private during implementation and security review.
2. Use atomic commits for plans, profile/onboarding, adapters, skill/docs, and release automation.
3. Push only after each commit's local gates pass.
4. Create a signed or annotated `v0.1.0` tag after all package gates pass.
5. Generate SHA-256 checksums for the release archive and publish release notes that distinguish
   automated verification from real-device pilot verification.
6. Change the repository to public only after tracked-file and full-history privacy scans pass.
7. Document the official installer command with repository and tag pinning.
8. Do not claim OpenAI-curated marketplace publication; GitHub is the supported distribution
   channel for this release.

## Release rollback

- Do not rewrite a published tag. Publish a corrective version or withdraw the release.
- A user may remove only `~/.codex/skills/galaxy-control` and the exact Galaxy Control application
  support/cache directories. OpenMinis, Tailscale, Galaxy data, and ADB keys are not deleted.
- If a release contains private data, immediately make the repository private, revoke the release,
  rotate any affected credential outside this repository, and publish a clean-history replacement.

## Exit gate

The public tag installs successfully, all published checksums match, GitHub Actions pass, and the
release verdict accurately states whether a real second-user E2E pilot has completed.
