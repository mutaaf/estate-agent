"""A small YAML reader and writer, standard library only.

Estate Agent has no dependencies on purpose: that is what makes it installable
on a locked-down work laptop, and what makes `docs/data-flow.md` short enough
for anyone to verify. PyYAML is not available, so this module implements the
subset of YAML that deeds and stack profiles actually use:

    key: value                  scalars: string, int, float, true/false, null
    nested:                     maps, by indentation
      key: value
    list:                       lists of scalars
      - one
      - two
    people:                     lists of maps
      - name: ada
        role: engineer
    inline: [a, b, c]           flow sequences of scalars
    text: |                     literal block scalar (newlines kept)
      line one
      line two
    folded: >                   folded block scalar (newlines become spaces)
      a long sentence split
      across lines

Anything outside that subset raises `YamliteError` with a line number, rather
than being silently misread. A confusing parse error beats a wrong value in a
file that tells an AI agent what it is allowed to do.

If PyYAML happens to be installed, `load` uses it instead - same subset, more
battle-tested parser. Nothing requires it.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["load", "dump", "YamliteError"]


class YamliteError(ValueError):
    """Raised when a file uses YAML beyond the supported subset."""

    def __init__(self, message: str, line_no: int, line: str = "") -> None:
        detail = f"line {line_no}: {message}"
        if line:
            detail += f"\n    {line.strip()}"
        super().__init__(detail)
        self.line_no = line_no


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

_KEY_RE = re.compile(r"^([A-Za-z_][\w.\-]*|\"[^\"]+\"|'[^']+')\s*:(?:\s+(.*))?$")
_TRUE = {"true", "yes", "on"}
_FALSE = {"false", "no", "off"}
_NULL = {"", "null", "~", "none"}


class _Line:
    __slots__ = ("indent", "text", "no", "raw")

    def __init__(self, indent: int, text: str, no: int, raw: str) -> None:
        self.indent = indent
        self.text = text
        self.no = no
        self.raw = raw


def _tokenize(source: str) -> list[_Line]:
    lines: list[_Line] = []
    for i, raw in enumerate(source.splitlines(), start=1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise YamliteError("tabs are not valid indentation in YAML", i, raw)
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "---":
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        lines.append(_Line(indent, stripped, i, raw))
    return lines


def _strip_comment(value: str) -> str:
    """Remove a trailing comment, respecting quotes."""
    out: list[str] = []
    quote: str | None = None
    prev = ""
    for ch in value:
        if quote:
            if ch == quote and prev != "\\":
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (not out or out[-1] in " \t"):
            break
        out.append(ch)
        prev = ch
    return "".join(out).strip()


def _scalar(raw: str, line_no: int) -> Any:
    value = _strip_comment(raw).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        if value[0] == '"':
            return inner.replace('\\"', '"').replace("\\n", "\n")
        # Single-quoted YAML is verbatim apart from '' meaning a literal
        # quote. Detection patterns are stored single-quoted precisely so a
        # regex like \d+ survives without backslash mangling.
        return inner.replace("''", "'")
    low = value.lower()
    if low in _NULL:
        return None
    if low in _TRUE:
        return True
    if low in _FALSE:
        return False
    if re.fullmatch(r"[-+]?\d+", value):
        return int(value)
    if re.fullmatch(r"[-+]?(\d+\.\d*|\.\d+)([eE][-+]?\d+)?", value):
        return float(value)
    if value.startswith("[") and value.endswith("]"):
        body = value[1:-1].strip()
        if not body:
            return []
        return [_scalar(item, line_no) for item in _split_flow(body)]
    if value.startswith("{") and value.endswith("}"):
        if not value[1:-1].strip():
            return {}  # `key: {}` is a common and unambiguous way to say empty
        raise YamliteError(
            "inline maps are not supported - use indented keys instead",
            line_no, raw,
        )
    return value


def _split_flow(body: str) -> list[str]:
    items, depth, current, quote = [], 0, [], None
    for ch in body:
        if quote:
            if ch == quote:
                quote = None
            current.append(ch)
            continue
        if ch in "\"'":
            quote = ch
            current.append(ch)
        elif ch == "[":
            depth += 1
            current.append(ch)
        elif ch == "]":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            items.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        items.append("".join(current))
    return [item.strip() for item in items if item.strip()]


def _block_scalar(
    lines: list[_Line], index: int, parent_indent: int, style: str, chomp: str
) -> tuple[str, int]:
    """Collect an indented literal (|) or folded (>) block."""
    collected: list[str] = []
    base: int | None = None
    while index < len(lines) and lines[index].indent > parent_indent:
        line = lines[index]
        if base is None:
            base = line.indent
        collected.append(" " * max(0, line.indent - base) + line.text)
        index += 1
    if style == ">":
        text = " ".join(part for part in collected if part)
    else:
        text = "\n".join(collected)
    if chomp != "-":
        text += "\n"
    if chomp == "-":
        text = text.rstrip("\n")
    return text, index


def _parse_block(lines: list[_Line], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return None, index
    if lines[index].text.startswith("- "):
        return _parse_list(lines, index, indent)
    if lines[index].text == "-":
        return _parse_list(lines, index, indent)
    return _parse_map(lines, index, indent)


def _parse_map(lines: list[_Line], index: int, indent: int) -> tuple[dict, int]:
    result: dict[str, Any] = {}
    while index < len(lines) and lines[index].indent >= indent:
        line = lines[index]
        if line.indent > indent:
            raise YamliteError("unexpected indentation", line.no, line.raw)
        if line.text.startswith("- "):
            break
        match = _KEY_RE.match(line.text)
        if not match:
            raise YamliteError(
                "expected `key: value` - Estate Agent's YAML subset does not "
                "support this construct",
                line.no, line.raw,
            )
        key = match.group(1).strip("\"'")
        rest = (match.group(2) or "").strip()
        index += 1

        if rest in ("|", ">", "|-", ">-", "|+", ">+"):
            style, chomp = rest[0], (rest[1] if len(rest) > 1 else "")
            result[key], index = _block_scalar(lines, index, line.indent, style, chomp)
            continue

        if rest == "":
            if index < len(lines) and lines[index].indent > line.indent:
                result[key], index = _parse_block(lines, index, lines[index].indent)
            elif (
                index < len(lines)
                and lines[index].indent == line.indent
                and lines[index].text.startswith("-")
            ):
                # A list written at the same indentation as its key, which is
                # valid YAML and common in hand-written files.
                result[key], index = _parse_list(lines, index, line.indent)
            else:
                result[key] = None
            continue

        result[key] = _scalar(rest, line.no)
    return result, index


def _parse_list(lines: list[_Line], index: int, indent: int) -> tuple[list, int]:
    items: list[Any] = []
    while index < len(lines) and lines[index].indent == indent:
        line = lines[index]
        if not line.text.startswith("-"):
            break
        rest = line.text[1:].strip()
        index += 1

        if rest == "":
            if index < len(lines) and lines[index].indent > indent:
                value, index = _parse_block(lines, index, lines[index].indent)
                items.append(value)
            else:
                items.append(None)
            continue

        if _KEY_RE.match(rest):
            # `- key: value`, optionally followed by sibling keys indented to
            # line up under the dash:
            #
            #     - service: payments      <- inline, belongs with the siblings
            #       via: rest              <- sibling
            #       endpoints:
            #         - /v2/charge
            #
            # Collect the continuation lines first so we know what indentation
            # the siblings actually use, then splice the inline part in at that
            # same depth and parse the whole thing as one map.
            body = []
            while index < len(lines) and lines[index].indent > indent:
                body.append(lines[index])
                index += 1
            sibling_indent = body[0].indent if body else indent + 2
            spliced = [_Line(sibling_indent, rest, line.no, line.raw)] + body
            value, _ = _parse_map(spliced, 0, sibling_indent)
            items.append(value)
            continue

        items.append(_scalar(rest, line.no))
    return items, index


def load(source: str) -> Any:
    """Parse the supported YAML subset. Returns dict, list, or None.

    Deliberately does not fall back to PyYAML when it happens to be installed.
    Two parsers means the one running on your machine might not be the one the
    test suite exercises, and a context file that reads differently on two
    laptops is exactly the class of bug this project exists to prevent.
    """
    lines = _tokenize(source)
    if not lines:
        return None
    value, index = _parse_block(lines, 0, lines[0].indent)
    if index < len(lines):
        leftover = lines[index]
        raise YamliteError(
            "could not parse the rest of the file", leftover.no, leftover.raw
        )
    return value


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

_PLAIN_SAFE = re.compile(r"^[A-Za-z_][\w .,/@+()'\-]*$")


def _emit_scalar(value: Any) -> str:
    if value is None:
        return ""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "":
        return '""'
    if "\n" in text:
        return "|"  # handled by the caller
    if _PLAIN_SAFE.match(text) and text.lower() not in _TRUE | _FALSE | _NULL:
        return text
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _dump_value(value: Any, indent: int, out: list[str]) -> None:
    pad = " " * indent
    if isinstance(value, dict):
        for key, item in value.items():
            _dump_pair(str(key), item, indent, out)
    elif isinstance(value, list):
        if not value:
            out[-1] = out[-1] + " []"
            return
        for item in value:
            if isinstance(item, dict):
                first = True
                for key, sub in item.items():
                    if first:
                        buffer: list[str] = []
                        _dump_pair(str(key), sub, 0, buffer)
                        out.append(f"{pad}- {buffer[0].lstrip()}")
                        out.extend(f"{pad}  {line}" for line in buffer[1:])
                        first = False
                    else:
                        buffer = []
                        _dump_pair(str(key), sub, 0, buffer)
                        out.extend(f"{pad}  {line}" for line in buffer)
            elif isinstance(item, list):
                raise YamliteError("nested bare lists are not supported", 0)
            else:
                out.append(f"{pad}- {_emit_scalar(item)}")
    else:
        out.append(f"{pad}{_emit_scalar(value)}")


def _dump_pair(key: str, value: Any, indent: int, out: list[str]) -> None:
    pad = " " * indent
    if isinstance(value, dict):
        if not value:
            out.append(f"{pad}{key}: {{}}".replace("{}", ""))
            return
        out.append(f"{pad}{key}:")
        _dump_value(value, indent + 2, out)
    elif isinstance(value, list):
        if not value:
            out.append(f"{pad}{key}: []")
            return
        out.append(f"{pad}{key}:")
        _dump_value(value, indent + 2, out)
    elif isinstance(value, str) and "\n" in value:
        out.append(f"{pad}{key}: |")
        for line in value.rstrip("\n").split("\n"):
            out.append(f"{pad}  {line}" if line else "")
    else:
        out.append(f"{pad}{key}: {_emit_scalar(value)}")


def dump(data: Any) -> str:
    """Serialise back into the same subset. Round-trips with `load`."""
    out: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            _dump_pair(str(key), value, 0, out)
    else:
        _dump_value(data, 0, out)
    return "\n".join(out) + "\n"
