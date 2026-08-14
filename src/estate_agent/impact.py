"""`estate impact` - what breaks if you change this.

The command the whole project is built to make possible. An agent working in
one repo cannot see the twelve others that depend on it; this answers that
question from the map, with evidence, in the order you would have to ship.

The ordering rule is the part people underestimate. Services can be deployed
in minutes and rolled back almost as fast. A mobile or TV client cannot: it
goes through review, ships to a fraction of users, and older versions keep
calling the old shape for months. So a client app in the blast radius is not
a follow-up ticket, it is a constraint on the server change itself - usually
meaning you add the new shape before removing the old one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import ui
from .graph import Edge, EstateMap, Unresolved, normalise_path
from .discover import Endpoint, RepoRecord

GRAPH_PATH = Path("estate") / "graph.json"


def _find_graph(start: Path) -> Path | None:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        graph = candidate / GRAPH_PATH
        if graph.is_file():
            return graph
    return None


def load_map(graph_file: Path) -> EstateMap:
    """Rebuild an EstateMap from graph.json (written by `estate scan`)."""
    data = json.loads(graph_file.read_text(encoding="utf-8"))
    repos = []
    for raw in data.get("repos", []):
        record = RepoRecord(
            name=raw.get("name", ""),
            path=raw.get("path", ""),
            primary_stack=raw.get("stack", ""),
            stacks=raw.get("stacks", []),
            kind=raw.get("kind", "backend"),
            contracts=raw.get("contracts", []),
            has_deed=bool(raw.get("has_deed")),
            hosts=raw.get("hosts", []),
            notes=raw.get("notes", []),
        )
        record.endpoints = [
            Endpoint(e.get("method", ""), e.get("path", ""), e.get("evidence", ""))
            for e in raw.get("endpoints", [])
        ]
        repos.append(record)

    edges = [
        Edge(
            e.get("from", ""), e.get("to", ""), e.get("via", "unknown"),
            e.get("resolved_by", ""), float(e.get("confidence", 0)),
            list(e.get("evidence", [])), e.get("detail", ""),
        )
        for e in data.get("edges", [])
    ]
    unresolved = [
        Unresolved(
            u.get("from", ""), u.get("kind", ""), u.get("value", ""),
            u.get("via", ""), u.get("evidence", ""), u.get("reason", ""),
            list(u.get("candidates", [])),
        )
        for u in data.get("unresolved", [])
    ]
    return EstateMap(repos, edges, unresolved, data.get("workspace", ""))


# --------------------------------------------------------------------------
# Blast radius
# --------------------------------------------------------------------------

# Client platforms cannot be rolled forward. The number is "how many release
# cycles you are committed to supporting the old shape for" and drives both
# ordering and the wording of the advice.
SHIP_COST = {"client": 2, "legacy": 1, "backend": 0}


def blast_radius(
    estate: EstateMap, target: str, endpoint: str | None = None
) -> dict[str, Any]:
    """Everything affected by changing `target`, breadth-first from the change."""
    record = estate.repo(target)
    if record is None:
        return {"error": f"no repo called '{target}' in the map"}

    matched_endpoints: list[Endpoint] = []
    if endpoint:
        wanted = normalise_path(endpoint)
        matched_endpoints = [
            e for e in record.endpoints
            if normalise_path(e.path) == wanted
            or normalise_path(e.path).startswith(wanted + "/")
            or wanted.startswith(normalise_path(e.path) + "/")
        ]

    levels: list[list[dict[str, Any]]] = []
    seen = {target}
    frontier = [target]
    depth = 0

    while frontier and depth < 8:
        callers: list[dict[str, Any]] = []
        for name in frontier:
            for edge in estate.callers_of(name):
                if edge.source in seen:
                    continue
                seen.add(edge.source)
                caller = estate.repo(edge.source)
                callers.append({
                    "repo": edge.source,
                    "kind": caller.kind if caller else "backend",
                    "stack": caller.primary_stack if caller else "",
                    "via": edge.via,
                    "through": name,
                    "confidence": edge.score,
                    "resolved_by": edge.method,
                    "evidence": edge.evidence[0] if edge.evidence else "",
                })
        if not callers:
            break
        callers.sort(key=lambda c: (-SHIP_COST.get(c["kind"], 0), c["repo"]))
        levels.append(callers)
        frontier = [c["repo"] for c in callers]
        depth += 1

    affected = [c for level in levels for c in level]
    clients = [c for c in affected if c["kind"] == "client"]
    legacy = [c for c in affected if c["kind"] == "legacy"]

    questions = [
        u for u in estate.unresolved
        if u.candidates and target in u.candidates
    ]

    return {
        "target": target,
        "endpoint": endpoint,
        "matched_endpoints": matched_endpoints,
        "levels": levels,
        "affected": affected,
        "clients": clients,
        "legacy": legacy,
        "unconfirmed": questions,
        "record": record,
    }


def landing_order(result: dict[str, Any]) -> list[str]:
    """The sequence to ship in, and why."""
    steps: list[str] = []
    target = result["target"]

    if result["clients"]:
        steps.append(
            f"Add the new shape to `{target}` alongside the old one. Do not "
            f"remove anything yet."
        )
    else:
        steps.append(f"Change `{target}`.")

    # Services, deepest first, so nothing is briefly broken.
    services = [
        c for level in reversed(result["levels"]) for c in level
        if c["kind"] == "backend"
    ]
    if services:
        names = ", ".join(
            f"`{name}`" for name in dict.fromkeys(c["repo"] for c in services)
        )
        steps.append(f"Update and deploy the services that call it: {names}.")

    if result["legacy"]:
        names = ", ".join(f"`{c['repo']}`" for c in result["legacy"])
        steps.append(
            f"Coordinate the legacy systems by hand: {names}. These do not "
            f"deploy on your schedule."
        )

    if result["clients"]:
        names = ", ".join(
            f"`{name}`" for name in dict.fromkeys(
                c["repo"] for c in result["clients"]
            )
        )
        steps.append(
            f"Ship the client apps: {names}. Each needs its own release, and "
            f"users on older versions keep calling the old shape."
        )
        steps.append(
            f"Only once client adoption is high enough, remove the old shape "
            f"from `{target}`. This is usually months, not days."
        )

    return steps


# --------------------------------------------------------------------------
# Command
# --------------------------------------------------------------------------


def cmd_impact(args: list[str]) -> int:
    positional = [a for a in args if not a.startswith("-")]
    as_json = "--json" in args

    if not positional:
        ui.error("which repo? usage: estate impact <repo> [endpoint]")
        return 64

    graph_file = _find_graph(Path.cwd())
    if graph_file is None:
        ui.error("no estate map found")
        ui.note("Run `estate scan <workspace>` first to build one.")
        return 1

    try:
        estate = load_map(graph_file)
    except (json.JSONDecodeError, OSError) as exc:
        ui.error(f"could not read {graph_file}: {exc}")
        return 1

    target = positional[0]
    endpoint = positional[1] if len(positional) > 1 else None

    result = blast_radius(estate, target, endpoint)
    if "error" in result:
        ui.error(result["error"])
        known = ", ".join(sorted(r.name for r in estate.repos)[:12])
        ui.note(f"Known repos: {known}")
        return 1

    if as_json:
        print(json.dumps({
            "target": result["target"],
            "endpoint": result["endpoint"],
            "affected": result["affected"],
            "landing_order": landing_order(result),
        }, indent=2))
        return 0

    _report(result)
    return 0


def _report(result: dict[str, Any]) -> None:
    target = result["target"]
    endpoint = result["endpoint"]
    heading = f"If you change {target}"
    if endpoint:
        heading = f"If you change {endpoint} in {target}"
    ui.title(heading)

    if endpoint:
        if result["matched_endpoints"]:
            for match in result["matched_endpoints"]:
                ui.item(
                    ui.INFO, f"{match.method or 'ANY'} {match.path}",
                    match.evidence,
                )
        else:
            ui.item(
                ui.WARN, f"{endpoint} is not a known endpoint of {target}",
                "showing everything that depends on the repo instead",
            )

    if not result["affected"]:
        ui.say()
        ui.item(ui.PASS, "nothing else in the estate depends on this")
        ui.summary(1, 0, 0)
        if result["unconfirmed"]:
            ui.note(
                f"But {len(result['unconfirmed'])} unconfirmed connection(s) "
                f"might point here - see ESTATE.md."
            )
            ui.say()
        return

    ui.say()
    for depth, level in enumerate(result["levels"], start=1):
        label = "Directly affected" if depth == 1 else f"Affected via {depth - 1} hop(s)"
        ui.say(f"  {label}:")
        for caller in level:
            marker = ui.WARN if caller["kind"] == "client" else ui.FAIL
            tag = {
                "client": "CLIENT APP - ships on its own release cycle",
                "legacy": "LEGACY - coordinate by hand",
            }.get(caller["kind"], caller["stack"])
            ui.item(
                marker, f"{caller['repo']}  ({tag})",
                f"calls {caller['through']} via {caller['via']} · "
                f"{caller['resolved_by']} {caller['confidence']:.2f} · "
                f"{caller['evidence']}",
            )
        ui.say()

    # Written out longhand rather than as a nested f-string: reusing the same
    # quote inside an f-string expression only became legal in Python 3.12,
    # and Estate Agent has to run on whatever Python a work laptop already has.
    total = len(result["affected"])
    client_count = len(result["clients"])
    counts = f"{total} repos affected"
    if client_count:
        counts += f", {client_count} of them client apps"
    ui.summary(0, len(result["affected"]) - len(result["clients"]), len(result["clients"]))
    ui.say(f"  {counts}")
    ui.say()

    ui.say(f"  {ui.paint('Ship in this order:', 'bold')}")
    for number, step in enumerate(landing_order(result), start=1):
        ui.say(f"    {number}. {step}")
    ui.say()

    if result["unconfirmed"]:
        ui.note(
            f"{len(result['unconfirmed'])} unconfirmed connection(s) might also "
            f"point here. Confirm them in ESTATE.md to be sure this list is "
            f"complete."
        )
        ui.say()
