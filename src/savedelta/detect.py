from __future__ import annotations

import json
from pathlib import PurePosixPath


SQLITE_MAGIC = b"SQLite format 3\x00"
ZIP_MAGICS = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")

JSON_EXTENSIONS = {".json", ".jsonc", ".mcmeta"}
TOML_EXTENSIONS = {".toml"}
INI_EXTENSIONS = {".ini", ".cfg", ".conf", ".prefs"}
TEXT_EXTENSIONS = {
    ".ass",
    ".csv",
    ".env",
    ".log",
    ".md",
    ".po",
    ".properties",
    ".srt",
    ".txt",
    ".vtt",
    ".xml",
    ".yaml",
    ".yml",
}


def decode_text(data: bytes) -> tuple[str, str] | None:
    if data.startswith(b"\xef\xbb\xbf"):
        try:
            return data.decode("utf-8-sig"), "utf-8-sig"
        except UnicodeDecodeError:
            return None
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16"), "utf-16"
        except UnicodeDecodeError:
            return None
    if b"\x00" in data[:8192]:
        return None
    try:
        text = data.decode("utf-8")
        return text, "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        text = data.decode("latin-1")
    except UnicodeDecodeError:
        return None
    if not text:
        return text, "latin-1"
    printable = sum(char.isprintable() or char in "\r\n\t" for char in text)
    if printable / len(text) < 0.90:
        return None
    return text, "latin-1"


def looks_like_json(data: bytes) -> bool:
    decoded = decode_text(data)
    if decoded is None:
        return False
    text = decoded[0].lstrip()
    if not text.startswith(("{", "[")):
        return False
    try:
        json.loads(text)
        return True
    except json.JSONDecodeError:
        return False


def detect_format(path: str, before: bytes, after: bytes) -> str:
    samples = (before, after)
    if all(sample.startswith(SQLITE_MAGIC) for sample in samples):
        return "sqlite"
    if all(sample.startswith(ZIP_MAGICS) for sample in samples):
        return "zip"

    suffix = PurePosixPath(path).suffix.lower()
    if suffix in JSON_EXTENSIONS or all(looks_like_json(sample) for sample in samples):
        return "json"
    if suffix in TOML_EXTENSIONS:
        return "toml"
    if suffix in INI_EXTENSIONS:
        return "ini"
    if suffix in TEXT_EXTENSIONS:
        return "text"
    if all(decode_text(sample) is not None for sample in samples):
        return "text"
    return "binary"


def detect_single_format(path: str, data: bytes) -> str:
    return detect_format(path, data, data)
