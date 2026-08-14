#!/usr/bin/env python3
"""Tests for the zero-dependency YAML subset reader/writer.

This parser reads the files that tell an AI agent what it may do, so a wrong
value here is a safety problem, not a formatting problem. Round-tripping is
checked as well as parsing.

Run:  python3 tests/test_yamlite.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from estate_agent import yamlite  # noqa: E402


class Scalars(unittest.TestCase):
    def test_types(self) -> None:
        data = yamlite.load(
            "name: payments-api\n"
            "port: 8080\n"
            "ratio: 0.75\n"
            "enabled: true\n"
            "disabled: false\n"
            "missing: null\n"
            "empty:\n"
            "quoted: \"has: a colon\"\n"
            "single: 'keeps # hash'\n"
        )
        self.assertEqual("payments-api", data["name"])
        self.assertEqual(8080, data["port"])
        self.assertEqual(0.75, data["ratio"])
        self.assertIs(True, data["enabled"])
        self.assertIs(False, data["disabled"])
        self.assertIsNone(data["missing"])
        self.assertIsNone(data["empty"])
        self.assertEqual("has: a colon", data["quoted"])
        self.assertEqual("keeps # hash", data["single"])

    def test_comments_are_ignored(self) -> None:
        data = yamlite.load(
            "# leading comment\n"
            "name: api   # trailing comment\n"
            "\n"
            "  # indented comment\n"
            "tier: 2\n"
        )
        self.assertEqual({"name": "api", "tier": 2}, data)

    def test_hash_inside_quotes_is_kept(self) -> None:
        data = yamlite.load('cmd: "grep # in a file"\n')
        self.assertEqual("grep # in a file", data["cmd"])

    def test_command_strings_survive(self) -> None:
        """Build commands are the most common scalar in a deed."""
        data = yamlite.load(
            "build: ./gradlew clean build -x test\n"
            "test: mvn -q verify\n"
            "lint: npx eslint . --max-warnings 0\n"
        )
        self.assertEqual("./gradlew clean build -x test", data["build"])
        self.assertEqual("mvn -q verify", data["test"])
        self.assertEqual("npx eslint . --max-warnings 0", data["lint"])


class Collections(unittest.TestCase):
    def test_nested_maps(self) -> None:
        data = yamlite.load(
            "repo:\n"
            "  name: payments-api\n"
            "  stack:\n"
            "    language: java\n"
            "    build: maven\n"
            "tier: 1\n"
        )
        self.assertEqual("java", data["repo"]["stack"]["language"])
        self.assertEqual(1, data["tier"])

    def test_scalar_lists(self) -> None:
        data = yamlite.load(
            "never_do:\n"
            "  - modify RPG source\n"
            "  - commit to main directly\n"
        )
        self.assertEqual(
            ["modify RPG source", "commit to main directly"], data["never_do"]
        )

    def test_list_at_same_indent_as_key(self) -> None:
        data = yamlite.load("owners:\n- platform-team\n- payments-team\n")
        self.assertEqual(["platform-team", "payments-team"], data["owners"])

    def test_inline_list(self) -> None:
        data = yamlite.load("tags: [java, backend, tier1]\n")
        self.assertEqual(["java", "backend", "tier1"], data["tags"])
        self.assertEqual([], yamlite.load("tags: []\n")["tags"])

    def test_list_of_maps(self) -> None:
        data = yamlite.load(
            "consumes:\n"
            "  - service: payments-api\n"
            "    via: rest\n"
            "    endpoints:\n"
            "      - /v2/charge\n"
            "      - /v2/refund\n"
            "  - service: ledger\n"
            "    via: grpc\n"
        )
        self.assertEqual(2, len(data["consumes"]))
        self.assertEqual("payments-api", data["consumes"][0]["service"])
        self.assertEqual(
            ["/v2/charge", "/v2/refund"], data["consumes"][0]["endpoints"]
        )
        self.assertEqual("grpc", data["consumes"][1]["via"])

    def test_deeply_nested_list_of_maps(self) -> None:
        data = yamlite.load(
            "estate:\n"
            "  services:\n"
            "    - name: a\n"
            "      calls:\n"
            "        - name: b\n"
            "          via: rest\n"
        )
        call = data["estate"]["services"][0]["calls"][0]
        self.assertEqual({"name": "b", "via": "rest"}, call)


class BlockScalars(unittest.TestCase):
    def test_literal_block_keeps_newlines(self) -> None:
        data = yamlite.load(
            "summary: |\n"
            "  Handles card payments.\n"
            "  Talks to the ledger over gRPC.\n"
            "tier: 1\n"
        )
        self.assertEqual(
            "Handles card payments.\nTalks to the ledger over gRPC.\n",
            data["summary"],
        )
        self.assertEqual(1, data["tier"])

    def test_folded_block_joins_lines(self) -> None:
        data = yamlite.load(
            "summary: >\n"
            "  one sentence split\n"
            "  across two lines\n"
        )
        self.assertEqual("one sentence split across two lines\n", data["summary"])

    def test_strip_chomping(self) -> None:
        data = yamlite.load("note: |-\n  no trailing newline\n")
        self.assertEqual("no trailing newline", data["note"])

    def test_block_preserves_relative_indent(self) -> None:
        data = yamlite.load(
            "steps: |\n"
            "  first\n"
            "    indented under first\n"
            "  second\n"
        )
        self.assertEqual("first\n  indented under first\nsecond\n", data["steps"])


class Errors(unittest.TestCase):
    def test_tabs_rejected_with_line_number(self) -> None:
        with self.assertRaises(yamlite.YamliteError) as ctx:
            yamlite.load("name: api\n\tbad: value\n")
        self.assertEqual(2, ctx.exception.line_no)

    def test_inline_map_rejected_clearly(self) -> None:
        with self.assertRaises(yamlite.YamliteError) as ctx:
            yamlite.load("stack: {language: java}\n")
        self.assertIn("inline maps are not supported", str(ctx.exception))

    def test_garbage_line_reports_position(self) -> None:
        with self.assertRaises(yamlite.YamliteError) as ctx:
            yamlite.load("name: api\nthis is not yaml\n")
        self.assertEqual(2, ctx.exception.line_no)

    def test_empty_document(self) -> None:
        self.assertIsNone(yamlite.load(""))
        self.assertIsNone(yamlite.load("# only a comment\n"))


class RoundTrip(unittest.TestCase):
    """`estate init` writes deeds and `estate upkeep` rewrites them, so a
    value must survive a load/dump/load cycle unchanged."""

    CASES = [
        {"name": "payments-api", "tier": 1, "enabled": True},
        {"stack": {"language": "java", "build": "./gradlew build"}},
        {"never_do": ["modify RPG", "push to main"]},
        {"consumes": [
            {"service": "ledger", "via": "grpc"},
            {"service": "notify", "via": "rest", "endpoints": ["/v1/send"]},
        ]},
        {"summary": "Line one.\nLine two.\n", "tier": 3},
        {"tags": [], "owners": ["a"], "note": None},
        {"cmd": "grep -r 'x: y' .", "weird": "value: with colon"},
    ]

    def test_round_trips(self) -> None:
        for original in self.CASES:
            with self.subTest(original=original):
                text = yamlite.dump(original)
                reparsed = yamlite.load(text)
                self.assertEqual(
                    original, reparsed,
                    f"round trip changed the value.\n--- dumped ---\n{text}",
                )

    def test_dump_is_stable(self) -> None:
        """Dumping twice produces identical bytes, so `check` does not report
        phantom drift."""
        for original in self.CASES:
            once = yamlite.dump(original)
            twice = yamlite.dump(yamlite.load(once))
            self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main(verbosity=2)
