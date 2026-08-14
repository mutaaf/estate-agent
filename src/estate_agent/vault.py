"""`estate vault` - emit the estate as a folder of linked markdown notes.

The same map, in the shape a knowledge base wants: one note per service, per
shared piece of infrastructure, per endpoint that somebody actually calls, and
per cross-cutting concern. Notes carry YAML frontmatter and link to each other
with `[[wikilinks]]`, so the graph is the emergent result of the links rather
than something stored in a database.

Obsidian renders it. So does GitHub. `rg` searches it, and an AI agent pointed
at the folder gets cross-service context without crawling every repo. Nothing
here is Obsidian-specific; delete Obsidian and it is still a folder of
markdown in git.

Two design decisions worth knowing about, because both are load-bearing:

**Generated and human-authored notes are strictly separated.** Everything this
command writes goes under `Generated/`, carries a do-not-edit header, and is
overwritten wholesale on every run. Human notes live in sibling trees and link
*into* the generated ones. That is what stops automation and judgement from
fighting over the same file.

**Generated notes carry no timestamp.** A `last generated` field in every note
means every regeneration rewrites every file, so each run produces a full-vault
diff and the pull request is unreviewable. The generation time lives once, in
the index. A note's diff then shows only what actually changed about the
service - which is the thing you wanted to review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import ui, yamlite
from .graph import EstateMap
from .infra import InfraNode

GENERATED = "Generated"
DO_NOT_EDIT = (
    "> [!warning] Generated file\n"
    "> Written by `estate vault`. Edits here are overwritten on the next run.\n"
    "> Put human knowledge in `Investigations/`, `Decisions/`, `Runbooks/` or\n"
    "> `Concepts/` and link to this note instead.\n"
)

HUMAN_TREES = {
    "Investigations": (
        "What we learned chasing a specific problem.",
        "One note per investigation. Link the services it touched, so the next "
        "person debugging that service finds it from the service note's "
        "backlinks rather than by remembering it exists.",
    ),
    "Decisions": (
        "Why we chose this approach, and what we rejected.",
        "One note per decision. Record the alternatives and why they lost - "
        "that is the part nobody can reconstruct later, and the part an agent "
        "cannot infer from the code.",
    ),
    "Runbooks": (
        "How to reproduce, debug, or operate something.",
        "One note per procedure. Link the service and any infrastructure it "
        "touches.",
    ),
    "Concepts": (
        "Cross-cutting concerns that span services.",
        "Caching, entitlements, routing, personalisation. These are curated by "
        "hand - a concept is a judgement about what matters, not something "
        "that can be read out of the code. `estate vault` will link services "
        "to a concept automatically when `estate/concepts.yaml` lists them.",
    ),
}


def slug(text: str) -> str:
    """A filename-safe, link-stable name."""
    cleaned = re.sub(r"[^\w\s.-]", " ", str(text)).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "unnamed"


def frontmatter(fields: dict[str, Any]) -> str:
    present = {k: v for k, v in fields.items() if v not in (None, "", [], {})}
    return "---\n" + yamlite.dump(present) + "---\n\n"


def link(name: str) -> str:
    return f"[[{slug(name)}]]"


# --------------------------------------------------------------------------
# Notes
# --------------------------------------------------------------------------


def service_note(estate: EstateMap, record, concepts: dict[str, list[str]]) -> str:
    callers = estate.callers_of(record.name)
    callees = estate.callees_of(record.name)
    infra = [n for n in estate.infrastructure if record.name in n.users]
    mine = [c for c, services in concepts.items() if record.name in services]

    out = [frontmatter({
        "type": "service",
        "repo": record.name,
        "path": record.path,
        "stack": record.primary_stack or "unrecognised",
        "role": record.kind,
        "endpoints": len(record.endpoints),
        "has_deed": record.has_deed,
    })]
    out.append(DO_NOT_EDIT)
    out.append(f"\n# {record.name}\n")

    role = {
        "client": "A client application. It consumes services and exposes "
                  "nothing, and it ships on its own release cycle - a breaking "
                  "change reaches its users only after a store release, and "
                  "older versions keep calling the old shape for months.",
        "legacy": "A legacy system. Described rather than parsed: agents may "
                  "read it and write code that calls it, but not modify it.",
    }.get(record.kind, f"A {record.primary_stack or 'service'} service.")
    out.append(f"\n{role}\n")

    if callees:
        out.append("\n## Calls\n")
        for edge in callees:
            out.append(
                f"- {link(edge.target)} via {edge.via} "
                f"— {edge.method} {edge.score:.2f}, `{edge.evidence[0]}`"
            )
        out.append("")

    if callers:
        out.append("\n## Called by\n")
        for edge in callers:
            out.append(
                f"- {link(edge.source)} via {edge.via} "
                f"— {edge.method} {edge.score:.2f}, `{edge.evidence[0]}`"
            )
        out.append("")
        out.append(
            f"\nBefore changing any endpoint below, run "
            f"`estate impact {record.name} <endpoint>`.\n"
        )

    if infra:
        out.append("\n## Infrastructure\n")
        for node in infra:
            others = [u for u in node.users if u != record.name]
            shared = (
                f" — **shared with** {', '.join(link(o) for o in sorted(others))}"
                if others else ""
            )
            out.append(f"- {link(node.display)} ({node.kind}){shared}")
        out.append("")

    if record.endpoints:
        out.append("\n## Endpoints\n")
        out.append("| Method | Path | Evidence |")
        out.append("| --- | --- | --- |")
        for endpoint in record.endpoints[:80]:
            out.append(
                f"| {endpoint.method or 'ANY'} | `{endpoint.path}` "
                f"| `{endpoint.evidence}` |"
            )
        if len(record.endpoints) > 80:
            out.append(f"\n_…and {len(record.endpoints) - 80} more._")
        out.append("")

    if record.contracts:
        out.append("\n## Contracts\n")
        out += [f"- `{c}`" for c in record.contracts]
        out.append("")

    external = [x for x in estate.external if x.source == record.name]
    if external:
        out.append("\n## Outside the estate\n")
        values = sorted({x.value for x in external})
        out += [f"- `{v}`" for v in values[:20]]
        out.append("")

    if mine:
        out.append("\n## Concepts\n")
        out += [f"- {link(c)}" for c in sorted(mine)]
        out.append("")

    for note in record.notes:
        out.append(f"\n> {note}\n")

    return "\n".join(out).rstrip() + "\n"


def infrastructure_note(node: InfraNode) -> str:
    out = [frontmatter({
        "type": "infrastructure",
        "kind": node.kind,
        "technology": node.technology,
        "shared": node.is_shared,
        "used_by": sorted(node.users),
    })]
    out.append(DO_NOT_EDIT)
    out.append(f"\n# {node.display}\n")
    out.append(f"\nA {node.technology} {node.kind}.\n")

    if node.is_shared:
        out.append(
            f"\n**Shared by {len(node.users)} services.** A change to capacity, "
            f"schema, eviction policy or failover affects all of them, and an "
            f"incident here is not isolated to one team.\n"
        )
    out.append("\n## Used by\n")
    out += [f"- {link(u)}" for u in sorted(node.users)]
    out.append("\n## Evidence\n")
    out += [f"- `{e}`" for e in node.evidence[:12]]
    return "\n".join(out).rstrip() + "\n"


def endpoint_note(estate: EstateMap, owner: str, endpoint, callers) -> str:
    title = f"{owner} {endpoint.method or 'ANY'} {endpoint.path}"
    out = [frontmatter({
        "type": "endpoint",
        "service": owner,
        "method": endpoint.method or "ANY",
        "path": endpoint.path,
        "consumers": len(callers),
    })]
    out.append(DO_NOT_EDIT)
    out.append(f"\n# {title}\n")
    out.append(f"\nExposed by {link(owner)}. Declared at `{endpoint.evidence}`.\n")
    if callers:
        clients = [c for c in callers if c["kind"] == "client"]
        out.append("\n## Consumers\n")
        for caller in callers:
            marker = " **(client app)**" if caller["kind"] == "client" else ""
            certainty = (
                "" if caller.get("uses") == "this endpoint"
                else " — calls the service; which endpoint is unknown"
            )
            out.append(f"- {link(caller['repo'])}{marker}{certainty}")
        if clients:
            out.append(
                f"\n> Changing this endpoint requires expand-and-contract: "
                f"{len(clients)} client application(s) cannot be rolled "
                f"forward. Run `estate impact {owner} {endpoint.path}` for the "
                f"landing order.\n"
            )
    return "\n".join(out).rstrip() + "\n"


def concept_note(name: str, services: list[str], description: str) -> str:
    out = [frontmatter({"type": "concept", "services": sorted(services)})]
    out.append(f"\n# {name}\n")
    if description:
        out.append(f"\n{description}\n")
    out.append("\n## Services\n")
    out += [f"- {link(s)}" for s in sorted(services)]
    out.append(
        "\n---\n\n"
        "_This note is yours to edit. `estate vault` maintains the service "
        "list above from `estate/concepts.yaml`; everything else you write "
        "here is preserved._\n"
    )
    return "\n".join(out).rstrip() + "\n"


def index_note(estate: EstateMap, generated_at: str = "") -> str:
    services = [r for r in estate.repos if r.kind == "backend"]
    clients = [r for r in estate.repos if r.kind == "client"]
    legacy = [r for r in estate.repos if r.kind == "legacy"]
    shared = [n for n in estate.infrastructure if n.is_shared]

    out = [frontmatter({"type": "index"})]
    out.append(DO_NOT_EDIT)
    out.append("\n# The estate\n")
    out.append(
        f"\n{len(estate.repos)} repos · {len(estate.edges)} connections · "
        f"{len(estate.infrastructure)} pieces of infrastructure "
        f"({len(shared)} shared).\n"
    )
    out.append(
        "\nEverything under `Generated/` is written by `estate vault` and "
        "overwritten on each run. Write yours in `Investigations/`, "
        "`Decisions/`, `Runbooks/` and `Concepts/`, and link into the "
        "generated notes — the backlinks then surface your note from the "
        "service it concerns.\n"
    )

    for heading, group in (
        ("Services", services), ("Client apps", clients),
        ("Legacy systems", legacy),
    ):
        if not group:
            continue
        out.append(f"\n## {heading}\n")
        out += [f"- {link(r.name)}" for r in sorted(group, key=lambda r: r.name)]

    if estate.infrastructure:
        out.append("\n## Infrastructure\n")
        for node in estate.infrastructure:
            tag = f" — shared by {len(node.users)}" if node.is_shared else ""
            out.append(f"- {link(node.display)} ({node.kind}){tag}")

    if estate.unresolved:
        out.append("\n## Needs confirming\n")
        out.append(
            f"\n{len(estate.unresolved)} connection(s) could not be pinned to "
            f"one service. Answer one in the calling repo's "
            f"`.agent/estate.yaml` under `consumes:` and it stops being "
            f"asked.\n"
        )
        for item in estate.unresolved[:25]:
            out.append(
                f"- {link(item.source)} → `{item.value}` — {item.reason} "
                f"(`{item.evidence}`)"
            )

    out.append("\n---\n")
    out.append(
        f"\n_Generated by Estate Agent. Individual notes carry no timestamp "
        f"on purpose: a per-note `last generated` field makes every "
        f"regeneration rewrite every file, and the diff becomes unreviewable._\n"
    )
    return "\n".join(out).rstrip() + "\n"


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


@dataclass
class VaultResult:
    written: int = 0
    removed: int = 0
    preserved: int = 0
    root: Path | None = None


def load_concepts(workspace: Path) -> dict[str, dict[str, Any]]:
    """Optional `estate/concepts.yaml`. Curated by hand, by design.

    A concept is a judgement about what matters across services. Nothing in
    the code says "this is the caching story", so nothing is inferred here.
    """
    path = workspace / "estate" / "concepts.yaml"
    if not path.is_file():
        return {}
    try:
        data = yamlite.load(path.read_text(encoding="utf-8"))
    except (yamlite.YamliteError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    concepts: dict[str, dict[str, Any]] = {}
    for item in data.get("concepts") or []:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        concepts[str(item["name"])] = {
            "services": [str(s) for s in (item.get("services") or [])],
            "description": str(item.get("description") or ""),
        }
    return concepts


def write(estate: EstateMap, out: Path, generated_at: str = "") -> VaultResult:
    result = VaultResult(root=out)
    generated_root = out / GENERATED

    # Wholesale regeneration: remove the old generated tree first, so a
    # service that has been deleted does not linger as a note nobody notices.
    if generated_root.exists():
        for path in sorted(generated_root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
                result.removed += 1
            elif path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    pass

    workspace = Path(estate.workspace) if estate.workspace else out
    concept_config = load_concepts(workspace)
    concept_services = {
        name: config["services"] for name, config in concept_config.items()
    }

    def emit(relative: str, text: str) -> None:
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_tidy(text), encoding="utf-8")
        result.written += 1

    emit(f"{GENERATED}/Estate.md", index_note(estate))
    emit("README.md", _vault_readme(estate, generated_at))

    for record in estate.repos:
        emit(
            f"{GENERATED}/Services/{slug(record.name)}.md",
            service_note(estate, record, concept_services),
        )

    for node in estate.infrastructure:
        emit(
            f"{GENERATED}/Infrastructure/{slug(node.display)}.md",
            infrastructure_note(node),
        )

    # An endpoint note only earns its place when something calls it. Emitting
    # one per route would bury the vault in notes with no links, which is
    # exactly how a knowledge base becomes noise nobody reads.
    from .impact import blast_radius

    for record in estate.repos:
        for endpoint in record.endpoints:
            result_map = blast_radius(estate, record.name, endpoint.path)
            callers = result_map.get("affected") or []
            if not callers:
                continue
            name = slug(f"{record.name} {endpoint.method or 'ANY'} {endpoint.path}")
            emit(f"{GENERATED}/Endpoints/{name}.md",
                 endpoint_note(estate, record.name, endpoint, callers))

    # Human trees: scaffolded, never overwritten.
    for tree, (summary, guidance) in HUMAN_TREES.items():
        readme = out / tree / "README.md"
        if readme.exists():
            result.preserved += 1
            continue
        readme.parent.mkdir(parents=True, exist_ok=True)
        readme.write_text(
            f"# {tree}\n\n{summary}\n\n{guidance}\n", encoding="utf-8"
        )
        result.written += 1

    for name, config in concept_config.items():
        path = out / "Concepts" / f"{slug(name)}.md"
        if path.exists():
            # Human-authored. Only the service list is maintained, and only
            # when it is safe to do so.
            result.preserved += 1
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            concept_note(name, config["services"], config["description"]),
            encoding="utf-8",
        )
        result.written += 1

    return result


def _tidy(text: str) -> str:
    """Collapse runs of blank lines. A vault people actually read should not
    look like it was assembled by string concatenation, even though it was."""
    return re.sub(r"\n{3,}", "\n\n", text).rstrip() + "\n"


def _vault_readme(estate: EstateMap, generated_at: str) -> str:
    return (
        "# Estate vault\n\n"
        "A folder of linked markdown describing how these services fit "
        "together. Open it in Obsidian for the graph view and backlinks, read "
        "it on GitHub, search it with `rg`, or point an AI agent at it.\n\n"
        "```\n"
        "Generated/       written by `estate vault`, overwritten every run\n"
        "  Services/      one note per repo\n"
        "  Infrastructure/  shared clusters, caches, datastores\n"
        "  Endpoints/     one note per endpoint that something calls\n"
        "Concepts/        curated cross-cutting concerns\n"
        "Investigations/  what we learned chasing a problem\n"
        "Decisions/       why we chose this, and what we rejected\n"
        "Runbooks/        how to reproduce, debug, operate\n"
        "```\n\n"
        "**The one rule:** never edit anything under `Generated/`. It is "
        "overwritten wholesale. Write in the human trees and link *into* the "
        "generated notes — backlinks then surface your note from the service "
        "it concerns, which is the whole point.\n\n"
        f"Regenerate with `estate scan <workspace> && estate vault "
        f"<workspace>`.\n\n"
        f"_Last generated: {generated_at or 'unknown'}. Individual notes carry "
        f"no timestamp, so a regeneration diff shows only what actually "
        f"changed._\n"
    )


# --------------------------------------------------------------------------
# Command
# --------------------------------------------------------------------------


def cmd_vault(args: list[str]) -> int:
    import json
    from datetime import datetime

    from .impact import _find_graph, load_map

    positional = [a for a in args if not a.startswith("-")]
    workspace = Path(positional[0] if positional else ".").expanduser().resolve()

    out = workspace / "vault"
    if "--out" in args:
        out = Path(args[args.index("--out") + 1]).expanduser().resolve()

    graph_file = _find_graph(workspace)
    if graph_file is None:
        ui.error("no estate map found")
        ui.note(f"Run `estate scan {workspace}` first to build one.")
        return 1

    try:
        estate = load_map(graph_file)
    except (json.JSONDecodeError, OSError) as exc:
        ui.error(f"could not read {graph_file}: {exc}")
        return 1

    ui.title(f"Writing the vault to {out}")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    result = write(estate, out, stamp)

    ui.item(ui.PASS, f"{result.written} notes written")
    if result.preserved:
        ui.item(
            ui.INFO, f"{result.preserved} human-authored file(s) left alone",
            "Concepts/ and the human trees are never overwritten",
        )
    shared = [n for n in estate.infrastructure if n.is_shared]
    if shared:
        ui.item(
            ui.WARN, f"{len(shared)} shared piece(s) of infrastructure",
            "\n".join(
                f"{n.display} — used by {', '.join(sorted(n.users))}"
                for n in shared[:5]
            ),
        )
    ui.summary(result.written, 0, len(shared))
    ui.note("Open the folder in Obsidian, or read it on GitHub.")
    ui.say()
    ui.next_step(
        "write what the code cannot say — an investigation, a decision, a "
        "runbook — and link it to a service"
    )
    return 0
