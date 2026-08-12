# Task routing

Use the smallest path that directly matches the request.

Classify the task before probing the phone, then run only the matching fixed preflight:

```sh
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" openminis
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" adb
uv run "$GALAXY_SKILL_ROOT/scripts/galaxy_doctor.py" scrcpy
```

The `scrcpy` target includes its ADB dependency. Use the no-argument or `all` target only for a new
control session, after reboot/network changes or bridge/ADB errors, or for work that truly crosses
all path categories. Reuse a successful result only in the current agent session and invalidate it
on any event listed in `result.reuse.invalidate_on`.

| Path | Recognizes output as | Sends input as | Best use | Main weakness |
| --- | --- | --- | --- | --- |
| OpenMinis | Accessibility nodes, text, roles, bounds, state | Fixed semantic taps, text, keys, scroll | Repeatable meaning-based UI work | May miss animation, canvas, video, or custom views |
| scrcpy | Live pixels rendered in a managed Mac window | Computer Use mouse/keyboard gestures | Motion, drag, rotation, complex gestures | Pixel success is ambiguous without independent proof |
| ADB/Shizuku | Fixed system/property/process results | Only reviewed fixed profiles | Device identity, transport, package/system facts | Broad shell access would be dangerous and is forbidden |

Default order:

1. Observe meaning through OpenMinis.
2. Use OpenMinis for repeatable semantic input.
3. Use scrcpy only where live pixels or gestures add value.
4. Use reviewed ADB/Shizuku for system facts, not ordinary UI guessing.
5. Verify with the strongest independent route available.

Fallback is allowed only after confirmed non-execution. When execution is uncertain, keep the phone
still and add observations instead of repeating the action.
