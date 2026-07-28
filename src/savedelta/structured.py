from __future__ import annotations

import configparser
import io
import json
import tomllib
from dataclasses import dataclass
from typing import Any, Iterable

from .errors import AnalysisError
from .util import json_safe, truncate_text


MISSING = object()


@dataclass(slots=True)
class StructureOptions:
    max_changes: int = 300
    value_preview: int = 240


def _parse_ini(data: bytes) -> dict[str, Any]:
    text = data.decode("utf-8-sig")
    parser = configparser.ConfigParser(
        interpolation=None,
        strict=False,
        empty_lines_in_values=True,
    )
    parser.optionxform = str
    parser.read_file(io.StringIO(text))
    result: dict[str, Any] = {}
    if parser.defaults():
        result["DEFAULT"] = dict(parser.defaults())
    for section in parser.sections():
        result[section] = dict(parser.items(section, raw=True))
    return result


def parse_structured(data: bytes, kind: str) -> Any:
    try:
        if kind == "json":
            return json.loads(data.decode("utf-8-sig"))
        if kind == "toml":
            return tomllib.loads(data.decode("utf-8-sig"))
        if kind == "ini":
            return _parse_ini(data)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        tomllib.TOMLDecodeError,
        configparser.Error,
    ) as exc:
        raise AnalysisError(f"cannot parse {kind}: {exc}") from exc
    raise AnalysisError(f"unsupported structured format: {kind}")


def _path_key(parent: str, key: Any) -> str:
    if isinstance(key, int):
        return f"{parent}[{key}]"
    text = str(key)
    if text.replace("_", "").isalnum() and not text[:1].isdigit():
        return f"{parent}.{text}"
    return f"{parent}[{json.dumps(text, ensure_ascii=False)}]"


def _preview(value: Any, limit: int) -> Any:
    safe = json_safe(value)
    if isinstance(safe, str):
        return truncate_text(safe, limit)
    encoded = json.dumps(safe, ensure_ascii=False, sort_keys=True)
    if len(encoded) <= limit:
        return safe
    return truncate_text(encoded, limit)


def structural_diff(
    before: Any,
    after: Any,
    *,
    options: StructureOptions | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    opts = options or StructureOptions()
    changes: list[dict[str, Any]] = []
    truncated = False

    def add(change: dict[str, Any]) -> None:
        nonlocal truncated
        if len(changes) >= opts.max_changes:
            truncated = True
            return
        changes.append(change)

    def walk(left: Any, right: Any, path: str) -> None:
        if truncated:
            return
        if type(left) is not type(right):
            add(
                {
                    "path": path,
                    "kind": "type_changed",
                    "before": _preview(left, opts.value_preview),
                    "after": _preview(right, opts.value_preview),
                    "before_type": type(left).__name__,
                    "after_type": type(right).__name__,
                }
            )
            return

        if isinstance(left, dict):
            keys = sorted(set(left) | set(right), key=str)
            for key in keys:
                child_path = _path_key(path, key)
                left_value = left.get(key, MISSING)
                right_value = right.get(key, MISSING)
                if left_value is MISSING:
                    add(
                        {
                            "path": child_path,
                            "kind": "added",
                            "after": _preview(right_value, opts.value_preview),
                        }
                    )
                elif right_value is MISSING:
                    add(
                        {
                            "path": child_path,
                            "kind": "removed",
                            "before": _preview(left_value, opts.value_preview),
                        }
                    )
                else:
                    walk(left_value, right_value, child_path)
            return

        if isinstance(left, list):
            common = min(len(left), len(right))
            for index in range(common):
                walk(left[index], right[index], _path_key(path, index))
            for index in range(common, len(left)):
                add(
                    {
                        "path": _path_key(path, index),
                        "kind": "removed",
                        "before": _preview(left[index], opts.value_preview),
                    }
                )
            for index in range(common, len(right)):
                add(
                    {
                        "path": _path_key(path, index),
                        "kind": "added",
                        "after": _preview(right[index], opts.value_preview),
                    }
                )
            return

        if left != right:
            add(
                {
                    "path": path,
                    "kind": "changed",
                    "before": _preview(left, opts.value_preview),
                    "after": _preview(right, opts.value_preview),
                }
            )

    walk(before, after, "$")
    return changes, truncated


def _expectation_matches(
    changes: Iterable[dict[str, Any]],
    expectations: Iterable[tuple[int | float, int | float]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    expected = list(expectations)
    for change in changes:
        if change.get("kind") not in {"changed", "type_changed"}:
            continue
        before = change.get("before")
        after = change.get("after")
        for old, new in expected:
            if before == old and after == new:
                result.append(
                    {
                        "path": change["path"],
                        "from": old,
                        "to": new,
                        "confidence": 1.0,
                        "reason": "exact structured value change",
                    }
                )
    return result


def analyze_structured(
    before_data: bytes,
    after_data: bytes,
    kind: str,
    *,
    expectations: Iterable[tuple[int | float, int | float]] = (),
    max_changes: int = 300,
) -> dict[str, Any]:
    before = parse_structured(before_data, kind)
    after = parse_structured(after_data, kind)
    changes, truncated = structural_diff(
        before,
        after,
        options=StructureOptions(max_changes=max_changes),
    )
    return {
        "kind": kind,
        "change_count": len(changes),
        "truncated": truncated,
        "changes": changes,
        "expectation_matches": _expectation_matches(changes, expectations),
    }
