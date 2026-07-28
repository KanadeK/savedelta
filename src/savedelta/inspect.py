from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

from .detect import decode_text, detect_single_format
from .errors import WorkLimitError
from .util import (
    extract_strings,
    format_bytes,
    sha256_bytes,
    shannon_entropy,
)


def _sqlite_inventory(data: bytes) -> dict[str, Any]:
    connection = sqlite3.connect(":memory:")
    try:
        connection.deserialize(data)
        connection.execute("PRAGMA query_only = ON")
        rows = connection.execute(
            """
            SELECT type, name, tbl_name
            FROM sqlite_master
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall()
        return {
            "objects": [
                {"type": row[0], "name": row[1], "table": row[2]} for row in rows
            ]
        }
    except sqlite3.DatabaseError as exc:
        return {"warning": f"SQLite inventory unavailable: {exc}"}
    finally:
        connection.close()


def _zip_inventory(data: bytes, max_entries: int = 500) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as bundle:
            infos = bundle.infolist()
            return {
                "entry_count": len(infos),
                "expanded_bytes": sum(info.file_size for info in infos),
                "entries_truncated": len(infos) > max_entries,
                "entries": [
                    {
                        "path": info.filename,
                        "size": info.file_size,
                        "compressed_size": info.compress_size,
                        "crc32": f"{info.CRC:08x}",
                        "encrypted": bool(info.flag_bits & 0x1),
                    }
                    for info in infos[:max_entries]
                ],
            }
    except zipfile.BadZipFile as exc:
        return {"warning": f"ZIP inventory unavailable: {exc}"}


def inspect_file(
    path: str | Path,
    *,
    max_file_bytes: int = 64 * 1024 * 1024,
) -> dict[str, Any]:
    candidate = Path(path).expanduser().resolve()
    if not candidate.is_file():
        raise ValueError(f"inspect expects a regular file: {candidate}")
    size = candidate.stat().st_size
    if size > max_file_bytes:
        raise WorkLimitError(
            f"{candidate} is {format_bytes(size)}, above the "
            f"{format_bytes(max_file_bytes)} inspect limit"
        )
    data = candidate.read_bytes()
    kind = detect_single_format(candidate.name, data)
    result: dict[str, Any] = {
        "path": str(candidate),
        "name": candidate.name,
        "size": size,
        "sha256": sha256_bytes(data),
        "format": kind,
        "entropy": round(shannon_entropy(data), 4),
    }
    if kind == "sqlite":
        result["sqlite"] = _sqlite_inventory(data)
    elif kind == "zip":
        result["zip"] = _zip_inventory(data)
    elif kind in {"json", "toml", "ini", "text"}:
        decoded = decode_text(data)
        if decoded is not None:
            text, encoding = decoded
            result["text"] = {
                "encoding": encoding,
                "line_count": len(text.splitlines()),
                "character_count": len(text),
            }
            if kind == "json":
                try:
                    parsed = json.loads(text)
                    result["json"] = {
                        "root_type": type(parsed).__name__,
                        "top_level_keys": (
                            sorted(str(key) for key in parsed)[:100]
                            if isinstance(parsed, dict)
                            else None
                        ),
                    }
                except json.JSONDecodeError:
                    pass
    else:
        result["strings"] = extract_strings(data)
    return result
