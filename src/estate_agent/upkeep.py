"""`estate upkeep` - find what has gone stale and repair what is safe.

Every effort like this dies the same death: accurate the week it is written,
quietly wrong six months later, at which point an agent acts on it
confidently and is wrong fast. So repair is a feature rather than a chore.

What this command will do on its own:

  * regenerate assistant files whose deed has moved on
  * drop references to repos that no longer exist
  * prune map connections whose evidence file has been deleted
  * migrate a deed written by an older version of Estate Agent

What it will never do, and the reasons are not stylistic:

  1. Overwrite a hand-edited file. It offers to promote the edit instead.
     Destroying someone's writing once loses their trust permanently.
  2. Relax a safety rule. Auto-tuning may suggest; only a human applies.
     Anything else means the guardrails erode by themselves.
  3. Touch source code. Only Estate Agent's own files are in scope.
  4. Leave an old repo behind. Migrations run so a repo set up months ago
     keeps working after the tool changes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import ui, yamlite
from .deed import DEED_PATH, load as load_deed
from .doctor import _broken_commands, _find_upwards
from .render import (
    HAND_EDITED, MATCHES, UNMANAGED, VERSION, check_file, render_all,
    split_stamp,
)

CURRENT_VERSION = VERSION


@dataclass
class Repair:
    what: str
    detail: str = ""


@dataclass
class Report:
    fixed: list[Repair] = field(default_factory=list)
    needs_a_human: list[Repair] = field(default_factory=list)
    suggestions: list[Repair] = field(default_factory=list)
    checked: int = 0


def cmd_upkeep(args: list[str]) -> int:
    positional = [a for a in args if not a.startswith("-")]
    root = Path(positional[0] if positional else ".").expanduser().resolve()
    dry_run = "--dry-run" in args

    deed_file = root / DEED_PATH
    if not deed_file.is_file():
        ui.error(f"no deed at {deed_file}")
        ui.note("Run `estate init` here first.")
        return 1

    ui.title(f"Upkeep: {root.name}" + ("  (dry run)" if dry_run else ""))
    report = Report()

    _migrate(root, deed_file, report, dry_run)
    _check_commands(root, report)
    _prune_missing_repos(root, deed_file, report, dry_run)
    _resync(root, report, dry_run)
    _prune_stale_evidence(root, report, dry_run)
    _suggest_guard_tuning(root, report)

    for repair in report.fixed:
        ui.item(ui.PASS, repair.what, repair.detail)
    for repair in report.needs_a_human:
        ui.item(ui.WARN, repair.what, repair.detail)
    for repair in report.suggestions:
        ui.item(ui.INFO, repair.what, repair.detail)

    if not report.fixed and not report.needs_a_human:
        ui.item(ui.PASS, "Nothing has gone stale")

    ui.summary(len(report.fixed), 0, len(report.needs_a_human))

    if dry_run:
        ui.next_step("run without --dry-run to apply the fixes above")
    elif report.needs_a_human:
        ui.note("The warnings above need a decision - Estate Agent will not")
        ui.note("guess at them, and will never relax a safety rule for you.")
        ui.say()
        ui.next_step("resolve the warnings, then run upkeep again")
    elif report.fixed:
        ui.next_step("review the diff and commit it")
    else:
        ui.next_step("nothing to do")

    return 0


# --------------------------------------------------------------------------
# Rule 4: old setups do not rot
# --------------------------------------------------------------------------


def _migrate(root: Path, deed_file: Path, report: Report, dry_run: bool) -> None:
    try:
        data = yamlite.load(deed_file.read_text(encoding="utf-8"))
    except (yamlite.YamliteError, OSError) as exc:
        report.needs_a_human.append(Repair(
            "The deed could not be parsed", str(exc)
        ))
        return
    if not isinstance(data, dict):
        return

    was = str(data.get("estate_agent_version") or "0.0.0")
    if was == CURRENT_VERSION:
        return

    changed = _apply_migrations(data, was)
    data["estate_agent_version"] = CURRENT_VERSION

    if not dry_run:
        deed_file.write_text(yamlite.dump(data), encoding="utf-8")
    report.fixed.append(Repair(
        f"Deed migrated from {was} to {CURRENT_VERSION}",
        "; ".join(changed) if changed else "no format changes were needed",
    ))


def _apply_migrations(data: dict[str, Any], from_version: str) -> list[str]:
    """Each migration is a small, named, idempotent step.

    There are none yet - 0.1.0 is the first release. The machinery is here
    from the start because retro-fitting migrations onto files already in a
    hundred repos is the kind of thing that never gets done.
    """
    applied: list[str] = []
    return applied


# --------------------------------------------------------------------------
# Loop A: do the notes still match reality?
# --------------------------------------------------------------------------


def _check_commands(root: Path, report: Report) -> None:
    deed, _problems = load_deed(root / DEED_PATH)
    if not deed.commands:
        report.needs_a_human.append(Repair(
            "No commands recorded",
            "an agent cannot verify its own work here - add build and test "
            "to .agent/estate.yaml",
        ))
        return
    report.checked += len(deed.commands)
    broken = _broken_commands(root, deed.commands)
    if broken:
        # Deliberately not auto-fixed: the right replacement is a judgement
        # call, and silently rewriting someone's build command is worse than
        # telling them it is wrong.
        report.needs_a_human.append(Repair(
            f"{len(broken)} command(s) no longer work",
            "\n".join(broken)
            + "\nFix them in .agent/estate.yaml, then run `estate sync`.",
        ))


def _prune_missing_repos(
    root: Path, deed_file: Path, report: Report, dry_run: bool
) -> None:
    """A related repo that has been deleted or renamed is worse than none."""
    deed, _problems = load_deed(deed_file)
    if not deed.related_repos:
        return

    workspace = root.parent
    missing = [
        name for name in deed.related_repos
        if not (workspace / name).is_dir()
    ]
    if not missing:
        return

    graph_file = _find_upwards(root, Path("estate") / "graph.json")
    known: set[str] = set()
    if graph_file:
        try:
            data = json.loads(graph_file.read_text(encoding="utf-8"))
            known = {r.get("name", "") for r in data.get("repos", [])}
        except (json.JSONDecodeError, OSError):
            pass

    # Only drop a repo that is missing from disk *and* absent from the map.
    gone = [name for name in missing if name not in known]
    if not gone:
        return

    try:
        data = yamlite.load(deed_file.read_text(encoding="utf-8"))
    except (yamlite.YamliteError, OSError):
        return
    if not isinstance(data, dict):
        return
    remaining = [r for r in deed.related_repos if r not in gone]
    if remaining:
        data["related_repos"] = remaining
    else:
        data.pop("related_repos", None)

    if not dry_run:
        deed_file.write_text(yamlite.dump(data), encoding="utf-8")
    report.fixed.append(Repair(
        f"Dropped {len(gone)} related repo(s) that no longer exist",
        ", ".join(gone),
    ))


def _resync(root: Path, report: Report, dry_run: bool) -> None:
    """Rule 1 lives here: stale is regenerated, hand-edited never is."""
    deed, problems = load_deed(root / DEED_PATH)
    if [p for p in problems if p.fatal]:
        return

    regenerated: list[str] = []
    for rendered in render_all(deed):
        result = check_file(root, rendered)
        report.checked += 1

        if result.state == MATCHES:
            continue

        if result.state == HAND_EDITED:
            report.needs_a_human.append(Repair(
                f"{rendered.path} was edited by hand",
                _promotion_advice(root, rendered),
            ))
            continue

        if result.state == UNMANAGED:
            report.needs_a_human.append(Repair(
                f"{rendered.path} was written by hand, not by Estate Agent",
                "run `estate init --force` to fold its content into the deed",
            ))
            continue

        if not dry_run:
            target = root / rendered.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered.text, encoding="utf-8")
        regenerated.append(rendered.path)

    if regenerated:
        report.fixed.append(Repair(
            f"Regenerated {len(regenerated)} assistant file(s)",
            ", ".join(regenerated),
        ))


def _promotion_advice(root: Path, rendered) -> str:
    """Show the human what they added, so promoting it is a copy and paste."""
    try:
        on_disk = (root / rendered.path).read_text(encoding="utf-8")
    except OSError:
        return "could not read the file to compare"

    _sha, disk_body = split_stamp(on_disk)
    _fresh_sha, fresh_body = split_stamp(rendered.text)

    generated_lines = set(fresh_body.splitlines())
    added = [
        line for line in disk_body.splitlines()
        if line.strip() and line not in generated_lines
    ]
    if not added:
        return "the edit could not be isolated - compare it against git history"

    preview = "\n".join(f"  {line}" for line in added[:8])
    more = f"\n  ... and {len(added) - 8} more line(s)" if len(added) > 8 else ""
    return (
        "This file has not been touched. The lines below are yours:\n"
        f"{preview}{more}\n"
        "Move them into .agent/estate.yaml (`notes:` or `conventions:`), then "
        "run `estate sync`."
    )


def _prune_stale_evidence(root: Path, report: Report, dry_run: bool) -> None:
    """A connection whose proof has been deleted is no longer proven."""
    graph_file = _find_upwards(root, Path("estate") / "graph.json")
    if graph_file is None:
        return
    workspace = graph_file.parent.parent

    try:
        data = json.loads(graph_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    paths_by_repo = {
        r.get("name", ""): r.get("path", "") for r in data.get("repos", [])
    }
    edges = data.get("edges", [])
    survivors: list[dict[str, Any]] = []
    dropped: list[str] = []

    for edge in edges:
        evidence = edge.get("evidence") or []
        repo_path = paths_by_repo.get(edge.get("from", ""), "")
        alive = []
        for item in evidence:
            file_part = str(item).rsplit(":", 1)[0]
            if (workspace / repo_path / file_part).exists():
                alive.append(item)
        if alive or not evidence:
            edge["evidence"] = alive or evidence
            survivors.append(edge)
        else:
            dropped.append(
                f"{edge.get('from')} -> {edge.get('to')} "
                f"(proof was {evidence[0]})"
            )

    if not dropped:
        return

    data["edges"] = survivors
    if not dry_run:
        graph_file.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )
    report.fixed.append(Repair(
        f"Dropped {len(dropped)} connection(s) whose evidence is gone",
        "\n".join(dropped[:5])
        + ("\n..." if len(dropped) > 5 else "")
        + "\nRun `estate scan` to rebuild the map properly.",
    ))


# --------------------------------------------------------------------------
# Loop C: suggest, never apply (rule 2)
# --------------------------------------------------------------------------


def _suggest_guard_tuning(root: Path, report: Report) -> None:
    path = root / ".agent" / ".local" / "friction.jsonl"
    if not path.is_file():
        return

    blocked: dict[str, int] = {}
    overridden: dict[str, int] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = str(entry.get("kind") or "unknown")
            if entry.get("event") == "blocked":
                blocked[kind] = blocked.get(kind, 0) + 1
            elif entry.get("event") == "allowlisted":
                overridden[kind] = overridden.get(kind, 0) + 1
    except OSError:
        return

    for kind, count in sorted(overridden.items(), key=lambda kv: -kv[1])[:3]:
        attempts = count + blocked.get(kind, 0)
        if attempts >= 3 and count / attempts > 0.34:
            report.suggestions.append(Repair(
                f"Suggestion: '{kind}' is overridden {count} of {attempts} times",
                "That rule is probably too broad for this repo. Narrowing it "
                "is a decision for you - Estate Agent only ever tightens or "
                "reports, and will not relax a safety rule on its own.",
            ))
