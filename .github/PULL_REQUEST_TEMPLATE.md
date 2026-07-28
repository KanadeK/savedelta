## What changed

Describe the user-visible outcome and why it belongs in SaveDelta.

## Validation

- [ ] `python scripts/check.py`
- [ ] `python -m unittest discover -s tests -v`
- [ ] `python scripts/smoke_test.py`
- [ ] New behavior has a synthetic regression test.
- [ ] Analyzers remain read-only and bounded.
- [ ] No real save files, secrets, or personal paths are included.
