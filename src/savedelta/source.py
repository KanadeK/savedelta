from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Iterable

from .errors import SnapshotFormatError, WorkLimitError
from .models import FileEntry, SourceView
from .util import (
    DEFAULT_IGNORES,
    is_ignored,
    normalize_relative,
    read_limited,
    safe_member_name,
    sha256_file,
    sha256_bytes,
    validate_logical_path,
)


SNAPSHOT_FORMAT_VERSION = 1
SNAPSHOT_MANIFEST = "manifest.json"


def _direct_reader(path: Path):
    def read(limit: int | None) -> bytes:
        return read_limited(path, limit)

    return read


def _snapshot_reader(archive: Path, member: str, size: int, expected_digest: str):
    def read(limit: int | None) -> bytes:
        if limit is not None and size > limit:
            raise WorkLimitError(
                f"snapshot member is {size} bytes, above the {limit} byte limit"
            )
        with zipfile.ZipFile(archive, "r") as bundle:
            info = bundle.getinfo(member)
            if info.file_size != size:
                raise SnapshotFormatError(
                    f"snapshot member size changed for {member!r}"
                )
            with bundle.open(info, "r") as stream:
                data = stream.read(size + 1)
            if len(data) != size:
                raise SnapshotFormatError(
                    f"snapshot member length mismatch for {member!r}"
                )
            if sha256_bytes(data) != expected_digest:
                raise SnapshotFormatError(
                    f"snapshot member digest mismatch for {member!r}"
                )
            return data

    return read


def _verify_member(
    bundle: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    expected_digest: str,
) -> None:
    digest = hashlib.sha256()
    total = 0
    with bundle.open(info, "r") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            total += len(chunk)
            digest.update(chunk)
    if total != info.file_size:
        raise SnapshotFormatError(
            f"snapshot member length mismatch for {info.filename!r}"
        )
    if digest.hexdigest() != expected_digest:
        raise SnapshotFormatError(
            f"snapshot member digest mismatch for {info.filename!r}"
        )


def _validated_snapshot_entries(
    path: Path,
    infos: dict[str, zipfile.ZipInfo],
    raw_entries: list[Any],
) -> dict[str, FileEntry]:
    entries: dict[str, FileEntry] = {}
    members_seen: set[str] = set()
    try:
        with zipfile.ZipFile(path, "r") as verification_bundle:
            for index, raw in enumerate(raw_entries, start=1):
                if not isinstance(raw, dict):
                    raise SnapshotFormatError("snapshot entry must be an object")
                try:
                    logical_path = validate_logical_path(str(raw["path"]))
                    member = str(raw["member"])
                    size = int(raw["size"])
                    digest = str(raw["sha256"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise SnapshotFormatError(
                        f"invalid snapshot entry: {raw!r}"
                    ) from exc
                if member != safe_member_name(index):
                    raise SnapshotFormatError(
                        f"unexpected data member name {member!r}"
                    )
                if not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise SnapshotFormatError(
                        f"invalid SHA-256 for snapshot member {member!r}"
                    )
                if member in members_seen:
                    raise SnapshotFormatError(
                        f"duplicate snapshot member {member!r}"
                    )
                members_seen.add(member)
                if member not in infos or member == SNAPSHOT_MANIFEST:
                    raise SnapshotFormatError(f"missing data member {member!r}")
                info = infos[member]
                if info.is_dir() or info.file_size != size or size < 0:
                    raise SnapshotFormatError(
                        f"invalid member metadata for {member!r}"
                    )
                if logical_path in entries:
                    raise SnapshotFormatError(
                        f"duplicate logical path {logical_path!r}"
                    )
                _verify_member(verification_bundle, info, digest)
                entries[logical_path] = FileEntry(
                    path=logical_path,
                    size=size,
                    sha256=digest,
                    reader=_snapshot_reader(path, member, size, digest),
                )
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise SnapshotFormatError(
            f"cannot verify snapshot {path}: {exc}"
        ) from exc
    return entries


def is_snapshot(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        with zipfile.ZipFile(path, "r") as bundle:
            return SNAPSHOT_MANIFEST in bundle.namelist()
    except (OSError, zipfile.BadZipFile):
        return False


def load_snapshot(path: Path) -> SourceView:
    try:
        with zipfile.ZipFile(path, "r") as bundle:
            infos = {info.filename: info for info in bundle.infolist()}
            manifest_info = infos.get(SNAPSHOT_MANIFEST)
            if manifest_info is None:
                raise SnapshotFormatError("missing manifest.json")
            if manifest_info.file_size > 16 * 1024 * 1024:
                raise SnapshotFormatError("snapshot manifest is unexpectedly large")
            manifest = json.loads(bundle.read(manifest_info).decode("utf-8"))
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotFormatError(f"cannot read snapshot {path}: {exc}") from exc

    if not isinstance(manifest, dict):
        raise SnapshotFormatError("snapshot manifest must be an object")
    if manifest.get("format") != "savedelta-snapshot":
        raise SnapshotFormatError("unrecognized snapshot format")
    if manifest.get("format_version") != SNAPSHOT_FORMAT_VERSION:
        raise SnapshotFormatError(
            "unsupported snapshot format version "
            f"{manifest.get('format_version')!r}"
        )

    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list):
        raise SnapshotFormatError("snapshot entries must be a list")
    if len(raw_entries) > 1_000_000:
        raise SnapshotFormatError("snapshot contains too many entries")

    entries = _validated_snapshot_entries(path, infos, raw_entries)
    raw_warnings = manifest.get("warnings", [])
    if not isinstance(raw_warnings, list) or not all(
        isinstance(item, str) for item in raw_warnings
    ):
        raise SnapshotFormatError("snapshot warnings must be a string list")

    return SourceView(
        label=str(path),
        kind="snapshot",
        entries=entries,
        warnings=list(raw_warnings),
        single_file=bool(manifest.get("single_file", False)),
    )


def load_direct(
    path: Path,
    *,
    ignore_patterns: Iterable[str] = (),
    default_ignores: bool = True,
) -> SourceView:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"input does not exist: {path}")
    patterns = tuple(DEFAULT_IGNORES if default_ignores else ()) + tuple(
        ignore_patterns
    )
    warnings: list[str] = []
    entries: dict[str, FileEntry] = {}

    if resolved.is_file():
        entries[resolved.name] = FileEntry(
            path=resolved.name,
            size=resolved.stat().st_size,
            sha256=sha256_file(resolved),
            reader=_direct_reader(resolved),
            native_path=resolved,
        )
        return SourceView(
            label=str(resolved),
            kind="file",
            entries=entries,
            warnings=warnings,
            single_file=True,
        )

    if not resolved.is_dir():
        raise ValueError(f"input is not a regular file or directory: {path}")

    for candidate in sorted(resolved.rglob("*")):
        relative = normalize_relative(candidate.relative_to(resolved))
        if is_ignored(relative, patterns):
            continue
        if candidate.is_symlink():
            warnings.append(f"skipped symlink: {relative}")
            continue
        if not candidate.is_file():
            continue
        try:
            stat = candidate.stat()
            digest = sha256_file(candidate)
        except OSError as exc:
            warnings.append(f"skipped unreadable file {relative}: {exc}")
            continue
        entries[relative] = FileEntry(
            path=relative,
            size=stat.st_size,
            sha256=digest,
            reader=_direct_reader(candidate),
            native_path=candidate,
        )

    return SourceView(
        label=str(resolved),
        kind="directory",
        entries=entries,
        warnings=warnings,
        single_file=False,
    )


def load_source(
    path: str | Path,
    *,
    ignore_patterns: Iterable[str] = (),
    default_ignores: bool = True,
) -> SourceView:
    candidate = Path(path).expanduser()
    if is_snapshot(candidate):
        return load_snapshot(candidate.resolve())
    return load_direct(
        candidate,
        ignore_patterns=ignore_patterns,
        default_ignores=default_ignores,
    )


def manifest_entry(
    path: str,
    *,
    member: str,
    size: int,
    sha256: str,
) -> dict[str, Any]:
    return {
        "path": path,
        "member": member,
        "size": size,
        "sha256": sha256,
    }
