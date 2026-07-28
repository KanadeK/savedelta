# Security policy

## Supported versions

Security fixes are provided for the latest released version.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting feature for this
repository. Do not attach real save files, credentials, personal information,
or copyrighted game assets to a public issue.

## Security boundaries

SaveDelta treats every compared file and archive as untrusted:

- it never executes input content;
- SQLite databases are opened through temporary copies in query-only mode;
- ZIP members are inspected in memory and are never extracted;
- archive entry count and expanded-byte budgets are enforced;
- HTML output escapes all input-derived strings and contains no JavaScript;
- symlinks are skipped by default;
- snapshots store data under generated member names, not user-controlled paths.

See [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md) for the detailed model.
