# Phase 1 — Baseline and repository

## Goal

Create a clean-room Git repository without copying the private skill's Git history or runtime data.

## Tasks

1. Record the private source commit, working-tree state, test result, and protected hashes.
2. Create the distribution repository outside `<PRIVATE_SKILL_PATH>`.
3. Add ignores for profiles, runtime state, logs, recordings, caches, and Python artifacts.
4. Add this master plan and every detailed phase plan before implementation.
5. Create a private GitHub repository and push the planning checkpoint.

## Verification

- `git -C <PRIVATE_SKILL_PATH> status --porcelain` is empty.
- Protected hashes equal the values in `docs/MASTER_PLAN.md`.
- The new repository has no remote history from the private skill.
- GitHub visibility is private until sanitization and automated gates pass.

## Rollback

Delete only this new distribution repository or revert its planning commit. Never alter the source
skill.
