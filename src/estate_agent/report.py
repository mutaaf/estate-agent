"""`estate report` - a diagnostic you can actually send.

Field-testing on a work machine has a problem: the interesting bugs are found
against a real estate, and a real estate is confidential. Repo names, internal
hostnames and route paths are exactly the things you cannot paste into a public
issue tracker - so the findings stay on the laptop and the bug never gets
fixed.

This produces a report that is structurally complete and carries no identifying
information. Every repo becomes `repo-01`, every host becomes `host-a`, and
every file path is reduced to its basename and line number. What survives is
the shape of the problem: which stacks were detected, how many endpoints each
found, which resolution methods fired, what got truncated, and where coverage
looks suspicious.

Redaction is the default. `--include-names` turns it off for local use, and
says so at the top of the report so nobody forwards one by accident.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
from pathlib import Path
from typing import Any

from . import ui
from .graph import EstateMap
from .impact import _find_graph, load_map

VERSION = "0.1.0"


class Redactor:
    """Stable pseudonyms. The same repo is `repo-03` every time, so two
    reports from the same machine can be compared."""

    def __init__(self, estate: EstateMap, active: bool = True) -> None:
        self.active = active
        self.repos: dict[str, str] = {}
        self.hosts: dict[str, str] = {}
        self.extra: list[str] = []

        for index, record in enumerate(
            sorted(estate.repos, key=lambda r: r.name), start=1
        ):
            self.repos[record.name] = f"repo-{index:02d}"
        for index, node in enumerate(
            sorted(estate.infrastructure, key=lambda n: n.display), start=1
        ):
            self.hosts[node.display] = f"host-{chr(96 + min(index, 26))}"

        # Anything the user listed locally as private, if they made the file.
        denylist = Path.cwd() / ".publish-denylist"
        if denylist.is_file():
            try:
                for line in denylist.read_text(encoding="utf-8").splitlines():
                    line = line.split("#")[0].strip()
                    if len(line) >= 3:
                        self.extra.append(line)
            except OSError:
                pass

    def repo(self, name: str) -> str:
        if not self.active:
            return name
        return self.repos.get(name, "repo-??")

    def host(self, name: str) -> str:
        if not self.active:
            return name
        return self.hosts.get(name, self.scrub(name))

    def evidence(self, value: str) -> str:
        """`src/app/(dashboard)/settings/page.tsx:78` -> `…/page.tsx:78`.

        The basename and line number are what make a pattern bug diagnosable.
        The directory names are what identify a company.
        """
        if not self.active:
            return value
        if not value:
            return ""
        text, _, line = value.rpartition(":")
        if not text:
            text, line = value, ""
        name = text.rsplit("/", 1)[-1]
        return f"…/{name}:{line}" if line else f"…/{name}"

    def scrub(self, text: str) -> str:
        if not self.active or not text:
            return text
        for real, alias in self.repos.items():
            text = re.sub(rf"\b{re.escape(real)}\b", alias, text)
        for real, alias in self.hosts.items():
            text = text.replace(real, alias)
        for term in self.extra:
            text = re.sub(rf"(?i)\b{re.escape(term)}\b", "[redacted]", text)
        # Any remaining internal-looking hostname.
        text = re.sub(
            r"\b[\w-]+\.(?:corp|internal|intranet|local|lan|prod|priv)"
            r"(?:\.[\w-]+)*\b",
            "[host]", text,
        )
        return text

    def path_shape(self, path: str) -> str:
        """`/api/settings/ai-keys` -> `/a/b/c` - depth without the words."""
        if not self.active:
            return path
        segments = [s for s in path.split("/") if s]
        return "/" + "/".join(
            "*" if s == "*" else chr(97 + (i % 26)) for i, s in enumerate(segments)
        ) if segments else "/"


def _call_sites(record: Any) -> int:
    return getattr(record, "call_sites", 0) or len(record.signals)


def build(estate: EstateMap, seconds: float, redact: bool = True) -> str:
    r = Redactor(estate, active=redact)
    out: list[str] = []

    out.append("# Estate Agent field report")
    out.append("")
    if not redact:
        out.append(
            "> **UNREDACTED.** This contains real repo names and paths. Do not "
            "post it anywhere public. Regenerate without `--include-names` to "
            "get a shareable version."
        )
        out.append("")
    else:
        out.append(
            "_Repo names, hosts and file paths are pseudonymised. The shape of "
            "the data is preserved so the report is still diagnosable._"
        )
        out.append("")

    # -- environment --------------------------------------------------------
    out.append("## Environment")
    out.append("")
    out.append(f"- Estate Agent {VERSION}")
    out.append(f"- Python {sys.version.split()[0]}")
    out.append(f"- {platform.system()} {platform.machine()}")
    out.append(f"- Scan took **{seconds:.1f}s** for {len(estate.repos)} repos")
    out.append("")

    # -- coverage -----------------------------------------------------------
    by_stack: dict[str, list[Any]] = {}
    for record in estate.repos:
        by_stack.setdefault(record.primary_stack or "unrecognised", []).append(record)

    out.append("## Detection coverage")
    out.append("")
    out.append(
        "`silent` counts repos of that stack where nothing at all was found - "
        "no endpoints and no call sites. A high silent count is the clearest "
        "signal that a stack profile needs work."
    )
    out.append("")
    out.append("| Stack | Repos | Endpoints | Call sites | Silent |")
    out.append("| --- | --- | --- | --- | --- |")
    for stack in sorted(by_stack, key=lambda s: -len(by_stack[s])):
        records = by_stack[stack]
        endpoints = sum(len(x.endpoints) for x in records)
        signals = sum(_call_sites(x) for x in records)
        silent = sum(
            1 for x in records if not x.endpoints and not _call_sites(x)
        )
        out.append(
            f"| {stack} | {len(records)} | {endpoints} | {signals} | "
            f"{silent}{' ⚠' if silent else ''} |"
        )
    out.append("")

    # -- resolution ---------------------------------------------------------
    methods: dict[str, int] = {}
    for edge in estate.edges:
        methods[edge.method] = methods.get(edge.method, 0) + 1

    out.append("## Resolution")
    out.append("")
    out.append(f"- **{len(estate.edges)}** connections")
    out.append(f"- **{len(estate.unresolved)}** awaiting confirmation")
    out.append(f"- **{len(estate.external)}** external (outside the estate)")
    out.append(
        f"- **{len(estate.infrastructure)}** infrastructure nodes, "
        f"{sum(1 for n in estate.infrastructure if n.is_shared)} shared"
    )
    out.append("")
    if methods:
        out.append("| Resolved by | Count |")
        out.append("| --- | --- |")
        for method, count in sorted(methods.items(), key=lambda kv: -kv[1]):
            out.append(f"| {method} | {count} |")
        out.append("")

    # -- the edges, in shape only -------------------------------------------
    if estate.edges:
        out.append("### Connections")
        out.append("")
        out.append("| From | To | Via | By | Confidence | Evidence |")
        out.append("| --- | --- | --- | --- | --- | --- |")
        for edge in estate.edges[:40]:
            out.append(
                f"| {r.repo(edge.source)} | {r.repo(edge.target)} | {edge.via} "
                f"| {edge.method} | {edge.score:.2f} "
                f"| `{r.evidence(edge.evidence[0] if edge.evidence else '')}` |"
            )
        if len(estate.edges) > 40:
            out.append(f"\n_…and {len(estate.edges) - 40} more._")
        out.append("")

    # -- the questions ------------------------------------------------------
    if estate.unresolved:
        out.append("### Awaiting confirmation")
        out.append("")
        out.append(
            "If this list is long, that is the bug: people stop answering it "
            "and the map stays partial."
        )
        out.append("")
        out.append("| From | Kind | Shape | Reason |")
        out.append("| --- | --- | --- | --- |")
        for item in estate.unresolved[:30]:
            shape = (
                r.path_shape(item.value) if item.signal == "path"
                else f"<{item.signal}>"
            )
            out.append(
                f"| {r.repo(item.source)} | {item.signal} | `{shape}` "
                f"| {r.scrub(item.reason)} |"
            )
        out.append("")

    # -- anomalies worth reporting -----------------------------------------
    out.append("## Possible problems")
    out.append("")
    problems: list[str] = []

    for record in estate.repos:
        for note in record.notes:
            problems.append(f"`{r.repo(record.name)}`: {r.scrub(note)}")

    silent_repos = [
        x for x in estate.repos
        if x.primary_stack and not x.endpoints and not _call_sites(x)
    ]
    if silent_repos:
        problems.append(
            f"{len(silent_repos)} repo(s) matched a stack but yielded nothing: "
            + ", ".join(
                f"{r.repo(x.name)} ({x.primary_stack})" for x in silent_repos[:10]
            )
        )

    unrecognised = [x for x in estate.repos if not x.primary_stack]
    if unrecognised:
        problems.append(
            f"{len(unrecognised)} repo(s) matched no stack profile at all "
            f"— a missing profile, or detection too strict"
        )

    if seconds > 30:
        problems.append(
            f"scan took {seconds:.0f}s, which is slow — worth profiling"
        )

    if len(estate.unresolved) > 10:
        problems.append(
            f"{len(estate.unresolved)} items awaiting confirmation — too many "
            f"to be answered in practice"
        )

    if problems:
        out += [f"- {p}" for p in problems]
    else:
        out.append("_Nothing obviously wrong._")
    out.append("")

    out.append("---")
    out.append("")
    out.append(
        "**Judging this report:** a phantom connection is the most serious "
        "finding — check a few of the connections above against the code and "
        "say how many were real. Recall matters less than precision, because a "
        "missed connection gets added by hand and stays added, while a false "
        "one stops the map being read."
    )
    out.append("")
    return "\n".join(out)


def cmd_report(args: list[str]) -> int:
    import time

    positional = [a for a in args if not a.startswith("-")]
    workspace = Path(positional[0] if positional else ".").expanduser().resolve()
    redact = "--include-names" not in args

    out_file: Path | None = None
    if "--out" in args:
        out_file = Path(args[args.index("--out") + 1]).expanduser().resolve()

    graph_file = _find_graph(workspace)
    if graph_file is None:
        ui.error("no estate map found")
        ui.note(f"Run `estate scan {workspace}` first.")
        return 1

    started = time.time()
    try:
        estate = load_map(graph_file)
    except (json.JSONDecodeError, OSError) as exc:
        ui.error(f"could not read {graph_file}: {exc}")
        return 1
    elapsed = time.time() - started

    # Prefer the real scan duration if the scan recorded one.
    try:
        raw = json.loads(graph_file.read_text(encoding="utf-8"))
        elapsed = float(raw.get("scan_seconds") or elapsed)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        pass

    text = build(estate, elapsed, redact=redact)

    if out_file:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(text, encoding="utf-8")
        ui.title("Field report written")
        ui.item(ui.PASS, str(out_file))
        if redact:
            ui.item(
                ui.INFO, "Redacted",
                "repo names, hosts and paths are pseudonymised — safe to share",
            )
        else:
            ui.item(
                ui.WARN, "NOT redacted",
                "contains real names and paths; do not post publicly",
            )
        ui.say()
        ui.next_step(
            "read it, then open an issue at "
            "github.com/mutaaf/estate-agent/issues"
        )
    else:
        print(text)
    return 0
