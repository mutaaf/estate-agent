"""Terminal output.

The plan calls for output a non-expert can read: a short checklist with green
and red, not a log. Everything here exists to keep that promise, including
degrading to plain ASCII when colour would be noise (pipes, CI, NO_COLOR).
"""

from __future__ import annotations

import os
import shutil
import sys

_FORCE = os.environ.get("ESTATE_COLOR") == "always"


def _colour_ok() -> bool:
    if _FORCE:
        return True
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return sys.stdout.isatty()


COLOUR = _colour_ok()

_CODES = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
    "green": "\033[32m", "red": "\033[31m", "yellow": "\033[33m",
    "blue": "\033[34m", "grey": "\033[90m",
}


def paint(text: str, *styles: str) -> str:
    if not COLOUR or not styles:
        return text
    prefix = "".join(_CODES.get(s, "") for s in styles)
    return f"{prefix}{text}{_CODES['reset']}"


def width() -> int:
    return min(shutil.get_terminal_size((80, 24)).columns, 100)


# -- structured output ------------------------------------------------------

PASS = "pass"
FAIL = "fail"
WARN = "warn"
INFO = "info"

_MARKS = {
    PASS: ("ok  ", "green"),
    FAIL: ("FAIL", "red"),
    WARN: ("warn", "yellow"),
    INFO: ("    ", "grey"),
}


def title(text: str) -> None:
    print()
    print(paint(text, "bold"))
    print(paint("-" * min(len(text), width()), "grey"))


def item(status: str, text: str, detail: str = "") -> None:
    mark, colour = _MARKS.get(status, _MARKS[INFO])
    print(f"  {paint(mark, colour)}  {text}")
    if detail:
        for line in detail.strip().splitlines():
            print(f"        {paint(line, 'grey')}")


def note(text: str) -> None:
    print(f"  {paint(text, 'grey')}")


def say(text: str = "") -> None:
    print(text)


def error(text: str) -> None:
    print(paint(f"error: {text}", "red"), file=sys.stderr)


def summary(passed: int, failed: int, warned: int = 0) -> None:
    print()
    bits = [paint(f"{passed} ok", "green")]
    if warned:
        bits.append(paint(f"{warned} warning{'s' if warned != 1 else ''}", "yellow"))
    if failed:
        bits.append(paint(f"{failed} problem{'s' if failed != 1 else ''}", "red"))
    print("  " + paint(" · ", "grey").join(bits))
    print()


def next_step(text: str) -> None:
    """Every command ends by telling you what to do next."""
    print(f"  {paint('next:', 'bold')} {text}")
    print()
