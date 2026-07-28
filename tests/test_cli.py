from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from savedelta.cli import main


class CliTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(list(arguments))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_demo_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "demo"
            code, stdout, stderr = self.run_cli("demo", str(destination))
            self.assertEqual(code, 0, stderr)
            self.assertIn("Demo complete", stdout)
            self.assertTrue((destination / "report.html").is_file())
            payload = json.loads((destination / "report.json").read_text())
            self.assertEqual(payload["summary"]["changed"], 8)

    def test_demo_force_only_replaces_savedelta_demo(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "important"
            destination.mkdir()
            evidence = destination / "keep.txt"
            evidence.write_text("keep me")
            code, _, stderr = self.run_cli(
                "demo",
                str(destination),
                "--force",
            )
            self.assertEqual(code, 2)
            self.assertIn("refusing to replace unmarked directory", stderr)
            self.assertEqual(evidence.read_text(), "keep me")

    def test_demo_force_can_refresh_its_own_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "demo"
            first_code, _, first_error = self.run_cli(
                "demo",
                str(destination),
            )
            second_code, _, second_error = self.run_cli(
                "demo",
                str(destination),
                "--force",
            )
            self.assertEqual(first_code, 0, first_error)
            self.assertEqual(second_code, 0, second_error)
            self.assertTrue((destination / "report.html").is_file())

    def test_snapshot_and_json_diff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = root / "before"
            after = root / "after"
            before.mkdir()
            after.mkdir()
            (before / "state.json").write_text('{"gold":100}')
            (after / "state.json").write_text('{"gold":250}')
            before_snapshot = root / "before.sdelta"
            after_snapshot = root / "after.sdelta"
            for source, output in (
                (before, before_snapshot),
                (after, after_snapshot),
            ):
                code, _, stderr = self.run_cli(
                    "snapshot",
                    str(source),
                    "-o",
                    str(output),
                )
                self.assertEqual(code, 0, stderr)
            code, stdout, stderr = self.run_cli(
                "diff",
                str(before_snapshot),
                str(after_snapshot),
                "--format",
                "json",
                "--expect",
                "100:250",
            )
            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["expectations"][0]["match_count"], 1)

    def test_fail_on_change_returns_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = root / "before.txt"
            after = root / "after.txt"
            before.write_text("before")
            after.write_text("after")
            code, _, _ = self.run_cli(
                "diff",
                str(before),
                str(after),
                "--fail-on-change",
            )
            self.assertEqual(code, 1)

    def test_identical_with_fail_on_change_returns_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "same.txt"
            path.write_text("same")
            code, _, _ = self.run_cli(
                "diff",
                str(path),
                str(path),
                "--fail-on-change",
            )
            self.assertEqual(code, 0)

    def test_inspect_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.json"
            path.write_text('{"value":1}')
            code, stdout, stderr = self.run_cli(
                "inspect",
                str(path),
                "--format",
                "json",
            )
            self.assertEqual(code, 0, stderr)
            self.assertEqual(json.loads(stdout)["format"], "json")

    def test_missing_input_returns_two(self) -> None:
        code, _, stderr = self.run_cli("inspect", "/definitely/missing")
        self.assertEqual(code, 2)
        self.assertIn("error", stderr)

    def test_html_diff_gets_default_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = root / "a.txt"
            after = root / "b.txt"
            output = root / "report.html"
            before.write_text("a")
            after.write_text("b")
            code, stdout, stderr = self.run_cli(
                "diff",
                str(before),
                str(after),
                "--format",
                "html",
                "--output",
                str(output),
            )
            self.assertEqual(code, 0, stderr)
            self.assertTrue(output.is_file())
            self.assertIn("Wrote HTML report", stdout)


if __name__ == "__main__":
    unittest.main()
