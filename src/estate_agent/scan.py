"""`estate scan` - map the whole workspace.

Reads every repo it can find, resolves the connections between them, and
writes three things:

    estate/estate.yaml   the register, in the same format as a deed
    estate/graph.json    the machine-readable map, including the confirm list
    ESTATE.md            the readable version

It also writes a `related_repos` hint back into each repo's deed, so an agent
opening a single repo already knows who calls it without running anything.
"""

from __future__ import annotations

import time
from pathlib import Path

from . import ui, yamlite
from .deed import DEED_PATH, load as load_deed
from .discover import find_repos, survey
from .graph import EstateMap, build, render_register, write_json

ESTATE_DIR = "estate"


def cmd_scan(args: list[str]) -> int:
    positional = [a for a in args if not a.startswith("-")]
    workspace = Path(positional[0] if positional else ".").expanduser().resolve()
    quiet = "--quiet" in args
    write_back = "--no-write-back" not in args

    if not workspace.is_dir():
        ui.error(f"{workspace} is not a directory")
        return 1

    started = time.time()
    if not quiet:
        ui.title(f"Surveying {workspace}")

    repos = find_repos(workspace)
    if not repos:
        ui.error(f"no repos found under {workspace}")
        ui.note("Point `estate scan` at the directory that holds your repos.")
        return 1

    records = []
    for root in repos:
        record = survey(root, workspace)
        # A deed's declared connections outrank anything detected.
        deed, _problems = load_deed(root / DEED_PATH)
        if deed.consumes:
            record.declared_consumes = deed.consumes
        if deed.name:
            record.name = deed.name
        records.append(record)
        if not quiet:
            _report_repo(record)

    estate = build(records, str(workspace))

    out_dir = workspace / ESTATE_DIR
    write_json(estate, out_dir / "graph.json", time.time() - started)
    (out_dir / "estate.yaml").write_text(
        yamlite.dump(_register_yaml(estate)), encoding="utf-8"
    )
    (workspace / "ESTATE.md").write_text(
        render_register(estate), encoding="utf-8"
    )

    written_back = _write_back(estate, workspace) if write_back else 0

    if not quiet:
        _report_estate(estate, workspace, written_back, time.time() - started)
    return 0


def _report_repo(record) -> None:
    stack = record.primary_stack or "unrecognised"
    detail_bits = []
    if record.endpoints:
        detail_bits.append(f"{len(record.endpoints)} endpoints")
    if record.signals:
        detail_bits.append(f"{len(record.signals)} call sites")
    if record.contracts:
        detail_bits.append(f"{len(record.contracts)} contracts")
    status = ui.PASS if record.primary_stack else ui.WARN
    ui.item(
        status, f"{record.name}  ({stack})",
        ", ".join(detail_bits) or "nothing found",
    )


def _report_estate(
    estate: EstateMap, workspace: Path, written_back: int, seconds: float
) -> None:
    ui.title("The estate")
    kinds = {"backend": 0, "client": 0, "legacy": 0}
    for record in estate.repos:
        kinds[record.kind] = kinds.get(record.kind, 0) + 1
    ui.item(ui.INFO, f"{len(estate.repos)} repos")
    ui.item(
        ui.INFO,
        f"{kinds.get('backend', 0)} services · {kinds.get('client', 0)} client "
        f"apps · {kinds.get('legacy', 0)} legacy systems",
    )
    ui.item(ui.PASS, f"{len(estate.edges)} connections, each with evidence")
    if estate.unresolved:
        ui.item(
            ui.WARN, f"{len(estate.unresolved)} need confirming",
            "listed at the end of ESTATE.md - answering one takes a moment "
            "and it stops being asked",
        )
    no_deed = [r for r in estate.repos if not r.has_deed]
    if no_deed:
        ui.item(
            ui.WARN, f"{len(no_deed)} repos have no deed",
            "run `estate init` in each so agents know how to work there",
        )
    if written_back:
        ui.item(ui.PASS, f"updated related repos in {written_back} deeds")

    ui.summary(len(estate.edges), 0, len(estate.unresolved))
    ui.note(f"scanned in {seconds:.1f}s · nothing left this machine")
    ui.say()
    ui.note(f"  {workspace / 'ESTATE.md'}")
    ui.note(f"  {workspace / ESTATE_DIR / 'graph.json'}")
    ui.say()
    ui.next_step("estate impact <repo> <endpoint>   to see what a change breaks")


def _register_yaml(estate: EstateMap) -> dict:
    return {
        "estate_agent_version": "0.1.0",
        "workspace": estate.workspace,
        "repos": [
            {
                "name": r.name,
                "path": r.path,
                "stack": r.primary_stack or "unrecognised",
                "kind": r.kind,
                "endpoints": len(r.endpoints),
                "has_deed": r.has_deed,
            }
            for r in sorted(estate.repos, key=lambda r: r.name)
        ],
        "connections": [
            {
                "from": e.source, "to": e.target, "via": e.via,
                "resolved_by": e.method, "evidence": e.evidence[0]
                if e.evidence else "",
            }
            for e in estate.edges
        ],
        "needs_confirming": [u.as_dict() for u in estate.unresolved],
    }


def _write_back(estate: EstateMap, workspace: Path) -> int:
    """Put each repo's neighbours into its deed, so a single-repo session
    starts out knowing who depends on it."""
    updated = 0
    for record in estate.repos:
        deed_file = workspace / record.path / DEED_PATH
        if not deed_file.is_file():
            continue
        neighbours = sorted({
            *(e.target for e in estate.callees_of(record.name)),
            *(e.source for e in estate.callers_of(record.name)),
        })
        if not neighbours:
            continue
        try:
            data = yamlite.load(deed_file.read_text(encoding="utf-8"))
        except (yamlite.YamliteError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("related_repos") == neighbours:
            continue
        data["related_repos"] = neighbours
        try:
            deed_file.write_text(yamlite.dump(data), encoding="utf-8")
            updated += 1
        except OSError:
            continue
    return updated
