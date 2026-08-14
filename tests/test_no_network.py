#!/usr/bin/env python3
"""Enforce the central claim of docs/data-flow.md: no network code exists.

This runs in CI. If someone adds a networking import to Estate Agent, the
build fails and the security page stops being a promise nobody checks.

Run:  python3 tests/test_no_network.py
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNED_DIRS = ["src", "hooks", "bin", "site"]

# Modules that can open a socket. If Estate Agent ever needs one of these,
# that is a design decision requiring a docs change, not a quiet import.
FORBIDDEN_IMPORTS = [
    "socket", "ssl", "urllib", "http.client", "httplib", "requests",
    "httpx", "aiohttp", "smtplib", "ftplib", "telnetlib", "xmlrpc",
    "webbrowser", "socketserver", "asyncio.open_connection",
]

IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.,\s]+))", re.MULTILINE
)

# Subprocess calls that would smuggle a request out through a shell.
SHELL_EGRESS_RE = re.compile(
    r"""(?x)
    (subprocess|os\.system|os\.popen|Popen|check_output|run)
    [^\n]{0,120}?
    \b(curl|wget|nc|ncat|telnet|ssh|scp|rsync|ftp)\b
    """
)


def python_files() -> list[Path]:
    found: list[Path] = []
    for directory in SCANNED_DIRS:
        base = ROOT / directory
        if not base.exists():
            continue
        found.extend(p for p in base.rglob("*.py"))
        found.extend(
            p for p in base.rglob("*")
            if p.is_file() and not p.suffix and p.read_bytes()[:2] == b"#!"
        )
    return sorted(set(found))


class NoNetworkCode(unittest.TestCase):
    def test_no_networking_imports(self) -> None:
        offences: list[str] = []
        for path in python_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in IMPORT_RE.finditer(text):
                modules = (match.group(1) or match.group(2) or "")
                for name in re.split(r"[,\s]+", modules):
                    name = name.strip()
                    if not name:
                        continue
                    root = name.split(".")[0]
                    if name in FORBIDDEN_IMPORTS or root in FORBIDDEN_IMPORTS:
                        line = text[: match.start()].count("\n") + 1
                        rel = path.relative_to(ROOT)
                        offences.append(f"{rel}:{line} imports {name}")
        self.assertEqual(
            [], offences,
            "Estate Agent claims to make no network calls. These imports "
            "contradict docs/data-flow.md:\n  " + "\n  ".join(offences),
        )

    def test_no_shell_egress(self) -> None:
        offences: list[str] = []
        for path in python_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            # Skip this file - it necessarily contains the pattern strings.
            if path.name == "test_no_network.py":
                continue
            for match in SHELL_EGRESS_RE.finditer(text):
                line = text[: match.start()].count("\n") + 1
                offences.append(f"{path.relative_to(ROOT)}:{line}")
        self.assertEqual(
            [], offences,
            "Network access smuggled through a subprocess:\n  "
            + "\n  ".join(offences),
        )

    def test_no_dependencies(self) -> None:
        """Zero dependencies is why the locked-down-laptop path works."""
        for name in ("requirements.txt", "Pipfile", "poetry.lock"):
            self.assertFalse(
                (ROOT / name).exists(),
                f"{name} exists - Estate Agent must stay dependency-free",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
