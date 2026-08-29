# Samsung One UI launcher

Read this before app-drawer or folder-reorganization work. Treat every launcher state as live,
version-dependent evidence rather than a permanent coordinate map.

## Page and overlay guards

- `HOME` may return to the last remembered app-drawer page, not the first page.
- The existence of page dots does not prove which page is active. Confirm the active page from the
  current UI and visible anchors.
- A single-page drawer still needs a fresh page guard. Do not assume the same guard works across all
  One UI versions until tested.
- Exclude Edge panels, pop-ups, keyboards, and other overlays from drawer item counts.
- After a home-to-drawer gesture, prove the destination from a fresh UI observation. If the
  notification shade opens instead, return HOME, re-observe, and try the opposite direction at most
  once. Never repeat an unverified gesture or infer a hidden target from neighboring coordinates.
- After any bulk move, refresh the UI dump. Page count, app positions, folder positions, and visible
  anchors may all change.

Never drag a folder object when the task is to move apps inside folders. A launcher may interpret it
as moving the folder to another surface. Use the reviewed folder picker for app membership changes.

## Folder mutation behavior

A source folder may disappear automatically when emptied. Remaining items may also be released into
the app drawer when membership changes. Therefore, post-action verification must check the target,
the source, and the expected count rather than relying on the old folder coordinate.

Built-in sorting is only a candidate investigation path. Before using it, prove its scope, ordering,
and affected surface, then obtain approval for the actual change. Do not claim a verified alphabetic
order or a verified usage-frequency order from documentation alone.

Keep session-specific app counts, page numbers, coordinates, node IDs, scroll distances, folder
names, and app classifications in the task artifacts—not in this reusable skill.
