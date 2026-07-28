# Report schema

Machine-readable reports use schema version `1.0`.

The authoritative JSON Schema is
[`report.schema.json`](report.schema.json). The top-level object contains:

| Field | Meaning |
|---|---|
| `$schema` | Canonical schema location |
| `schema_version` | Report contract version |
| `tool` | Producer name and version |
| `generated_at` | UTC ISO-8601 timestamp |
| `sources` | Human-readable before/after labels |
| `summary` | File counts by status |
| `expectations` | Matches for user-supplied value pairs |
| `warnings` | Source-level warnings |
| `changes` | Ordered file changes |

Each change has `path`, `status`, `format`, `before`, `after`, `summary`, and a
format-specific `details` object with a `kind` discriminator.

Consumers must ignore unknown detail fields and should branch on
`schema_version`, not the SaveDelta package version.
