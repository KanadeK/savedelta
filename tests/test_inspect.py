from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from savedelta.errors import WorkLimitError
from savedelta.inspect import inspect_file


class InspectTests(unittest.TestCase):
    def test_json_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "player.json"
            path.write_text(json.dumps({"gold": 100, "name": "Aster"}))
            result = inspect_file(path)
            self.assertEqual(result["format"], "json")
            self.assertEqual(result["json"]["top_level_keys"], ["gold", "name"])

    def test_sqlite_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "save.db"
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE state(key TEXT PRIMARY KEY, value TEXT)")
            connection.commit()
            connection.close()
            result = inspect_file(path)
            self.assertEqual(result["format"], "sqlite")
            self.assertTrue(
                any(item["name"] == "state" for item in result["sqlite"]["objects"])
            )

    def test_zip_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "save.zip"
            with zipfile.ZipFile(path, "w") as bundle:
                bundle.writestr("meta.json", "{}")
            result = inspect_file(path)
            self.assertEqual(result["zip"]["entry_count"], 1)

    def test_binary_strings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "save.bin"
            path.write_bytes(b"\x00\x01PLAYER_NAME\x00")
            result = inspect_file(path)
            self.assertEqual(result["format"], "binary")
            self.assertEqual(result["strings"][0]["text"], "PLAYER_NAME")

    def test_size_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "large.bin"
            path.write_bytes(b"x" * 20)
            with self.assertRaises(WorkLimitError):
                inspect_file(path, max_file_bytes=10)


if __name__ == "__main__":
    unittest.main()
