# Synthetic example data

SaveDelta does not bundle proprietary save files. Generate a complete synthetic
fixture instead:

```bash
savedelta demo example-output
```

The command creates:

```text
example-output/
  before/
    checkpoint.zip
    obsolete.cache
    old_notes.txt
    player.json
    save.dat
    settings.ini
    world.db
  after/
    autosave.flag
    checkpoint.zip
    player.json
    quest_notes.txt
    save.dat
    settings.ini
    world.db
  before.sdelta
  after.sdelta
  report.html
  report.json
```

The binary layout is intentionally simple and documented in `savedelta.demo`.
Gold is stored as a little-endian 32-bit integer at offset `0x24`; the visible
change from 100 to 250 lets the expected-value locator prove the end-to-end
workflow.
