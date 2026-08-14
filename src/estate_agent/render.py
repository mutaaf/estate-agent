"""Render one deed into the five context files assistants actually read.

Every generated file carries a stamp:

    <!-- estate-agent v0.1.0 generated-from=.agent/estate.yaml body-sha=... -->

The stamp is what lets `estate check` tell two very different situations
apart, which matters because the right response to each is opposite:

  * body-sha still matches the file  -> the deed changed; regenerate freely.
  * body-sha no longer matches       -> a human edited this file by hand.
                                        Never overwrite. Offer to promote the
                                        edit into the deed instead.

Clobbering someone's writing once is enough to lose their trust in the tool
permanently, so the distinction is built into the format rather than left to
a command-line flag.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .deed import Deed

VERSION = "0.1.0"
SOURCE = ".agent/estate.yaml"

STAMP_RE = re.compile(
    r"<!--\s*estate-agent\s+v(?P<version>[\d.]+)\s+"
    r"generated-from=(?P<source>\S+)\s+body-sha=(?P<sha>[0-9a-f]{16})\s*-->"
)


@dataclass
class Rendered:
    path: str
    text: str


def body_sha(body: str) -> str:
    return hashlib.sha256(body.strip().encode("utf-8")).hexdigest()[:16]


def stamp(body: str) -> str:
    return (
        f"<!-- estate-agent v{VERSION} generated-from={SOURCE} "
        f"body-sha={body_sha(body)} -->"
    )


# --------------------------------------------------------------------------
# Shared body
# --------------------------------------------------------------------------


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _commands_block(deed: Deed) -> str:
    if not deed.commands:
        return (
            "_No commands recorded yet. Add them to `.agent/estate.yaml` — an "
            "agent that cannot run your tests cannot check its own work._"
        )
    order = ["install", "build", "test", "lint", "format", "run", "typecheck"]
    ordered = [k for k in order if k in deed.commands]
    ordered += [k for k in deed.commands if k not in order]
    rows = "\n".join(
        f"| {name} | `{deed.commands[name]}` |" for name in ordered
    )
    return f"| Purpose | Command |\n| --- | --- |\n{rows}"


def _estate_block(deed: Deed) -> str:
    parts: list[str] = []

    if deed.contracts:
        parts.append(
            "**Contracts this service publishes**\n\n"
            + _bullets([f"`{c}`" for c in deed.contracts])
        )

    if deed.endpoints:
        rows = []
        for endpoint in deed.endpoints[:25]:
            method = str(endpoint.get("method") or "").upper()
            path = endpoint.get("path", "")
            note = endpoint.get("note") or endpoint.get("summary") or ""
            rows.append(f"| {method or '—'} | `{path}` | {note} |")
        more = ""
        if len(deed.endpoints) > 25:
            more = f"\n\n_…and {len(deed.endpoints) - 25} more._"
        parts.append(
            "**Endpoints this service exposes**\n\n"
            "| Method | Path | Notes |\n| --- | --- | --- |\n"
            + "\n".join(rows) + more
        )

    if deed.consumes:
        rows = []
        for item in deed.consumes:
            service = item.get("service", "?")
            via = str(item.get("via") or "unknown")
            evidence = item.get("evidence") or ""
            rows.append(f"| `{service}` | {via} | {evidence} |")
        parts.append(
            "**Services this one calls** — changing how you use these affects "
            "them, and changing your own endpoints affects whoever calls you.\n\n"
            "| Service | Via | Evidence |\n| --- | --- | --- |\n" + "\n".join(rows)
        )

    if deed.related_repos:
        parts.append(
            "**Related repos**\n\n"
            + _bullets([f"`{r}`" for r in deed.related_repos])
        )

    if not parts:
        return (
            "_No estate connections recorded yet. Run `estate scan` at the "
            "root of your workspace to map which services call which._"
        )

    parts.append(
        "Before changing anything on this list, run `estate impact "
        f"{deed.name or '<repo>'} <endpoint>` to see everything that breaks — "
        "including the mobile and TV clients, which ship on their own "
        "timelines and cannot be fixed after the fact."
    )
    return "\n\n".join(parts)


def _tier_block(deed: Deed) -> str:
    info = deed.tier_info
    return (
        f"**Tier {deed.tier} — {info['name']}.** "
        f"In this repo you may {info['agent_may']}. "
        f"You may not {info['agent_may_not']}.\n\n"
        f"_Why this tier: {info['why']}._"
    )


def build_body(deed: Deed) -> str:
    """The shared content. Every client file wraps this."""
    name = deed.name or "this repo"
    sections: list[str] = []

    sections.append(f"# How to work in `{name}`")

    if deed.summary:
        sections.append(deed.summary)

    sections.append("## What you are allowed to do here\n\n" + _tier_block(deed))

    if deed.never_do:
        sections.append(
            "## Never do these\n\n" + _bullets(deed.never_do)
        )

    sections.append("## Commands\n\n" + _commands_block(deed))

    if deed.conventions:
        sections.append("## Conventions\n\n" + _bullets(deed.conventions))

    if deed.architecture:
        sections.append("## Architecture\n\n" + deed.architecture.strip())

    sections.append("## This service in the estate\n\n" + _estate_block(deed))

    sections.append(
        "## If this file turns out to be wrong\n\n"
        "These notes are generated from `.agent/estate.yaml`. They can go "
        "stale, and stale instructions are worse than none — you will act on "
        "them confidently and be wrong.\n\n"
        "So if reality contradicts anything above — a command fails, a service "
        "named here no longer exists, an endpoint has been renamed — then as "
        "part of the same piece of work:\n\n"
        "1. Fix `.agent/estate.yaml` (the source), **not this file** — edits "
        "here are overwritten.\n"
        "2. Run `estate sync` to regenerate.\n"
        "3. Mention the correction in your pull request description, in one "
        "line, so a human can sanity-check it.\n\n"
        "Do not silently work around a wrong instruction. Correcting it is "
        "part of the task, and it is how these notes get better over time "
        "rather than worse."
    )

    if deed.notes:
        sections.append("## Notes\n\n" + deed.notes.strip())

    if deed.owners:
        sections.append(
            "## Owners\n\n" + ", ".join(f"`{o}`" for o in deed.owners)
        )

    return "\n\n".join(sections).strip() + "\n"


# --------------------------------------------------------------------------
# Per-client wrappers
# --------------------------------------------------------------------------

_EDIT_WARNING = (
    "<!-- DO NOT EDIT THIS FILE. It is generated from .agent/estate.yaml.\n"
    "     Edit that file and run `estate sync`. -->"
)


def _wrap(body: str) -> str:
    return f"{stamp(body)}\n{_EDIT_WARNING}\n\n{body}"


def render_claude(deed: Deed) -> Rendered:
    return Rendered("CLAUDE.md", _wrap(build_body(deed)))


def render_agents(deed: Deed) -> Rendered:
    return Rendered("AGENTS.md", _wrap(build_body(deed)))


def render_gemini(deed: Deed) -> Rendered:
    return Rendered("GEMINI.md", _wrap(build_body(deed)))


def render_copilot(deed: Deed) -> Rendered:
    return Rendered(
        ".github/copilot-instructions.md", _wrap(build_body(deed))
    )


def render_cursor(deed: Deed) -> Rendered:
    """Cursor rules carry YAML frontmatter and live under .cursor/rules/."""
    body = build_body(deed)
    summary = (deed.summary or f"How to work in {deed.name}").strip()
    summary = summary.split("\n")[0][:160].replace('"', "'")
    front = (
        "---\n"
        f'description: "{summary}"\n'
        "alwaysApply: true\n"
        "---\n"
    )
    return Rendered(
        ".cursor/rules/00-estate.mdc", f"{front}{stamp(body)}\n{_EDIT_WARNING}\n\n{body}"
    )


RENDERERS = {
    "claude": render_claude,
    "agents": render_agents,
    "cursor": render_cursor,
    "copilot": render_copilot,
    "gemini": render_gemini,
}


def render_all(deed: Deed, clients: list[str] | None = None) -> list[Rendered]:
    names = clients or list(RENDERERS)
    return [RENDERERS[name](deed) for name in names if name in RENDERERS]


# --------------------------------------------------------------------------
# Drift detection
# --------------------------------------------------------------------------

MATCHES = "matches"
STALE = "stale"
HAND_EDITED = "hand-edited"
UNMANAGED = "unmanaged"
MISSING = "missing"


@dataclass
class DriftResult:
    path: str
    state: str
    detail: str = ""

    @property
    def needs_sync(self) -> bool:
        return self.state in (STALE, MISSING)

    @property
    def needs_a_human(self) -> bool:
        return self.state in (HAND_EDITED, UNMANAGED)


def split_stamp(text: str) -> tuple[str | None, str]:
    """Return (recorded_sha, body). `None` when the file is not ours."""
    match = STAMP_RE.search(text)
    if not match:
        return None, text
    body = STAMP_RE.sub("", text, count=1)
    body = body.replace(_EDIT_WARNING, "", 1)
    # Drop Cursor frontmatter before comparing bodies.
    if body.lstrip().startswith("---"):
        parts = body.lstrip().split("---", 2)
        if len(parts) == 3:
            body = parts[2]
    return match.group("sha"), body.strip() + "\n"


def check_file(root: Path, rendered: Rendered) -> DriftResult:
    """Compare what is on disk against what the deed says it should be."""
    path = root / rendered.path
    if not path.is_file():
        return DriftResult(rendered.path, MISSING, "not generated yet")

    try:
        on_disk = path.read_text(encoding="utf-8")
    except OSError as exc:
        return DriftResult(rendered.path, UNMANAGED, f"unreadable: {exc}")

    recorded, disk_body = split_stamp(on_disk)
    if recorded is None:
        return DriftResult(
            rendered.path, UNMANAGED,
            "written by hand, not by Estate Agent - `estate init` will fold "
            "its content into the deed rather than overwrite it",
        )

    if body_sha(disk_body) != recorded:
        return DriftResult(
            rendered.path, HAND_EDITED,
            "edited by hand since it was generated - the edit would be lost "
            "by `estate sync`, so promote it into the deed first",
        )

    _fresh_sha, fresh_body = split_stamp(rendered.text)
    if body_sha(disk_body) != body_sha(fresh_body):
        return DriftResult(
            rendered.path, STALE,
            "the deed changed since this was generated - run `estate sync`",
        )

    return DriftResult(rendered.path, MATCHES)
