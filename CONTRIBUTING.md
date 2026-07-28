# Contributing

Thanks for helping make SaveDelta more useful.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e .
python -m unittest discover -s tests -v
python scripts/check.py
```

## Pull requests

- Keep input handling read-only unless a feature explicitly creates an output.
- Add tests for every parser, format detector, or security boundary you change.
- Never include proprietary save files, personal data, or copyrighted game data.
- Use synthetic fixtures that can be regenerated from source.
- Update `CHANGELOG.md` for user-visible changes.

Commit messages should be short and use a conventional prefix such as
`feat:`, `fix:`, `docs:`, `test:`, or `ci:`.

## Adding a format

1. Add a conservative detector. Magic bytes beat filename extensions.
2. Set strict work limits before parsing attacker-controlled content.
3. Return JSON-serializable details through the existing report model.
4. Fall back to the binary analyzer instead of aborting the whole comparison.
5. Add malformed-input and size-limit tests.
