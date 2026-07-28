from __future__ import annotations

import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable

from . import __version__
from .models import SourceView
from .source import SNAPSHOT_FORMAT_VERSION, SNAPSHOT_MANIFEST, load_direct
from .util import safe_member_name, utc_now


def create_snapshot(
    source: str | Path,
    output: str | Path,
    *,
    ignore_patterns: Iterable[str] = (),
    default_ignores: bool = True,
    compress: bool = True,
) -> tuple[Path, dict[str, object]]:
    source_path = Path(source).expanduser().resolve()
    output_path = Path(output).expanduser().resolve()
    if output_path == source_path:
        raise ValueError("snapshot output cannot overwrite its input")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    extra_ignores = list(ignore_patterns)
    try:
        if source_path.is_dir() and output_path.is_relative_to(source_path):
            extra_ignores.append(output_path.relative_to(source_path).as_posix())
    except ValueError:
        pass

    view: SourceView = load_direct(
        source_path,
        ignore_patterns=extra_ignores,
        default_ignores=default_ignores,
    )
    compression = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    manifest_entries: list[dict[str, object]] = []

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)

    try:
        with zipfile.ZipFile(
            temporary_path,
            mode="w",
            compression=compression,
            compresslevel=6 if compress else None,
            allowZip64=True,
        ) as bundle:
            for index, logical_path in enumerate(sorted(view.entries), start=1):
                entry = view.entries[logical_path]
                member = safe_member_name(index)
                bundle.write(entry.native_path, arcname=member)
                manifest_entries.append(
                    {
                        "path": logical_path,
                        "member": member,
                        "size": entry.size,
                        "sha256": entry.sha256,
                    }
                )

            manifest: dict[str, object] = {
                "format": "savedelta-snapshot",
                "format_version": SNAPSHOT_FORMAT_VERSION,
                "tool_version": __version__,
                "created_at": utc_now(),
                "source_name": source_path.name,
                "single_file": view.single_file,
                "compression": "deflate" if compress else "store",
                "warnings": view.warnings,
                "entries": manifest_entries,
            }
            manifest_bytes = (
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ).encode("utf-8")
                + b"\n"
            )
            info = zipfile.ZipInfo(SNAPSHOT_MANIFEST)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = compression
            info.external_attr = 0o644 << 16
            bundle.writestr(info, manifest_bytes)

        os.replace(temporary_path, output_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise

    stats: dict[str, object] = {
        "output": str(output_path),
        "files": len(manifest_entries),
        "input_bytes": sum(int(item["size"]) for item in manifest_entries),
        "snapshot_bytes": output_path.stat().st_size,
        "warnings": view.warnings,
    }
    return output_path, stats
