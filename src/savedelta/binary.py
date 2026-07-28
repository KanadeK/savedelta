from __future__ import annotations

import math
import struct
from collections import Counter
from typing import Any, Iterable

from .util import ascii_preview, shannon_entropy


def _changed_spans_same_size(
    before: bytes,
    after: bytes,
    *,
    max_spans: int,
    preview_bytes: int,
) -> tuple[list[dict[str, Any]], int, bool]:
    spans: list[dict[str, Any]] = []
    different = 0
    index = 0
    truncated = False
    length = len(before)
    while index < length:
        if before[index] == after[index]:
            index += 1
            continue
        start = index
        while index < length and before[index] != after[index]:
            different += 1
            index += 1
        end = index
        if len(spans) < max_spans:
            old = before[start:end]
            new = after[start:end]
            spans.append(
                {
                    "start": start,
                    "end": end,
                    "length": end - start,
                    "before_hex": old[:preview_bytes].hex(" "),
                    "after_hex": new[:preview_bytes].hex(" "),
                    "before_ascii": ascii_preview(old, preview_bytes),
                    "after_ascii": ascii_preview(new, preview_bytes),
                    "preview_truncated": len(old) > preview_bytes,
                }
            )
        else:
            truncated = True
    return spans, different, truncated


def _different_size_span(
    before: bytes,
    after: bytes,
    *,
    preview_bytes: int,
) -> tuple[list[dict[str, Any]], int, int]:
    prefix = 0
    common = min(len(before), len(after))
    while prefix < common and before[prefix] == after[prefix]:
        prefix += 1

    suffix = 0
    remaining = common - prefix
    while (
        suffix < remaining
        and before[len(before) - 1 - suffix] == after[len(after) - 1 - suffix]
    ):
        suffix += 1

    before_end = len(before) - suffix
    after_end = len(after) - suffix
    old = before[prefix:before_end]
    new = after[prefix:after_end]
    span = {
        "start": prefix,
        "before_end": before_end,
        "after_end": after_end,
        "before_length": len(old),
        "after_length": len(new),
        "before_hex": old[:preview_bytes].hex(" "),
        "after_hex": new[:preview_bytes].hex(" "),
        "before_ascii": ascii_preview(old, preview_bytes),
        "after_ascii": ascii_preview(new, preview_bytes),
        "preview_truncated": max(len(old), len(new)) > preview_bytes,
    }
    return [span], prefix, suffix


def _value_specs() -> list[tuple[str, str, str]]:
    specs: list[tuple[str, str, str]] = [
        ("u8", "B", "native"),
        ("i8", "b", "native"),
    ]
    for name, code in (
        ("u16", "H"),
        ("i16", "h"),
        ("u32", "I"),
        ("i32", "i"),
        ("u64", "Q"),
        ("i64", "q"),
        ("f32", "f"),
        ("f64", "d"),
    ):
        specs.append((name, f"<{code}", "little"))
        specs.append((name, f">{code}", "big"))
    return specs


def _pack_value(value: int | float, code: str) -> bytes | None:
    try:
        return struct.pack(code, value)
    except (OverflowError, struct.error):
        return None


def locate_value_change(
    before: bytes,
    after: bytes,
    old_value: int | float,
    new_value: int | float,
    *,
    maximum_results: int = 80,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[tuple[int, bytes, bytes, str]] = set()
    same_length = len(before) == len(after)

    for type_name, code, endian in _value_specs():
        matches_for_spec = 0
        old_bytes = _pack_value(old_value, code)
        new_bytes = _pack_value(new_value, code)
        if old_bytes is None or new_bytes is None:
            continue
        width = len(old_bytes)
        occurrence_count = before.count(old_bytes)
        target_count = after.count(new_bytes)
        position = before.find(old_bytes)
        while position >= 0:
            if after[position : position + width] == new_bytes:
                key = (position, old_bytes, new_bytes, endian)
                if key not in seen:
                    seen.add(key)
                    context_start = max(0, position - 8)
                    context_end = min(
                        len(before),
                        len(after),
                        position + width + 8,
                    )
                    surrounding_before = (
                        before[context_start:position]
                        + before[position + width : context_end]
                    )
                    surrounding_after = (
                        after[context_start:position]
                        + after[position + width : context_end]
                    )
                    aligned = width == 1 or position % width == 0
                    signals: list[str] = []
                    score = 0.45
                    if occurrence_count == 1 and target_count == 1:
                        score += 0.18
                        signals.append("unique_before_after")
                    if width in {4, 8}:
                        score += 0.05
                        signals.append("common_field_width")
                    if width > 1 and aligned:
                        score += 0.12
                        signals.append("natural_alignment")
                    if endian == "little":
                        score += 0.03
                        signals.append("little_endian")
                    if surrounding_before == surrounding_after:
                        score += 0.10
                        signals.append("stable_surroundings")
                    if same_length:
                        score += 0.05
                        signals.append("same_file_size")
                    results.append(
                        {
                            "offset": position,
                            "offset_hex": f"0x{position:X}",
                            "type": type_name,
                            "endian": endian,
                            "width": width,
                            "from": old_value,
                            "to": new_value,
                            "before_hex": old_bytes.hex(" "),
                            "after_hex": new_bytes.hex(" "),
                            "confidence": round(min(score, 1.0), 2),
                            "signals": signals,
                            "aligned": aligned,
                            "unique_before": occurrence_count == 1,
                            "unique_after": target_count == 1,
                        }
                    )
                    matches_for_spec += 1
                    if matches_for_spec >= maximum_results:
                        break
            position = before.find(old_bytes, position + 1)

    return sorted(
        results,
        key=lambda item: (
            -item["confidence"],
            -item["width"],
            item["offset"],
            item["type"],
        ),
    )[:maximum_results]


def analyze_binary(
    before: bytes,
    after: bytes,
    *,
    expectations: Iterable[tuple[int | float, int | float]] = (),
    max_spans: int = 200,
    preview_bytes: int = 48,
) -> dict[str, Any]:
    if len(before) == len(after):
        spans, different, truncated = _changed_spans_same_size(
            before,
            after,
            max_spans=max_spans,
            preview_bytes=preview_bytes,
        )
        prefix = 0
        for old, new in zip(before, after):
            if old != new:
                break
            prefix += 1
        suffix = 0
        for old, new in zip(reversed(before), reversed(after)):
            if old != new or suffix >= len(before) - prefix:
                break
            suffix += 1
    else:
        spans, prefix, suffix = _different_size_span(
            before,
            after,
            preview_bytes=preview_bytes,
        )
        overlap = min(len(before), len(after))
        different = sum(
            before[index] != after[index] for index in range(overlap)
        ) + abs(len(before) - len(after))
        truncated = False

    denominator = max(len(before), len(after), 1)
    histogram_before = Counter(before)
    histogram_after = Counter(after)
    top_byte_changes = sorted(
        (
            {
                "byte": f"0x{byte:02X}",
                "before_count": histogram_before[byte],
                "after_count": histogram_after[byte],
                "delta": histogram_after[byte] - histogram_before[byte],
            }
            for byte in set(histogram_before) | set(histogram_after)
            if histogram_before[byte] != histogram_after[byte]
        ),
        key=lambda item: abs(item["delta"]),
        reverse=True,
    )[:12]

    expectation_results = []
    for old, new in expectations:
        candidates = locate_value_change(before, after, old, new)
        expectation_results.append(
            {
                "from": old,
                "to": new,
                "candidate_count": len(candidates),
                "candidates": candidates,
            }
        )

    entropy_before = shannon_entropy(before)
    entropy_after = shannon_entropy(after)
    return {
        "kind": "binary",
        "size_before": len(before),
        "size_after": len(after),
        "size_delta": len(after) - len(before),
        "different_bytes": different,
        "change_ratio": round(different / denominator, 6),
        "common_prefix_bytes": prefix,
        "common_suffix_bytes": suffix,
        "entropy_before": round(entropy_before, 4),
        "entropy_after": round(entropy_after, 4),
        "entropy_delta": round(entropy_after - entropy_before, 4),
        "likely_compressed_or_encrypted": (
            min(entropy_before, entropy_after) >= 7.6
        ),
        "span_count": len(spans),
        "spans_truncated": truncated,
        "spans": spans,
        "top_byte_count_changes": top_byte_changes,
        "expectation_matches": expectation_results,
    }
