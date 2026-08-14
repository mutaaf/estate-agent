"""A small Markdown renderer, standard library only.

The site is generated from the same files in `docs/` that people read on
GitHub, so the two can never drift. That means the generator needs a Markdown
renderer, and Estate Agent does not take dependencies - including for its own
website.

Supports the subset the docs actually use: headings, paragraphs, ordered and
unordered lists, fenced code, blockquotes, tables, horizontal rules, links,
images, bold, italic, and inline code. Headings get stable id anchors, which
matters more than it sounds: a versioned spec page whose anchors move breaks
every citation pointing at it.
"""

from __future__ import annotations

import html
import re

__all__ = ["render", "headings", "strip"]

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?!\*)")
_UNDERSCORE_ITALIC = re.compile(r"(?<![_\w])_([^_\n]+)_(?!\w)")
_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)(?:\s+\"([^\"]*)\")?\)")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_AUTOLINK = re.compile(r"(?<![\"'=(])\bhttps?://[^\s<>\"')\]]+")


def slugify(text: str) -> str:
    cleaned = re.sub(r"`|\*|_", "", text).strip().lower()
    cleaned = re.sub(r"[^\w\s-]", "", cleaned)
    return re.sub(r"[\s_]+", "-", cleaned).strip("-") or "section"


def _inline(text: str) -> str:
    """Escape, then apply inline formatting. Code spans are protected first."""
    placeholders: list[str] = []

    def stash(match: re.Match[str]) -> str:
        placeholders.append(
            f"<code>{html.escape(match.group(1), quote=False)}</code>"
        )
        return f"\x00{len(placeholders) - 1}\x00"

    text = _INLINE_CODE.sub(stash, text)
    text = html.escape(text, quote=False)

    text = _IMAGE.sub(
        lambda m: f'<img src="{html.escape(m.group(2), quote=True)}" '
                  f'alt="{html.escape(m.group(1), quote=True)}" loading="lazy">',
        text,
    )
    text = _LINK.sub(_render_link, text)
    text = _AUTOLINK.sub(lambda m: f'<a href="{m.group(0)}">{m.group(0)}</a>', text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    text = _UNDERSCORE_ITALIC.sub(r"<em>\1</em>", text)

    for index, value in enumerate(placeholders):
        text = text.replace(f"\x00{index}\x00", value)
    return text


# The slug of the page currently being rendered, e.g. "estate" or
# "workflows/cross-repo-change". Docs link to each other by filename; on the
# site every page lives in its own directory, so a sibling link needs to climb
# out first. Without this the links resolve one level too deep and every
# cross-reference on the site 404s.
_current_slug = ""


def _render_link(match: re.Match[str]) -> str:
    import posixpath

    label, target = match.group(1), match.group(2)
    title = match.group(3)

    # Split the anchor off first: `tiers.md#one` does not end in `.md`, so
    # checking the extension before splitting silently skips every link that
    # points at a specific section.
    anchor = ""
    if "#" in target and not target.startswith("#"):
        target, fragment = target.split("#", 1)
        anchor = "#" + fragment

    if target.endswith(".md") and not target.startswith(("http", "/")):
        # Resolve the link against the current page's position in docs/,
        # then express it relative to the current page's URL depth.
        here = posixpath.dirname(_current_slug)
        resolved = posixpath.normpath(posixpath.join(here, target[:-3]))
        depth = len([p for p in _current_slug.split("/") if p])
        target = "../" * depth + f"{resolved}/{anchor}"
    else:
        target = target + anchor
    attributes = f' title="{html.escape(title, quote=True)}"' if title else ""
    external = ' target="_blank" rel="noopener"' if target.startswith("http") else ""
    return (
        f'<a href="{html.escape(target, quote=True)}"{attributes}{external}>'
        f"{label}</a>"
    )


def _table(rows: list[str]) -> str:
    def cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]

    header = cells(rows[0])
    body = [cells(r) for r in rows[2:]]
    out = ['<div class="scroll"><table>', "<thead><tr>"]
    out += [f"<th>{_inline(c)}</th>" for c in header]
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append("<tr>")
        out += [f"<td>{_inline(c)}</td>" for c in row]
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def render(source: str, slug: str = "") -> str:
    """Markdown to HTML. `slug` is the page's URL path, used to rewrite
    links between documents correctly."""
    global _current_slug
    _current_slug = slug
    lines = source.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    index = 0
    seen_ids: dict[str, int] = {}

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            index += 1
            continue

        # Fenced code
        if stripped.startswith("```"):
            language = stripped[3:].strip()
            index += 1
            block: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                block.append(lines[index])
                index += 1
            index += 1
            code = html.escape("\n".join(block), quote=False)
            attribute = f' class="language-{html.escape(language, quote=True)}"' if language else ""
            out.append(f'<div class="scroll"><pre><code{attribute}>{code}</code></pre></div>')
            continue

        # Heading
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            level = len(heading.group(1))
            text = heading.group(2).rstrip("#").strip()
            base = slugify(text)
            seen_ids[base] = seen_ids.get(base, 0) + 1
            anchor = base if seen_ids[base] == 1 else f"{base}-{seen_ids[base]}"
            out.append(
                f'<h{level} id="{anchor}">{_inline(text)}'
                f'<a class="anchor" href="#{anchor}" aria-label="Link to this section">#</a>'
                f"</h{level}>"
            )
            index += 1
            continue

        # Horizontal rule
        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            out.append("<hr>")
            index += 1
            continue

        # Table
        if (
            "|" in stripped
            and index + 1 < len(lines)
            and re.fullmatch(r"\|?[\s:|-]+\|[\s:|-]*", lines[index + 1].strip())
        ):
            block = []
            while index < len(lines) and "|" in lines[index]:
                block.append(lines[index])
                index += 1
            if len(block) >= 2:
                out.append(_table(block))
                continue

        # Blockquote
        if stripped.startswith(">"):
            block = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                block.append(lines[index].strip().lstrip(">").strip())
                index += 1
            out.append(f"<blockquote>{render(chr(10).join(block), slug)}</blockquote>")
            continue

        # Lists
        list_match = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)$", line)
        if list_match:
            ordered = not list_match.group(2) in ("-", "*", "+")
            items: list[str] = []
            while index < len(lines):
                item_match = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)$", lines[index])
                if not item_match:
                    # A wrapped continuation line belongs to the previous item.
                    if items and lines[index].strip() and lines[index].startswith(("  ", "\t")):
                        items[-1] += " " + lines[index].strip()
                        index += 1
                        continue
                    break
                items.append(item_match.group(3))
                index += 1
            tag = "ol" if ordered else "ul"
            rendered = "".join(f"<li>{_inline(i)}</li>" for i in items)
            out.append(f"<{tag}>{rendered}</{tag}>")
            continue

        # Paragraph
        block = []
        while index < len(lines) and lines[index].strip():
            candidate = lines[index].strip()
            if (
                candidate.startswith(("#", ">", "```"))
                or re.match(r"^(\s*)([-*+]|\d+\.)\s+", lines[index])
                or re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", candidate)
            ):
                break
            block.append(candidate)
            index += 1
        if block:
            out.append(f"<p>{_inline(' '.join(block))}</p>")

    return "\n".join(out)


def headings(source: str, levels: tuple[int, ...] = (2,)) -> list[tuple[int, str, str]]:
    """(level, text, anchor) for building a table of contents."""
    found: list[tuple[int, str, str]] = []
    seen: dict[str, int] = {}
    in_code = False
    for line in source.split("\n"):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        match = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
        if not match:
            continue
        level = len(match.group(1))
        text = match.group(2).rstrip("#").strip()
        base = slugify(text)
        seen[base] = seen.get(base, 0) + 1
        anchor = base if seen[base] == 1 else f"{base}-{seen[base]}"
        if level in levels:
            found.append((level, text, anchor))
    return found


def strip(source: str, limit: int = 200) -> str:
    """Plain-text summary for meta description tags."""
    text = source
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"^\s*#.*$", " ", text, flags=re.M)
    text = re.sub(r"^\s*[|>-].*$", " ", text, flags=re.M)
    text = _IMAGE.sub(" ", text)
    text = _LINK.sub(r"\1", text)
    text = re.sub(r"[`*_#]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "…"
