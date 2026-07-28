from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from savedelta.compare import compare_views
from savedelta.sqlitediff import analyze_sqlite
from savedelta.source import load_source


def make_database(path: Path, *, version: int) -> bytes:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE inventory(id INTEGER PRIMARY KEY, item TEXT, quantity INTEGER)"
        )
        connection.executemany(
            "INSERT INTO inventory VALUES (?, ?, ?)",
            [
                (1, "potion", 3 if version == 1 else 2),
                (2, "key", 1),
            ],
        )
        if version == 2:
            connection.execute("INSERT INTO inventory VALUES (3, 'map', 1)")
            connection.execute("CREATE INDEX idx_item ON inventory(item)")
        connection.commit()
    finally:
        connection.close()
    return path.read_bytes()


class SQLiteAnalysisTests(unittest.TestCase):
    def test_detects_rows_and_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = make_database(root / "before.db", version=1)
            after = make_database(root / "after.db", version=2)
            result = analyze_sqlite(before, after)
            self.assertEqual(result["table_change_count"], 1)
            self.assertEqual(result["schema_change_count"], 1)
            table = result["table_changes"][0]
            self.assertEqual(table["rows_before"], 2)
            self.assertEqual(table["rows_after"], 3)
            self.assertTrue(
                any(row["kind"] == "changed" for row in table["row_changes"])
            )
            self.assertTrue(
                any(row["kind"] == "added" for row in table["row_changes"])
            )

    def test_row_scan_limit_is_respected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = make_database(root / "before.db", version=1)
            after = make_database(root / "after.db", version=2)
            result = analyze_sqlite(before, after, max_rows_per_table=1)
            table = result["table_changes"][0]
            self.assertFalse(table["rows_scanned"])
            self.assertIsNone(table["row_change_count"])

    def test_compare_dispatches_sqlite_analyzer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = root / "before.db"
            after = root / "after.db"
            make_database(before, version=1)
            make_database(after, version=2)
            report = compare_views(load_source(before), load_source(after))
            self.assertEqual(report.changes[0].format, "sqlite")
            self.assertEqual(report.changes[0].details["kind"], "sqlite")

    def test_table_without_primary_key_uses_rowid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [root / "a.db", root / "b.db"]
            for index, path in enumerate(paths):
                connection = sqlite3.connect(path)
                connection.execute("CREATE TABLE notes(text TEXT)")
                connection.execute("INSERT INTO notes VALUES (?)", ("a" if index == 0 else "b",))
                connection.commit()
                connection.close()
            result = analyze_sqlite(paths[0].read_bytes(), paths[1].read_bytes())
            self.assertEqual(
                result["table_changes"][0]["key_mode_after"],
                "rowid",
            )


if __name__ == "__main__":
    unittest.main()
