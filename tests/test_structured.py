from __future__ import annotations

import json
import unittest

from savedelta.errors import AnalysisError
from savedelta.structured import (
    StructureOptions,
    analyze_structured,
    parse_structured,
    structural_diff,
)


class StructuredAnalysisTests(unittest.TestCase):
    def test_json_nested_changes(self) -> None:
        before = json.dumps({"player": {"gold": 100}, "quests": []}).encode()
        after = json.dumps(
            {"player": {"gold": 250}, "quests": ["gate"]}
        ).encode()
        result = analyze_structured(
            before,
            after,
            "json",
            expectations=((100, 250),),
        )
        paths = {item["path"] for item in result["changes"]}
        self.assertIn("$.player.gold", paths)
        self.assertIn("$.quests[0]", paths)
        self.assertEqual(
            result["expectation_matches"][0]["path"],
            "$.player.gold",
        )

    def test_type_change(self) -> None:
        changes, _ = structural_diff({"a": 1}, {"a": "1"})
        self.assertEqual(changes[0]["kind"], "type_changed")

    def test_removed_key(self) -> None:
        changes, _ = structural_diff({"a": 1}, {})
        self.assertEqual(changes[0], {"path": "$.a", "kind": "removed", "before": 1})

    def test_non_identifier_key_uses_brackets(self) -> None:
        changes, _ = structural_diff({"a-b": 1}, {"a-b": 2})
        self.assertEqual(changes[0]["path"], '$["a-b"]')

    def test_change_cap(self) -> None:
        before = {str(index): index for index in range(10)}
        after = {str(index): index + 1 for index in range(10)}
        changes, truncated = structural_diff(
            before,
            after,
            options=StructureOptions(max_changes=3),
        )
        self.assertEqual(len(changes), 3)
        self.assertTrue(truncated)

    def test_toml_parsing(self) -> None:
        parsed = parse_structured(b"[player]\ngold = 100\n", "toml")
        self.assertEqual(parsed["player"]["gold"], 100)

    def test_ini_preserves_option_case(self) -> None:
        parsed = parse_structured(b"[Save]\nPlayerGold = 100\n", "ini")
        self.assertEqual(parsed["Save"]["PlayerGold"], "100")

    def test_invalid_json_is_rejected(self) -> None:
        with self.assertRaises(AnalysisError):
            parse_structured(b"{broken", "json")


if __name__ == "__main__":
    unittest.main()
