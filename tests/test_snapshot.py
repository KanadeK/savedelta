from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from savedelta.errors import SnapshotFormatError
from savedelta.snapshot import create_snapshot
from savedelta.source import load_source, load_snapshot


class SnapshotTests(unittest.TestCase):
    def test_round_trip_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "state"
            source.mkdir()
            (source / "player.json").write_text('{"gold": 100}\n')
            (source / "nested").mkdir()
            (source / "nested" / "save.dat").write_bytes(b"\x00\x01")
            output, stats = create_snapshot(source, root / "before.sdelta")
            loaded = load_source(output)
            self.assertEqual(set(loaded.entries), {"player.json", "nested/save.dat"})
            self.assertEqual(loaded.entries["nested/save.dat"].read_bytes(), b"\x00\x01")
            self.assertEqual(stats["files"], 2)

    def test_single_file_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "save.bin"
            source.write_bytes(b"save")
            output, _ = create_snapshot(source, root / "save.sdelta")
            loaded = load_snapshot(output)
            self.assertTrue(loaded.single_file)
            self.assertEqual(loaded.entries["save.bin"].read_bytes(), b"save")

    def test_default_ignore_excludes_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "state"
            source.mkdir()
            (source / "live.lock").write_text("volatile")
            (source / "save.dat").write_text("stable")
            output, _ = create_snapshot(source, root / "state.sdelta")
            loaded = load_snapshot(output)
            self.assertEqual(set(loaded.entries), {"save.dat"})

    def test_snapshot_members_do_not_use_user_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "state"
            source.mkdir()
            (source / "private-name.txt").write_text("data")
            output, _ = create_snapshot(source, root / "state.sdelta")
            with zipfile.ZipFile(output) as bundle:
                names = bundle.namelist()
            self.assertNotIn("private-name.txt", names)
            self.assertIn("data/00000001.bin", names)

    def test_output_inside_source_is_not_captured(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            (source / "save.dat").write_bytes(b"data")
            output, _ = create_snapshot(source, source / "inside.sdelta")
            loaded = load_snapshot(output)
            self.assertNotIn("inside.sdelta", loaded.entries)

    def test_rejects_parent_traversal_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "bad.sdelta"
            manifest = {
                "format": "savedelta-snapshot",
                "format_version": 1,
                "entries": [
                    {
                        "path": "../escape",
                        "member": "data/00000001.bin",
                        "size": 1,
                        "sha256": "0" * 64,
                    }
                ],
            }
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("manifest.json", json.dumps(manifest))
                bundle.writestr("data/00000001.bin", b"x")
            with self.assertRaises(SnapshotFormatError):
                load_snapshot(archive)

    def test_rejects_wrong_format_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "bad.sdelta"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr(
                    "manifest.json",
                    json.dumps(
                        {
                            "format": "savedelta-snapshot",
                            "format_version": 99,
                            "entries": [],
                        }
                    ),
                )
            with self.assertRaises(SnapshotFormatError):
                load_snapshot(archive)

    def test_rejects_forged_member_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "forged.sdelta"
            manifest = {
                "format": "savedelta-snapshot",
                "format_version": 1,
                "warnings": [],
                "entries": [
                    {
                        "path": "save.dat",
                        "member": "data/00000001.bin",
                        "size": 4,
                        "sha256": "0" * 64,
                    }
                ],
            }
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("manifest.json", json.dumps(manifest))
                bundle.writestr("data/00000001.bin", b"save")
            with self.assertRaisesRegex(
                SnapshotFormatError,
                "digest mismatch",
            ):
                load_snapshot(archive)


if __name__ == "__main__":
    unittest.main()
