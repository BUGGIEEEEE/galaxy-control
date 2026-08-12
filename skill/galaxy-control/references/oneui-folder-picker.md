# Samsung One UI folder picker

The One UI folder picker is a partial view. Apps already inside the folder being edited may be
omitted, so one picker must never be reported as the complete installed-app inventory.

## Read-only inventory method

1. In one unchanged capture session, collect saved `ui-dump` windows from at least two different
   folder pickers whose omissions differ.
2. Record only fully visible result rows. Exclude the search field, selected-count label, buttons,
   keyboard, clipped rows, and overlays.
3. Scroll with overlap and require at least one exact overlapping row between consecutive windows.
4. Replay each saved JSONL with `oneui_inventory.py replay`.
5. Build the same-session maximum-occurrence union with `oneui_inventory.py union`.
6. If the sessions differ, windows do not overlap, or a saved dump contains a selected state, stop
   instead of filling the gap by inference.

`--capture-session` is an operator-supplied provenance label. Create it once at capture start from
the freshly observed boot session plus a new capture-batch identifier, preserve that evidence beside
the JSONL, and never reuse it. The checker proves that supplied labels agree; it cannot prove by
itself that two dumps were physically captured at the same time.

The maximum-occurrence rule preserves duplicate visible names while accounting for items omitted by
one source folder. It does not prove package identity. Use a reviewed package or component query when
one of several same-name apps must be distinguished.

Each line of the replay JSONL is one object with this fixed shape. `ui_dump` is the unmodified JSON
envelope returned by the reviewed OpenMinis `ui-dump` command; `labels` is optional and, when present,
must exactly match the rows reconstructed from that dump.

```json
{"step": 0, "labels": ["Example A", "Example B"], "ui_dump": {"ok": true, "result": {"data": {"nodes": []}}}}
```

The example uses an empty node list only to show the outer schema; it is not a valid picker window.
The checker accepts only a successful stable picker containing the expected header, search control,
completion control, and at least one complete app row.

Search results require a fresh exact-row check. Spaces may behave like tokenized search and produce
unrelated matches. Wait for the accessibility tree to settle, dismiss or account for the keyboard,
and never select a partially visible row by remembered coordinates.

## Selection ledger

For each target folder, select one manifest item at a time and immediately append its item ID,
visible name, target folder, and identity evidence to the ledger. Confirm that the selected count
increased by exactly one. Before pressing `Done` once, require:

- the selection ledger exactly equals the target manifest;
- the ledger row count equals `N개 선택됨`;
- duplicate labels have sufficient identity evidence; and
- no prior `Done` result is unresolved.

After the move, verify destination presence, source absence, and expected count, then write the
progress row immediately. Use `oneui_ledger.py check` to verify manifest, selection ledger, selected
count, and progress evidence. The checker is local and read-only; it never clicks a row or `Done`.

Here, read-only means device-read-only. Inventory `replay` and `union` create only the explicitly
named new Mac output directory. The ledger `check` profile does not write output files.

The three TSV files use these exact tab-separated headers:

```text
manifest.tsv: item_id  app_name  target_folder  identity_evidence
selection-ledger.tsv: selection_index  item_id  app_name  target_folder  identity_evidence
progress.tsv: item_id  app_name  target_folder  status  destination_present  source_absent  expected_count_ok
```

`status` is `completed`, `pending`, or `held`; proof flags are lowercase `true` or `false`.

`--selected-count` must come from a fresh saved picker observation. The progress proof flags must
come from preserved destination, source, and count observations. The checker validates their
internal agreement; it does not reread the Galaxy or authenticate those external observations.
Therefore checker success alone is not proof that an app move occurred.
