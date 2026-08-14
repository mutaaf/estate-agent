#!/usr/bin/env python3
"""Estate Agent must run on the Python a work laptop already has.

The floor is 3.9. That is not arbitrary: the whole point of having no
dependencies is that you can use this on a machine where you cannot install
anything, and on such a machine you get whatever Python is already there.

`ast.parse(..., feature_version=(3, 9))` does not catch everything - f-string
quote nesting changed in the tokenizer (PEP 701), not the grammar, so it parses
happily on 3.12 and fails on 3.9. This scans for the constructs that slip past.

Run:  python3 tests/test_python_compat.py
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNED = ["src", "hooks", "site", "tests"]
FLOOR = (3, 9)


def python_files() -> list[Path]:
    files: list[Path] = []
    for directory in SCANNED:
        base = ROOT / directory
        if base.exists():
            files.extend(sorted(base.rglob("*.py")))
    return files


class RunsOnTheFloorVersion(unittest.TestCase):
    def test_grammar_is_supported(self) -> None:
        """Catches match statements, PEP 604 in runtime positions, and so on."""
        offences: list[str] = []
        for path in python_files():
            source = path.read_text(encoding="utf-8")
            try:
                ast.parse(source, filename=str(path), feature_version=FLOOR)
            except SyntaxError as exc:
                offences.append(
                    f"{path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}"
                )
        self.assertEqual([], offences, "syntax newer than Python 3.9:\n  "
                         + "\n  ".join(offences))

    def test_no_nested_or_same_quote_fstrings(self) -> None:
        """PEP 701 relaxed f-string quoting in 3.12. Before that, reusing the
        outer quote inside an f-string expression is a SyntaxError - and it
        parses fine on a modern laptop, so only CI finds it."""
        patterns = [
            (re.compile(r'f"[^"\n]*f\''), "an f-string nested in an f-string"),
            (re.compile(r"f'[^'\n]*f\""), "an f-string nested in an f-string"),
            (re.compile(r'f"[^"\n]*\{[^}\n]*\["'), "a same-quote subscript"),
            (re.compile(r"f'[^'\n]*\{[^}\n]*\['"), "a same-quote subscript"),
        ]
        offences: list[str] = []
        for path in python_files():
            if path.name == "test_python_compat.py":
                continue  # This file necessarily contains the patterns.
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                for pattern, description in patterns:
                    if pattern.search(line):
                        offences.append(
                            f"{path.relative_to(ROOT)}:{number} has {description}"
                        )
        self.assertEqual(
            [], offences,
            "f-string syntax that needs Python 3.12:\n  " + "\n  ".join(offences),
        )

    def test_modern_annotations_are_postponed(self) -> None:
        """`str | None` in an annotation is fine on 3.9 only when annotations
        are postponed. Every module here uses them, so every module needs the
        future import."""
        offences: list[str] = []
        for path in python_files():
            source = path.read_text(encoding="utf-8")
            uses_union = re.search(r":\s*[\w.\[\]]+\s*\|\s*[\w.\[\]]+", source)
            uses_builtin_generic = re.search(
                r":\s*(list|dict|set|tuple|frozenset)\[", source
            )
            if not (uses_union or uses_builtin_generic):
                continue
            if "from __future__ import annotations" not in source:
                offences.append(str(path.relative_to(ROOT)))
        self.assertEqual(
            [], offences,
            "these use modern annotation syntax without postponing "
            "evaluation, which breaks on 3.9:\n  " + "\n  ".join(offences),
        )

    def test_the_launcher_enforces_the_same_floor(self) -> None:
        launcher = (ROOT / "bin" / "estate").read_text(encoding="utf-8")
        self.assertIn(
            f"({FLOOR[0]}, {FLOOR[1]})", launcher,
            "bin/estate must refuse to run on anything below the floor, "
            "rather than failing later with a confusing SyntaxError",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
