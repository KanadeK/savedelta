from __future__ import annotations

import struct
import unittest

from savedelta.binary import analyze_binary, locate_value_change


class BinaryAnalysisTests(unittest.TestCase):
    def test_same_size_changed_spans(self) -> None:
        result = analyze_binary(b"abc123xyz", b"abc456xyz")
        self.assertEqual(result["different_bytes"], 3)
        self.assertEqual(result["span_count"], 1)
        self.assertEqual(result["spans"][0]["start"], 3)
        self.assertEqual(result["spans"][0]["end"], 6)

    def test_different_size_reports_common_edges(self) -> None:
        result = analyze_binary(b"headOLDtail", b"headNEWERtail")
        self.assertEqual(result["size_delta"], 2)
        self.assertEqual(result["common_prefix_bytes"], 4)
        self.assertEqual(result["common_suffix_bytes"], 4)

    def test_locates_little_endian_u32_change(self) -> None:
        before = bytearray(64)
        after = bytearray(64)
        struct.pack_into("<I", before, 20, 100)
        struct.pack_into("<I", after, 20, 250)
        matches = locate_value_change(bytes(before), bytes(after), 100, 250)
        selected = [
            item
            for item in matches
            if item["offset"] == 20
            and item["type"] == "u32"
            and item["endian"] == "little"
        ]
        self.assertEqual(len(selected), 1)
        self.assertEqual(matches[0], selected[0])

    def test_locates_float_change(self) -> None:
        before = struct.pack("<f", 1.5)
        after = struct.pack("<f", 2.25)
        matches = locate_value_change(before, after, 1.5, 2.25)
        self.assertTrue(
            any(
                item["type"] == "f32"
                and item["endian"] == "little"
                and item["offset"] == 0
                for item in matches
            )
        )

    def test_expectation_group_is_embedded(self) -> None:
        before = struct.pack("<I", 100)
        after = struct.pack("<I", 250)
        result = analyze_binary(before, after, expectations=((100, 250),))
        self.assertEqual(result["expectation_matches"][0]["from"], 100)
        self.assertGreater(
            result["expectation_matches"][0]["candidate_count"],
            0,
        )

    def test_span_limit_sets_truncation(self) -> None:
        before = bytes([0, 1] * 100)
        after = bytes([1, 1] * 100)
        result = analyze_binary(before, after, max_spans=3)
        self.assertEqual(result["span_count"], 3)
        self.assertTrue(result["spans_truncated"])

    def test_empty_files_are_supported(self) -> None:
        result = analyze_binary(b"", b"")
        self.assertEqual(result["change_ratio"], 0.0)
        self.assertEqual(result["entropy_before"], 0.0)


if __name__ == "__main__":
    unittest.main()
