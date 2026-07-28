from __future__ import annotations

import unittest

from savedelta.util import (
    format_bytes,
    is_ignored,
    parse_size,
    shannon_entropy,
    split_expectation,
    validate_logical_path,
)


class UtilTests(unittest.TestCase):
    def test_parse_binary_size(self) -> None:
        self.assertEqual(parse_size("64MiB"), 64 * 1024 * 1024)

    def test_parse_decimal_size(self) -> None:
        self.assertEqual(parse_size("1.5MB"), 1_500_000)

    def test_parse_size_rejects_unknown_unit(self) -> None:
        with self.assertRaises(ValueError):
            parse_size("4 elephants")

    def test_split_expectation_accepts_hex(self) -> None:
        self.assertEqual(split_expectation("0x10:0x20"), (16, 32))

    def test_split_expectation_accepts_float(self) -> None:
        self.assertEqual(split_expectation("1.5->2.25"), (1.5, 2.25))

    def test_validate_logical_path_rejects_parent_escape(self) -> None:
        with self.assertRaises(ValueError):
            validate_logical_path("../secret")

    def test_ignore_matches_nested_git(self) -> None:
        self.assertTrue(is_ignored(".git/objects/a", (".git/**",)))

    def test_entropy_extremes(self) -> None:
        self.assertEqual(shannon_entropy(b"\x00" * 100), 0.0)
        self.assertGreater(shannon_entropy(bytes(range(256))), 7.9)

    def test_format_bytes(self) -> None:
        self.assertEqual(format_bytes(1024), "1.0 KiB")


if __name__ == "__main__":
    unittest.main()
