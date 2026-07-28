from __future__ import annotations

import io
import json
import unittest
import zipfile

from savedelta.errors import WorkLimitError
from savedelta.zipdiff import analyze_zip


def make_zip(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, data in files.items():
            bundle.writestr(name, data)
    return output.getvalue()


class ZipAnalysisTests(unittest.TestCase):
    def test_add_remove_and_modify(self) -> None:
        before = make_zip({"same.txt": b"x", "old.txt": b"old", "meta.json": b'{"x":1}'})
        after = make_zip({"same.txt": b"x", "new.txt": b"new", "meta.json": b'{"x":2}'})
        result = analyze_zip(before, after)
        statuses = {item["status"] for item in result["changes"]}
        self.assertEqual(statuses, {"added", "removed", "modified"})

    def test_deep_analyzes_json_member(self) -> None:
        before = make_zip({"meta.json": json.dumps({"gold": 100}).encode()})
        after = make_zip({"meta.json": json.dumps({"gold": 250}).encode()})
        result = analyze_zip(
            before,
            after,
            expectations=((100, 250),),
        )
        analysis = result["changes"][0]["analysis"]
        self.assertEqual(analysis["kind"], "json")
        self.assertEqual(
            analysis["expectation_matches"][0]["path"],
            "$.gold",
        )

    def test_entry_limit_is_enforced(self) -> None:
        archive = make_zip({"a": b"a", "b": b"b"})
        with self.assertRaises(WorkLimitError):
            analyze_zip(archive, archive, max_entries=1)

    def test_expanded_byte_budget_is_enforced(self) -> None:
        archive = make_zip({"large": b"x" * 100})
        with self.assertRaises(WorkLimitError):
            analyze_zip(archive, archive, max_expanded_bytes=50)


if __name__ == "__main__":
    unittest.main()
