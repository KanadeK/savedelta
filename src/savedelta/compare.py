from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from . import __version__
from .binary import analyze_binary
from .detect import detect_format
from .errors import AnalysisError, WorkLimitError
from .models import DeltaReport, FileChange, FileEntry, SourceView
from .sqlitediff import analyze_sqlite
from .structured import analyze_structured
from .textdiff import analyze_text
from .util import utc_now
from .zipdiff import analyze_zip


@dataclass(slots=True)
class CompareOptions:
    expectations: tuple[tuple[int | float, int | float], ...] = ()
    max_file_bytes: int = 64 * 1024 * 1024
    max_changes_per_file: int = 300
    max_binary_spans: int = 200
    max_sqlite_rows: int = 5_000
    detect_renames: bool = True


def _summary_for(kind: str, details: dict[str, Any]) -> str:
    if kind in {"json", "toml", "ini"}:
        count = details.get("change_count", 0)
        return f"{count} structured value change{'s' if count != 1 else ''}"
    if kind == "text":
        added = details.get("added_lines", 0)
        removed = details.get("removed_lines", 0)
        return f"{added} line(s) added, {removed} removed"
    if kind == "sqlite":
        schema = details.get("schema_change_count", 0)
        tables = details.get("table_change_count", 0)
        return f"{tables} table(s), {schema} schema object(s) changed"
    if kind == "zip":
        count = details.get("change_count", 0)
        return f"{count} archive member(s) changed"
    if kind == "binary":
        different = details.get("different_bytes", 0)
        delta = details.get("size_delta", 0)
        suffix = f", size {delta:+d} B" if delta else ""
        return f"{different} byte position(s) changed{suffix}"
    return "content changed"


def _analyze_pair(
    path: str,
    before: FileEntry,
    after: FileEntry,
    options: CompareOptions,
) -> FileChange:
    base = FileChange(
        path=path,
        status="modified",
        format="unknown",
        before_size=before.size,
        after_size=after.size,
        before_sha256=before.sha256,
        after_sha256=after.sha256,
    )
    if max(before.size, after.size) > options.max_file_bytes:
        base.format = "metadata"
        base.summary = "content changed; deep analysis skipped by size limit"
        base.details = {
            "kind": "metadata",
            "analysis_limit": options.max_file_bytes,
        }
        base.warnings.append(
            "deep analysis skipped because the file exceeds --max-file-bytes"
        )
        return base

    try:
        before_data = before.read_bytes(options.max_file_bytes)
        after_data = after.read_bytes(options.max_file_bytes)
    except WorkLimitError as exc:
        base.format = "metadata"
        base.summary = "content changed; deep analysis skipped"
        base.details = {"kind": "metadata"}
        base.warnings.append(str(exc))
        return base

    kind = detect_format(path, before_data, after_data)
    base.format = kind
    try:
        if kind in {"json", "toml", "ini"}:
            details = analyze_structured(
                before_data,
                after_data,
                kind,
                expectations=options.expectations,
                max_changes=options.max_changes_per_file,
            )
        elif kind == "text":
            details = analyze_text(
                before_data,
                after_data,
                path=path,
                max_diff_lines=options.max_changes_per_file * 2,
            )
        elif kind == "sqlite":
            details = analyze_sqlite(
                before_data,
                after_data,
                max_rows_per_table=options.max_sqlite_rows,
                max_row_changes=options.max_changes_per_file,
            )
        elif kind == "zip":
            details = analyze_zip(
                before_data,
                after_data,
                expectations=options.expectations,
            )
        else:
            details = analyze_binary(
                before_data,
                after_data,
                expectations=options.expectations,
                max_spans=options.max_binary_spans,
            )
    except (AnalysisError, WorkLimitError, ValueError, OSError) as exc:
        base.warnings.append(
            f"{kind} analyzer could not complete ({exc}); used binary fallback"
        )
        base.format = "binary"
        details = analyze_binary(
            before_data,
            after_data,
            expectations=options.expectations,
            max_spans=options.max_binary_spans,
        )

    base.details = details
    base.summary = _summary_for(base.format, details)
    return base


def _rename_pairs(
    removed: dict[str, FileEntry],
    added: dict[str, FileEntry],
) -> list[tuple[str, str]]:
    removed_by_hash: dict[str, list[str]] = {}
    added_by_hash: dict[str, list[str]] = {}
    for path, entry in removed.items():
        removed_by_hash.setdefault(entry.sha256, []).append(path)
    for path, entry in added.items():
        added_by_hash.setdefault(entry.sha256, []).append(path)

    pairs: list[tuple[str, str]] = []
    for digest in sorted(set(removed_by_hash) & set(added_by_hash)):
        old_paths = sorted(removed_by_hash[digest])
        new_paths = sorted(added_by_hash[digest])
        for old_path, new_path in zip(old_paths, new_paths):
            pairs.append((old_path, new_path))
    return pairs


def _collect_hits(
    details: dict[str, Any],
    *,
    file_path: str,
    output: list[dict[str, Any]],
) -> None:
    kind = details.get("kind")
    if kind in {"json", "toml", "ini"}:
        for match in details.get("expectation_matches", []):
            output.append({"file": file_path, **match})
        return
    if kind == "binary":
        for group in details.get("expectation_matches", []):
            for candidate in group.get("candidates", []):
                output.append({"file": file_path, **candidate})
        return
    if kind == "zip":
        for member in details.get("changes", []):
            nested = member.get("analysis")
            if isinstance(nested, dict):
                _collect_hits(
                    nested,
                    file_path=f"{file_path}!/{member.get('path', '?')}",
                    output=output,
                )


def _expectation_summary(
    changes: Iterable[FileChange],
    expectations: Iterable[tuple[int | float, int | float]],
) -> list[dict[str, Any]]:
    all_hits: list[dict[str, Any]] = []
    for change in changes:
        _collect_hits(change.details, file_path=change.path, output=all_hits)

    result: list[dict[str, Any]] = []
    for old, new in expectations:
        matches = [
            hit
            for hit in all_hits
            if hit.get("from") == old and hit.get("to") == new
        ]
        matches.sort(
            key=lambda item: (
                -float(item.get("confidence", 0.0)),
                item.get("file", ""),
                int(item.get("offset", 0)),
            )
        )
        result.append(
            {
                "from": old,
                "to": new,
                "match_count": len(matches),
                "matches": matches[:100],
                "truncated": len(matches) > 100,
            }
        )
    return result


def compare_views(
    before_view: SourceView,
    after_view: SourceView,
    *,
    options: CompareOptions | None = None,
) -> DeltaReport:
    opts = options or CompareOptions()
    changes: list[FileChange] = []
    unchanged = 0

    if before_view.single_file and after_view.single_file:
        before_entry = next(iter(before_view.entries.values()))
        after_entry = next(iter(after_view.entries.values()))
        if before_entry.sha256 == after_entry.sha256:
            unchanged = 1
        else:
            display_path = (
                after_entry.path
                if before_entry.path == after_entry.path
                else f"{before_entry.path} → {after_entry.path}"
            )
            changes.append(
                _analyze_pair(display_path, before_entry, after_entry, opts)
            )
    else:
        before_paths = set(before_view.entries)
        after_paths = set(after_view.entries)
        for path in sorted(before_paths & after_paths):
            before_entry = before_view.entries[path]
            after_entry = after_view.entries[path]
            if before_entry.sha256 == after_entry.sha256:
                unchanged += 1
                continue
            changes.append(_analyze_pair(path, before_entry, after_entry, opts))

        removed = {
            path: before_view.entries[path] for path in before_paths - after_paths
        }
        added = {path: after_view.entries[path] for path in after_paths - before_paths}
        if opts.detect_renames:
            for old_path, new_path in _rename_pairs(removed, added):
                old_entry = removed.pop(old_path)
                new_entry = added.pop(new_path)
                changes.append(
                    FileChange(
                        path=new_path,
                        previous_path=old_path,
                        status="renamed",
                        format="file",
                        before_size=old_entry.size,
                        after_size=new_entry.size,
                        before_sha256=old_entry.sha256,
                        after_sha256=new_entry.sha256,
                        summary=f"renamed from {old_path}",
                        details={"kind": "rename", "from": old_path, "to": new_path},
                    )
                )

        for path, entry in removed.items():
            changes.append(
                FileChange(
                    path=path,
                    status="removed",
                    format="file",
                    before_size=entry.size,
                    before_sha256=entry.sha256,
                    summary="file removed",
                    details={"kind": "file"},
                )
            )
        for path, entry in added.items():
            changes.append(
                FileChange(
                    path=path,
                    status="added",
                    format="file",
                    after_size=entry.size,
                    after_sha256=entry.sha256,
                    summary="file added",
                    details={"kind": "file"},
                )
            )

    order = {"modified": 0, "renamed": 1, "added": 2, "removed": 3}
    changes.sort(key=lambda change: (order.get(change.status, 9), change.path))
    counts = {
        "files_before": len(before_view.entries),
        "files_after": len(after_view.entries),
        "changed": len(changes),
        "modified": sum(item.status == "modified" for item in changes),
        "added": sum(item.status == "added" for item in changes),
        "removed": sum(item.status == "removed" for item in changes),
        "renamed": sum(item.status == "renamed" for item in changes),
        "unchanged": unchanged,
    }
    warnings = [
        *(f"before: {warning}" for warning in before_view.warnings),
        *(f"after: {warning}" for warning in after_view.warnings),
    ]
    return DeltaReport(
        schema_version="1.0",
        tool_version=__version__,
        generated_at=utc_now(),
        before=before_view.label,
        after=after_view.label,
        summary=counts,
        changes=changes,
        expectations=_expectation_summary(changes, opts.expectations),
        warnings=warnings,
    )
