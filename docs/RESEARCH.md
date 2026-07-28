# Research and differentiation

Research date: 2026-07-28.

SaveDelta was selected after excluding the previously explored project catalog
and sampling adjacent open-source tools. The opportunity is not “binary diff
does not exist.” It is that a useful before/after investigation still requires
several disconnected tools and manual correlation.

## Adjacent tools

| Tool | Strong at | Gap SaveDelta targets |
|---|---|---|
| [ImHex](https://github.com/WerWolv/ImHex) | Interactive hex inspection, patterns, data types, entropy, diffing | Requires the operator to know which files and offsets matter |
| [biodiff](https://github.com/8051Enthusiast/biodiff) | Pairwise binary alignment using sequence algorithms | No directory capture, structured formats, SQLite, or portable report |
| [Regshot](https://github.com/Seabreg/Regshot) | Before/after Windows Registry and directory snapshots | Windows/registry centered; not content-aware save analysis |
| [`sqldiff`](https://sqlite.org/sqldiff.html) | SQL transformation between two SQLite databases | SQLite only; no surrounding application-state workflow |
| [`sqlite-diffable`](https://github.com/simonw/sqlite-diffable) | Version-control-friendly SQLite export | Database export rather than controlled cross-format field discovery |

Relevant unmet-demand evidence also appears in requests for stronger binary
comparison in
[VS Code Hex Editor](https://github.com/microsoft/vscode-hexeditor/issues/445)
and
[ImHex](https://github.com/WerWolv/ImHex/issues/2342).

## Product thesis

The memorable interaction is:

> Change one visible value once; receive the exact JSON path, database row, or
> ranked byte offsets that could store it.

That creates a short, demonstrable loop while remaining useful without AI,
accounts, APIs, or a hosted service.

## Technical grounding

- Python packaging uses a declared `pyproject.toml` build system and console
  entry point, following the
  [Python Packaging User Guide](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
  and its
  [CLI packaging guide](https://packaging.python.org/en/latest/guides/creating-command-line-tools/).
- CI uses `setup-python`, which
  [GitHub recommends](https://docs.github.com/actions/guides/building-and-testing-python)
  for consistent hosted-runner behavior.
- SQLite comparison is deliberately complementary to the official
  [`sqldiff` utility](https://sqlite.org/sqldiff.html).
- ZIP handling assumes maintained Python 3.11+ maintenance releases and adds
  explicit entry, expanded-size, and deep-read budgets.

## Differentiation boundary

SaveDelta does not claim to outperform specialized editors at their core job.
Its differentiation is the orchestration and explanation layer:

1. self-contained capture;
2. mixed-format path pairing;
3. safe analyzer dispatch;
4. exact visible-value correlation;
5. one portable report;
6. a parser plug-in path rather than hard-coded proprietary formats.
