from __future__ import annotations

import configparser
import json
import shutil
import sqlite3
import struct
import zipfile
from pathlib import Path
from typing import Any

from .compare import CompareOptions, compare_views
from .report import write_report
from .snapshot import create_snapshot
from .source import load_source


DEMO_MARKER = ".savedelta-demo.json"


def _binary_save(*, health: int, gold: int, level: int, difficulty: int) -> bytes:
    data = bytearray(160)
    data[0:9] = b"SAVEDEMO\x01"
    data[16:22] = b"PLAYER"
    struct.pack_into("<I", data, 32, health)
    struct.pack_into("<I", data, 36, gold)
    struct.pack_into("<H", data, 40, level)
    struct.pack_into("<B", data, 42, difficulty)
    struct.pack_into("<f", data, 64, 1234.5)
    data[80:96] = bytes(range(16))
    return bytes(data)


def _write_ini(path: Path, *, difficulty: str, subtitles: bool) -> None:
    parser = configparser.ConfigParser()
    parser["video"] = {"fullscreen": "true", "quality": "high"}
    parser["gameplay"] = {
        "difficulty": difficulty,
        "subtitles": str(subtitles).lower(),
    }
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        parser.write(stream)


def _write_database(path: Path, *, upgraded: bool) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE inventory (
                id INTEGER PRIMARY KEY,
                item TEXT NOT NULL,
                quantity INTEGER NOT NULL
            );
            CREATE TABLE flags (
                name TEXT PRIMARY KEY,
                value INTEGER NOT NULL
            );
            """
        )
        connection.executemany(
            "INSERT INTO inventory(id, item, quantity) VALUES (?, ?, ?)",
            [
                (1, "potion", 3 if not upgraded else 2),
                (2, "iron_key", 1),
                *(([(3, "moon_shard", 1)]) if upgraded else []),
            ],
        )
        connection.executemany(
            "INSERT INTO flags(name, value) VALUES (?, ?)",
            [
                ("opened_gate", 0 if not upgraded else 1),
                ("met_archivist", 1),
            ],
        )
        connection.commit()
    finally:
        connection.close()


def _write_bundle(path: Path, *, stage: int) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(
            "meta.json",
            json.dumps(
                {"chapter": stage, "weather": "rain" if stage == 1 else "clear"},
                indent=2,
            )
            + "\n",
        )
        bundle.writestr("notes/readme.txt", f"Checkpoint stage {stage}\n")


def create_demo(
    destination: str | Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    root = Path(destination).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        if not force:
            raise FileExistsError(
                f"demo destination is not empty: {root}; use --force to replace it"
            )
        marker = root / DEMO_MARKER
        try:
            marker_payload = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"refusing to replace unmarked directory: {root}; "
                "choose an empty destination"
            ) from exc
        if marker_payload.get("format") != "savedelta-demo":
            raise ValueError(
                f"refusing to replace unrecognized demo directory: {root}"
            )
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / DEMO_MARKER).write_text(
        json.dumps({"format": "savedelta-demo", "version": 1}, indent=2) + "\n",
        encoding="utf-8",
    )
    before = root / "before"
    after = root / "after"
    before.mkdir()
    after.mkdir()

    before_player = {
        "player": {
            "name": "Aster",
            "health": 80,
            "gold": 100,
            "position": {"x": 14, "y": 8},
        },
        "quests": ["arrival"],
    }
    after_player = {
        "player": {
            "name": "Aster",
            "health": 65,
            "gold": 250,
            "position": {"x": 19, "y": 11},
        },
        "quests": ["arrival", "opened_gate"],
    }
    (before / "player.json").write_text(
        json.dumps(before_player, indent=2) + "\n",
        encoding="utf-8",
    )
    (after / "player.json").write_text(
        json.dumps(after_player, indent=2) + "\n",
        encoding="utf-8",
    )
    (before / "save.dat").write_bytes(
        _binary_save(health=80, gold=100, level=4, difficulty=1)
    )
    (after / "save.dat").write_bytes(
        _binary_save(health=65, gold=250, level=5, difficulty=2)
    )
    _write_ini(before / "settings.ini", difficulty="normal", subtitles=True)
    _write_ini(after / "settings.ini", difficulty="hard", subtitles=True)
    _write_database(before / "world.db", upgraded=False)
    _write_database(after / "world.db", upgraded=True)
    _write_bundle(before / "checkpoint.zip", stage=1)
    _write_bundle(after / "checkpoint.zip", stage=2)
    (before / "old_notes.txt").write_text(
        "Meet the archivist below the eastern tower.\n",
        encoding="utf-8",
    )
    (after / "quest_notes.txt").write_text(
        "Meet the archivist below the eastern tower.\n",
        encoding="utf-8",
    )
    (before / "obsolete.cache").write_bytes(b"old cache marker\n")
    (after / "autosave.flag").write_text("ready\n", encoding="utf-8")

    before_snapshot, _ = create_snapshot(before, root / "before.sdelta")
    after_snapshot, _ = create_snapshot(after, root / "after.sdelta")
    report = compare_views(
        load_source(before_snapshot),
        load_source(after_snapshot),
        options=CompareOptions(expectations=((100, 250),)),
    )
    html_path = write_report(
        report,
        format_name="html",
        output=root / "report.html",
    )
    json_path = write_report(
        report,
        format_name="json",
        output=root / "report.json",
    )
    return {
        "root": str(root),
        "before": str(before),
        "after": str(after),
        "before_snapshot": str(before_snapshot),
        "after_snapshot": str(after_snapshot),
        "html_report": str(html_path),
        "json_report": str(json_path),
        "summary": report.summary,
    }
