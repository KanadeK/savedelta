#!/usr/bin/env python3
"""Build the zero-dependency single-file SaveDelta zipapp."""

from __future__ import annotations

import shutil
import tempfile
import zipapp
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "dist" / "savedelta.pyz"


def main() -> int:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="savedelta-zipapp-") as temporary:
        staging = Path(temporary)
        shutil.copytree(
            ROOT / "src" / "savedelta",
            staging / "savedelta",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        zipapp.create_archive(
            staging,
            target=TARGET,
            interpreter="/usr/bin/env python3",
            main="savedelta.cli:main",
            compressed=True,
        )
    print(f"Built {TARGET.relative_to(ROOT)} ({TARGET.stat().st_size} bytes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
