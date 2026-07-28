# Troubleshooting and repair flow

This is the required failure-repair sequence for both users and contributors.

## 1. Preserve the evidence

Do not overwrite the before/after inputs. Record:

```bash
savedelta --version
python --version
savedelta inspect PATH --format json
```

Remove personal paths or values before sharing output.

## 2. Reduce the failure

Prefer the smallest command that still fails:

```bash
savedelta diff one-before-file one-after-file --format json
```

If the original input is sensitive, recreate the same structure with synthetic
bytes, JSON, SQLite rows, or ZIP members.

## 3. Identify the stage

| Symptom | Likely stage | Action |
|---|---|---|
| Input missing/unreadable | Source loading | Check path and permissions |
| File absent from snapshot | Ignore/symlink rule | Use `--no-default-ignore` or review warnings |
| `unsupported snapshot format` | Snapshot validation | Recreate with the current release |
| Deep analysis skipped | Work limit | Increase `--max-file-bytes` only for trusted content |
| SQLite counts only | Row budget | Increase `--max-sqlite-rows` |
| ZIP metadata only | Member size/encryption | Extract a trusted member yourself and compare it directly |
| Too many binary candidates | Ambiguous encoding | Make a second controlled change and intersect offsets |
| No binary candidates | Compressed/encrypted/checksummed save | Compare decompressed data or use a format-specific parser |
| `refusing to replace unmarked directory` | Unsafe `demo --force` target | Choose an empty path or a prior SaveDelta demo directory |

## 4. Add a regression test

Place the smallest synthetic reproducer in a temporary directory inside a
`unittest` test. Never commit the user's real save.

```bash
PYTHONPATH=src python -m unittest tests.test_binary -v
```

## 5. Fix within the boundary

- Preserve read-only behavior.
- Add a work limit before any new unbounded loop or allocation.
- Prefer analyzer fallback over whole-report failure.
- Keep report output JSON-serializable and HTML-escaped.

## 6. Rerun the full gate

```bash
python scripts/check.py
python -m unittest discover -s tests -v
python scripts/smoke_test.py
python scripts/build_zipapp.py
python dist/savedelta.pyz demo /tmp/savedelta-release-smoke --force
python -m pip wheel . --no-deps -w dist/wheel
```

Do not publish a release until every command succeeds.
