from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


Reader = Callable[[int | None], bytes]


@dataclass(slots=True)
class FileEntry:
    """One logical file from a directory, file, or portable snapshot."""

    path: str
    size: int
    sha256: str
    reader: Reader = field(repr=False)
    native_path: Path | None = field(default=None, repr=False)

    def read_bytes(self, limit: int | None = None) -> bytes:
        return self.reader(limit)


@dataclass(slots=True)
class SourceView:
    label: str
    kind: str
    entries: dict[str, FileEntry]
    warnings: list[str] = field(default_factory=list)
    single_file: bool = False


@dataclass(slots=True)
class FileChange:
    path: str
    status: str
    format: str
    before_size: int | None = None
    after_size: int | None = None
    before_sha256: str | None = None
    after_sha256: str | None = None
    previous_path: str | None = None
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "path": self.path,
            "status": self.status,
            "format": self.format,
            "before": (
                {"size": self.before_size, "sha256": self.before_sha256}
                if self.before_size is not None
                else None
            ),
            "after": (
                {"size": self.after_size, "sha256": self.after_sha256}
                if self.after_size is not None
                else None
            ),
            "summary": self.summary,
            "details": self.details,
        }
        if self.previous_path is not None:
            result["previous_path"] = self.previous_path
        if self.warnings:
            result["warnings"] = self.warnings
        return result


@dataclass(slots=True)
class DeltaReport:
    schema_version: str
    tool_version: str
    generated_at: str
    before: str
    after: str
    summary: dict[str, int]
    changes: list[FileChange]
    expectations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return self.summary.get("changed", 0) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "$schema": (
                "https://raw.githubusercontent.com/KanadeK/savedelta/"
                "main/docs/report.schema.json"
            ),
            "schema_version": self.schema_version,
            "tool": {"name": "savedelta", "version": self.tool_version},
            "generated_at": self.generated_at,
            "sources": {"before": self.before, "after": self.after},
            "summary": self.summary,
            "expectations": self.expectations,
            "warnings": self.warnings,
            "changes": [change.to_dict() for change in self.changes],
        }
