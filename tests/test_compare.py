from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from savedelta.compare import CompareOptions, compare_views
from savedelta.source import load_source


class CompareTests(unittest.TestCase):
    def test_identical_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "left"
            right = root / "right"
            left.mkdir()
            right.mkdir()
            (left / "same.txt").write_text("same\n")
            (right / "same.txt").write_text("same\n")
            report = compare_views(load_source(left), load_source(right))
            self.assertFalse(report.has_changes)
            self.assertEqual(report.summary["unchanged"], 1)

    def test_added_removed_and_modified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "left"
            right = root / "right"
            left.mkdir()
            right.mkdir()
            (left / "old.txt").write_text("old")
            (left / "both.txt").write_text("before")
            (right / "new.txt").write_text("new")
            (right / "both.txt").write_text("after")
            report = compare_views(load_source(left), load_source(right))
            self.assertEqual(report.summary["modified"], 1)
            self.assertEqual(report.summary["added"], 1)
            self.assertEqual(report.summary["removed"], 1)

    def test_detects_rename_by_content_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "left"
            right = root / "right"
            left.mkdir()
            right.mkdir()
            (left / "old.txt").write_text("same content")
            (right / "new.txt").write_text("same content")
            report = compare_views(load_source(left), load_source(right))
            self.assertEqual(report.summary["renamed"], 1)
            self.assertEqual(report.changes[0].previous_path, "old.txt")

    def test_can_disable_rename_detection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "left"
            right = root / "right"
            left.mkdir()
            right.mkdir()
            (left / "old.txt").write_text("same")
            (right / "new.txt").write_text("same")
            report = compare_views(
                load_source(left),
                load_source(right),
                options=CompareOptions(detect_renames=False),
            )
            self.assertEqual(report.summary["renamed"], 0)
            self.assertEqual(report.summary["added"], 1)
            self.assertEqual(report.summary["removed"], 1)

    def test_single_files_with_different_names_are_compared(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "a.json"
            right = root / "b.json"
            left.write_text('{"gold": 1}')
            right.write_text('{"gold": 2}')
            report = compare_views(load_source(left), load_source(right))
            self.assertEqual(report.summary["modified"], 1)
            self.assertEqual(report.changes[0].format, "json")

    def test_size_limit_uses_metadata_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = root / "left.bin"
            right = root / "right.bin"
            left.write_bytes(b"a" * 20)
            right.write_bytes(b"b" * 20)
            report = compare_views(
                load_source(left),
                load_source(right),
                options=CompareOptions(max_file_bytes=10),
            )
            self.assertEqual(report.changes[0].format, "metadata")
            self.assertTrue(report.changes[0].warnings)


if __name__ == "__main__":
    unittest.main()
