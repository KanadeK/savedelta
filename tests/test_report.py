from __future__ import annotations

import json
import unittest

from savedelta.models import DeltaReport, FileChange
from savedelta.report import render_html, render_json, render_text


def sample_report(path: str = "player.json") -> DeltaReport:
    change = FileChange(
        path=path,
        status="modified",
        format="json",
        before_size=10,
        after_size=11,
        before_sha256="a" * 64,
        after_sha256="b" * 64,
        summary="1 structured value change",
        details={
            "kind": "json",
            "change_count": 1,
            "truncated": False,
            "changes": [
                {
                    "path": "$.gold",
                    "kind": "changed",
                    "before": 100,
                    "after": 250,
                }
            ],
            "expectation_matches": [],
        },
    )
    return DeltaReport(
        schema_version="1.0",
        tool_version="0.1.0",
        generated_at="2026-07-28T00:00:00+00:00",
        before="before",
        after="after",
        summary={
            "files_before": 1,
            "files_after": 1,
            "changed": 1,
            "modified": 1,
            "added": 0,
            "removed": 0,
            "renamed": 0,
            "unchanged": 0,
        },
        changes=[change],
    )


class ReportTests(unittest.TestCase):
    def test_json_is_machine_readable(self) -> None:
        payload = json.loads(render_json(sample_report()))
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["changes"][0]["details"]["changes"][0]["after"], 250)

    def test_text_contains_summary_and_path(self) -> None:
        rendered = render_text(sample_report())
        self.assertIn("1 changed", rendered)
        self.assertIn("$.gold", rendered)

    def test_html_escapes_input_path(self) -> None:
        rendered = render_html(sample_report('<img src=x onerror="boom">'))
        self.assertNotIn('<img src=x onerror="boom">', rendered)
        self.assertIn("&lt;img", rendered)

    def test_html_has_restrictive_csp_and_no_script(self) -> None:
        rendered = render_html(sample_report())
        self.assertIn("Content-Security-Policy", rendered)
        self.assertNotIn("<script", rendered.lower())

    def test_html_is_self_contained(self) -> None:
        rendered = render_html(sample_report())
        self.assertNotIn('src="http', rendered)
        self.assertNotIn('href="http', rendered)


if __name__ == "__main__":
    unittest.main()
