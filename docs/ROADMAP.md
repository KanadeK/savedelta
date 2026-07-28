# Roadmap

The roadmap favors narrow, testable capabilities over a large editor UI.

## v0.2 — Better binary correlation

- content-defined chunk alignment for insertions and moved blocks;
- intersection of candidates across three or more controlled snapshots;
- UTF-16 and fixed-width string field correlation;
- optional ImHex bookmark export;
- deterministic benchmark corpus.

Acceptance: a shifted synthetic structure is aligned without hiding changed
payload bytes, and peak work remains bounded.

## v0.3 — Parser plug-ins

- documented entry-point interface;
- isolated parser discovery;
- community templates for open save formats;
- per-parser fixtures, limits, and compatibility metadata.

Acceptance: third-party parsers can add analysis without importing private
internals or executing during ordinary snapshot creation.

## v0.4 — Capture adapters

- optional Windows Registry capture;
- explicit application-data presets;
- process-open-file hinting where the OS safely exposes it;
- reproducible snapshot mode.

Acceptance: every adapter remains opt-in and records exactly what was captured.

## v0.5 — Verified patch export

- generate a patch only from a reviewed candidate;
- input SHA-256 precondition;
- automatic backup;
- write-to-new-file default;
- post-write byte and parser verification.

Acceptance: no in-place write can occur without explicit intent and a valid
precondition hash.

## Not planned

- cloud upload or hosted save storage;
- bypassing encryption, DRM, or anti-cheat;
- bundling proprietary parsers or copyrighted fixtures;
- making unverifiable claims about unknown fields.
