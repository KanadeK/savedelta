#!/usr/bin/env python3
"""Exercise the public CLI as a user would, without test-only helpers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    source_path = str(ROOT / "src")
    environment["PYTHONPATH"] = (
        source_path
        + os.pathsep
        + environment.get("PYTHONPATH", "")
    ).rstrip(os.pathsep)
    result = subprocess.run(
        [sys.executable, "-m", "savedelta", *arguments],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != expected:
        raise RuntimeError(
            f"command failed ({result.returncode}, expected {expected}): "
            f"{' '.join(arguments)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="savedelta-smoke-") as temporary:
        root = Path(temporary)
        demo = root / "demo"
        payload = json.loads(run("demo", str(demo), "--json").stdout)
        report = json.loads((demo / "report.json").read_text(encoding="utf-8"))

        assert payload["summary"]["changed"] == 8
        assert report["summary"] == {
            "files_before": 7,
            "files_after": 7,
            "changed": 8,
            "modified": 5,
            "added": 1,
            "removed": 1,
            "renamed": 1,
            "unchanged": 0,
        }
        kinds = {item["format"] for item in report["changes"]}
        assert {"binary", "ini", "json", "sqlite", "zip"} <= kinds
        assert report["expectations"][0]["match_count"] >= 2

        html = (demo / "report.html").read_text(encoding="utf-8")
        assert "Content-Security-Policy" in html
        assert "<script" not in html.lower()
        assert "100" in html and "250" in html

        direct_json = json.loads(
            run(
                "diff",
                str(demo / "before"),
                str(demo / "after"),
                "--expect",
                "100:250",
                "--format",
                "json",
            ).stdout
        )
        assert direct_json["summary"]["changed"] == 8

        run(
            "diff",
            str(demo / "before.sdelta"),
            str(demo / "after.sdelta"),
            "--fail-on-change",
            expected=1,
        )
        inspection = json.loads(
            run(
                "inspect",
                str(demo / "before" / "world.db"),
                "--format",
                "json",
            ).stdout
        )
        assert inspection["format"] == "sqlite"
        assert inspection["sqlite"]["objects"]

    print("Smoke test passed: demo, snapshots, reports, policy exit, and inspect.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
