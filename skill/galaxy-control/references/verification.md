# Verification

Verification answers “did the requested state actually change?”, not “did a command run?”

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
