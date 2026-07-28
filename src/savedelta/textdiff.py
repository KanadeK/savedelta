from __future__ import annotations

import difflib
from typing import Any

from .detect import decode_text
from .errors import AnalysisError


def analyze_text(
    before_data: bytes,
    after_data: bytes,
    *,
    path: str,
    max_diff_lines: int = 500,
) -> dict[str, Any]:
    before_decoded = decode_text(before_data)
    after_decoded = decode_text(after_data)
    if before_decoded is None or after_decoded is None:
        raise AnalysisError("input is not safely decodable text")
    before_text, before_encoding = before_decoded
    after_text, after_encoding = after_decoded
    before_lines = before_text.splitlines()
    after_lines = after_text.splitlines()

    generated = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"before/{path}",
            tofile=f"after/{path}",
            lineterm="",
            n=3,
        )
    )
    truncated = len(generated) > max_diff_lines
    visible = generated[:max_diff_lines]
    added = sum(line.startswith("+") and not line.startswith("+++") for line in generated)
    removed = sum(
        line.startswith("-") and not line.startswith("---") for line in generated
    )
    return {
        "kind": "text",
        "encoding_before": before_encoding,
        "encoding_after": after_encoding,
        "lines_before": len(before_lines),
        "lines_after": len(after_lines),
        "added_lines": added,
        "removed_lines": removed,
        "truncated": truncated,
        "unified_diff": visible,
    }
