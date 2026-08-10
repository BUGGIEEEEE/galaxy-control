# scrcpy policy

`galaxy_screen.py` accepts fixed profiles only.

- `view`: exact serial, `--no-control`, `--no-audio`, and no clipboard autosync. It is the default
  read-only live view.
- `control`: exact serial, no audio, and no clipboard autosync. Use only for a requested live
  interaction.
- `record`: explicit new absolute `.mp4` or `.mkv`, no control, no audio, and no playback. Existing
  files are never overwritten. `stop` verifies the file is regular, nonempty, and has a matching
  container signature.
- `stop`: checks saved PID, start identity, executable, full argv, serial, model, session marker,
  and exact process command before signaling. Never use `killall` or `pkill`.

The adapter may wrap the installed scrcpy executable in a private local `.app` bundle so macOS
Computer Use can identify it consistently. This changes only the user's private Galaxy Control
cache, not the installed scrcpy binary.

Starting scrcpy or delivering input is never result proof. Verify the requested phone state through
OpenMinis or a fixed ADB fact whenever possible.
