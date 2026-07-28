# Release checklist

## Identity

- Repository owner is `KanadeK`.
- Commit author and committer resolve to the `KanadeK` GitHub account.
- No automated-tool identity is listed as an author, committer, or contributor.

## Validation

```bash
python scripts/check.py
python -m unittest discover -s tests -v
python scripts/smoke_test.py
python scripts/build_zipapp.py
python dist/savedelta.pyz --version
python -m pip wheel . --no-deps -w dist/wheel
git diff --check
```

## Release

- Version matches `pyproject.toml`, `src/savedelta/__init__.py`, and changelog.
- `vX.Y.Z` points at the same commit as the intended release.
- Release notes state real capabilities and known limits.
- `savedelta.pyz`, wheel, source archive, and SHA-256 checksums are attached.
- CI passes on all supported Python versions.
- Repository description, topics, license, and README are visible.
- A fresh download passes `python savedelta.pyz demo`.
