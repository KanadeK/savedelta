from __future__ import annotations

import fnmatch
import hashlib
import math
import os
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Iterable

from .errors import WorkLimitError


DEFAULT_IGNORES = (
    ".git",
    ".git/**",
    ".DS_Store",
    "Thumbs.db",
    "*.lock",
    "*.lck",
    "*.tmp",
    "*.temp",
    "~$*",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_limited(path: Path, limit: int | None = None) -> bytes:
    size = path.stat().st_size
    if limit is not None and size > limit:
        raise WorkLimitError(
            f"{path} is {format_bytes(size)}, above the "
            f"{format_bytes(limit)} analysis limit"
        )
    return path.read_bytes()


def read_stream_limited(stream: BinaryIO, size: int, limit: int | None) -> bytes:
    if limit is not None and size > limit:
        raise WorkLimitError(
            f"file is {format_bytes(size)}, above the "
            f"{format_bytes(limit)} analysis limit"
        )
    data = stream.read(size + 1)
    if len(data) > size:
        data = data[:size]
    return data


def normalize_relative(path: Path) -> str:
    value = PurePosixPath(*path.parts).as_posix()
    if value in {"", "."}:
        return path.name or "input"
    return value


def is_ignored(path: str, patterns: Iterable[str]) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    name = PurePosixPath(normalized).name
    for pattern in patterns:
        clean = pattern.replace("\\", "/").lstrip("./")
        if fnmatch.fnmatch(normalized, clean) or fnmatch.fnmatch(name, clean):
            return True
        if clean.endswith("/**") and normalized == clean[:-3].rstrip("/"):
            return True
    return False


def safe_member_name(index: int) -> str:
    return f"data/{index:08d}.bin"


def format_bytes(value: int | None) -> str:
    if value is None:
        return "—"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    number = float(value)
    for unit in units:
        if abs(number) < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(number)} {unit}"
            return f"{number:.1f} {unit}"
        number /= 1024.0
    return f"{value} B"


def truncate_text(value: Any, limit: int = 240) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)]}…"


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, float) and not math.isfinite(value):
            return str(value)
        return value
    if isinstance(value, bytes):
        return {
            "type": "bytes",
            "length": len(value),
            "sha256": sha256_bytes(value),
            "hex_preview": value[:32].hex(),
        }
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    length = len(data)
    return -sum(
        (count / length) * math.log2(count / length) for count in counts.values()
    )


def ascii_preview(data: bytes, limit: int = 48) -> str:
    return "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in data[:limit])


def extract_strings(
    data: bytes,
    *,
    minimum: int = 4,
    maximum_results: int = 40,
) -> list[dict[str, Any]]:
    pattern = re.compile(rb"[\x20-\x7e]{%d,}" % minimum)
    result: list[dict[str, Any]] = []
    for match in pattern.finditer(data):
        result.append(
            {
                "offset": match.start(),
                "text": truncate_text(match.group().decode("ascii"), 160),
            }
        )
        if len(result) >= maximum_results:
            break
    return result


def parse_number(value: str) -> int | float:
    clean = value.strip().replace("_", "")
    lowered = clean.lower()
    if any(marker in lowered for marker in (".", "e")):
        return float(clean)
    return int(clean, 0)


def split_expectation(value: str) -> tuple[int | float, int | float]:
    for delimiter in ("->", ":", "→"):
        if delimiter in value:
            before, after = value.split(delimiter, 1)
            return parse_number(before), parse_number(after)
    raise ValueError(
        f"invalid expectation {value!r}; use FROM:TO, for example 100:250"
    )


def parse_size(value: str) -> int:
    match = re.fullmatch(
        r"\s*(\d+(?:\.\d+)?)\s*(b|kb|kib|mb|mib|gb|gib)?\s*",
        value,
        flags=re.IGNORECASE,
    )
    if not match:
        raise ValueError(
            f"invalid size {value!r}; examples: 1048576, 64MiB, 1GB"
        )
    number = float(match.group(1))
    unit = (match.group(2) or "b").lower()
    multipliers = {
        "b": 1,
        "kb": 1_000,
        "kib": 1_024,
        "mb": 1_000_000,
        "mib": 1_048_576,
        "gb": 1_000_000_000,
        "gib": 1_073_741_824,
    }
    result = int(number * multipliers[unit])
    if result < 1:
        raise ValueError("size must be at least 1 byte")
    return result


def validate_logical_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    candidate = PurePosixPath(normalized)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"unsafe logical path in snapshot: {value!r}")
    if normalized in {"", "."}:
        raise ValueError("empty logical path in snapshot")
    return candidate.as_posix()


def common_parent(paths: list[Path]) -> Path:
    if not paths:
        return Path.cwd()
    return Path(os.path.commonpath([str(path) for path in paths]))
