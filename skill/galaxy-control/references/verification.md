# Verification

Verification answers “did the requested state actually change?”, not “did a command run?”

Every reviewed adapter returns `result.route` with the controller, transport, action role, whether
fresh verification is required, and fixed verification candidates. This metadata describes the
path actually used; it does not itself prove that the action succeeded.

## Evidence strength

1. Destination state from a different path: strongest.
2. Fresh destination state from the same path: acceptable when no independent path exists.
3. Action response, window creation, or input delivery: execution evidence only.

## Loop

1. Capture a minimal precondition immediately before the action.
2. Perform exactly one minimum action.
3. Read the destination state after the action.
4. Compare the user-visible or system fact that defines success.
5. Restore state if the task was a test.
6. Proceed only after proof.

For messages, forms, purchases, deletions, account changes, permissions, or security settings, ask
for explicit target and effect before acting. “Type this” never means “send this.”

If personal content appears, report only the task-relevant state. Do not reproduce messages,
notifications, account names, tokens, or screenshots.

## One UI multi-app evidence

Treat quantity and identity as separate claims:

- `N개 선택됨` proves only the number of selected rows.
- Before each selection, identify the exact fully visible result row.
- Record the item ID, visible name, target folder, and any required package or component evidence in
  the selection ledger.
- After selection, confirm that the selected count increased by exactly one.
- Before `Done`, require both `ledger rows = manifest items` and `ledger rows = selected count`.

Coordinates alone do not distinguish duplicate visible names. If only one of two same-name apps
belongs in the target, obtain package or component evidence before selecting it. If both belong in
the same target, two separately recorded rows may be sufficient.

A move is complete only when all three are freshly proven:

1. The destination contains the intended item.
2. The source no longer contains it.
3. The destination count matches the expected count.

Write the item-level progress record immediately after proof. This prevents a resumed task from
repeating a completed move. When a commit-like action such as `Done` may already have executed, do
not press it again; change only the observation path until the result is known.
