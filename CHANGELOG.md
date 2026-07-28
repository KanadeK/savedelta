# Changelog

All notable changes to SaveDelta are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project follows [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-07-28

### Added

- Portable `.sdelta` snapshots with ordered manifests, digest verification, and embedded data.
- Directory, file, and snapshot comparison with add/remove/rename detection.
- Structural JSON, TOML, and INI diffs.
- Read-only SQLite schema, table, and row comparison.
- Safe ZIP member comparison without extraction.
- Binary changed-range analysis, entropy metrics, and numeric field location.
- Self-contained HTML, JSON, and terminal reports.
- One-command synthetic game-save demo.
- Zero runtime dependencies, test suite, CI, release workflow, and zipapp build.

[0.1.0]: https://github.com/KanadeK/savedelta/releases/tag/v0.1.0
