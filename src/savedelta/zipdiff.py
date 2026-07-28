from __future__ import annotations

import io
import zipfile
from collections import Counter
from pathlib import PurePosixPath
from typing import Any, Iterable

from .binary import analyze_binary
from .detect import detect_format
from .errors import AnalysisError, WorkLimitError
from .structured import analyze_structured
from .textdiff import analyze_text


def _index(
    data: bytes,
    *,
    max_entries: int,
    max_expanded_bytes: int,
) -> tuple[zipfile.ZipFile, dict[str, zipfile.ZipInfo], list[str]]:
    try:
        bundle = zipfile.ZipFile(io.BytesIO(data), "r")
    except zipfile.BadZipFile as exc:
        raise AnalysisError(f"cannot parse ZIP archive: {exc}") from exc
    infos = bundle.infolist()
    if len(infos) > max_entries:
        bundle.close()
        raise WorkLimitError(
            f"ZIP contains {len(infos)} entries, above the {max_entries} entry limit"
        )
    expanded = sum(info.file_size for info in infos if not info.is_dir())
    if expanded > max_expanded_bytes:
        bundle.close()
        raise WorkLimitError(
            f"ZIP expands to {expanded} bytes, above the "
            f"{max_expanded_bytes} byte metadata budget"
        )
    counts = Counter(info.filename for info in infos)
    warnings = [
        f"duplicate ZIP member name: {name}"
        for name, count in counts.items()
        if count > 1
    ]
    entries = {info.filename: info for info in infos if not info.is_dir()}
    return bundle, entries, warnings


def _member_meta(info: zipfile.ZipInfo) -> dict[str, Any]:
    ratio = (
        round(info.file_size / max(info.compress_size, 1), 2)
        if info.file_size
        else 0.0
    )
    return {
        "size": info.file_size,
        "compressed_size": info.compress_size,
        "crc32": f"{info.CRC:08x}",
        "compression": info.compress_type,
        "compression_ratio": ratio,
        "encrypted": bool(info.flag_bits & 0x1),
    }


def _read_member(
    bundle: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    *,
    limit: int,
) -> bytes:
    if info.file_size > limit:
        raise WorkLimitError(
            f"archive member {info.filename!r} is above the {limit} byte deep limit"
        )
    if info.flag_bits & 0x1:
        raise AnalysisError(f"archive member {info.filename!r} is encrypted")
    with bundle.open(info, "r") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise WorkLimitError(f"archive member {info.filename!r} exceeded read limit")
    return data


def _nested_analysis(
    name: str,
    before: bytes,
    after: bytes,
    *,
    expectations: Iterable[tuple[int | float, int | float]],
) -> dict[str, Any]:
    kind = detect_format(name, before, after)
    if kind in {"json", "toml", "ini"}:
        return analyze_structured(
            before,
            after,
            kind,
            expectations=expectations,
            max_changes=80,
        )
    if kind == "text":
        return analyze_text(
            before,
            after,
            path=name,
            max_diff_lines=120,
        )
    return analyze_binary(
        before,
        after,
        expectations=expectations,
        max_spans=40,
        preview_bytes=24,
    )


def analyze_zip(
    before_data: bytes,
    after_data: bytes,
    *,
    expectations: Iterable[tuple[int | float, int | float]] = (),
    max_entries: int = 20_000,
    max_expanded_bytes: int = 512 * 1024 * 1024,
    deep_member_limit: int = 2 * 1024 * 1024,
    max_deep_members: int = 20,
) -> dict[str, Any]:
    before_zip, before_entries, before_warnings = _index(
        before_data,
        max_entries=max_entries,
        max_expanded_bytes=max_expanded_bytes,
    )
    after_zip, after_entries, after_warnings = _index(
        after_data,
        max_entries=max_entries,
        max_expanded_bytes=max_expanded_bytes,
    )
    try:
        changes: list[dict[str, Any]] = []
        deep_count = 0
        for name in sorted(set(before_entries) | set(after_entries)):
            old = before_entries.get(name)
            new = after_entries.get(name)
            if old is None:
                changes.append(
                    {
                        "path": PurePosixPath(name).as_posix(),
                        "status": "added",
                        "after": _member_meta(new),
                    }
                )
                continue
            if new is None:
                changes.append(
                    {
                        "path": PurePosixPath(name).as_posix(),
                        "status": "removed",
                        "before": _member_meta(old),
                    }
                )
                continue
            if old.CRC == new.CRC and old.file_size == new.file_size:
                continue
            change: dict[str, Any] = {
                "path": PurePosixPath(name).as_posix(),
                "status": "modified",
                "before": _member_meta(old),
                "after": _member_meta(new),
            }
            if (
                deep_count < max_deep_members
                and old.file_size <= deep_member_limit
                and new.file_size <= deep_member_limit
                and not (old.flag_bits & 0x1 or new.flag_bits & 0x1)
            ):
                try:
                    old_data = _read_member(
                        before_zip,
                        old,
                        limit=deep_member_limit,
                    )
                    new_data = _read_member(
                        after_zip,
                        new,
                        limit=deep_member_limit,
                    )
                    change["analysis"] = _nested_analysis(
                        name,
                        old_data,
                        new_data,
                        expectations=expectations,
                    )
                    deep_count += 1
                except (AnalysisError, WorkLimitError, RuntimeError) as exc:
                    change["analysis_warning"] = str(exc)
            changes.append(change)

        return {
            "kind": "zip",
            "entries_before": len(before_entries),
            "entries_after": len(after_entries),
            "change_count": len(changes),
            "deep_analyzed_members": deep_count,
            "changes": changes,
            "warnings": [*before_warnings, *after_warnings],
        }
    finally:
        before_zip.close()
        after_zip.close()
