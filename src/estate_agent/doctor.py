"""`estate doctor` - what is set up here, and what is missing.

This is the command you run first, and the one you run on a machine nobody
else can see. It changes nothing, sends nothing, and prints a short checklist
rather than a log.

It is also where Loop C surfaces: if the secret guard or the permission rules
are generating friction, doctor is what tells you, so a noisy rule gets tuned
instead of switched off.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from . import stacks as stacks_mod, ui
from .deed import DEED_PATH, load as load_deed
from .render import MATCHES, check_file, render_all

FRICTION_PATH = Path(".agent") / ".local" / "friction.jsonl"


def cmd_doctor(args: list[str]) -> int:
    positional = [a for a in args if not a.startswith("-")]
    root = Path(positional[0] if positional else ".").expanduser().resolve()

    if not root.is_dir():
        ui.error(f"{root} is not a directory")
        return 1

    passed = failed = warned = 0
    todo: list[str] = []

    def record(status: str) -> None:
        nonlocal passed, failed, warned
        if status == ui.PASS:
            passed += 1
        elif status == ui.FAIL:
            failed += 1
        elif status == ui.WARN:
            warned += 1

    ui.title(f"Estate Agent check-up: {root.name}")

    # -- 1. Does this repo have a deed? ------------------------------------
    deed_file = root / DEED_PATH
    deed, problems = load_deed(deed_file)
    fatal = [p for p in problems if p.fatal]

    if not deed_file.is_file():
        ui.item(ui.FAIL, "No deed", "this repo has not been set up yet")
        record(ui.FAIL)
        todo.append("estate init   to set this repo up")
        _report_detected_stack(root)
        _report_existing_context(root)
        ui.summary(passed, failed, warned)
        _print_todo(todo)
        return 1

    if fatal:
        ui.item(ui.FAIL, "Deed has errors", "\n".join(
            f"{p.field}: {p.message}" for p in fatal
        ))
        record(ui.FAIL)
        todo.append("fix .agent/estate.yaml")
    else:
        ui.item(ui.PASS, f"Deed: {deed.name} ({deed.stack or 'no stack set'})")
        record(ui.PASS)

    for warning in [p for p in problems if not p.fatal]:
        ui.item(ui.WARN, warning.field, warning.message)
        record(ui.WARN)

    # -- 2. Tier ------------------------------------------------------------
    info = deed.tier_info
    ui.item(
        ui.INFO, f"Tier {deed.tier} - {info['name']}",
        f"agents may {info['agent_may']}",
    )

    # -- 3. Commands, checked against reality (Loop A) ----------------------
    if deed.commands:
        broken = _broken_commands(root, deed.commands)
        if broken:
            ui.item(
                ui.WARN, f"{len(broken)} command(s) may not work here",
                "\n".join(broken),
            )
            record(ui.WARN)
            todo.append("estate upkeep   to fix commands that no longer exist")
        else:
            ui.item(ui.PASS, f"{len(deed.commands)} commands recorded")
            record(ui.PASS)
    else:
        ui.item(
            ui.FAIL, "No commands recorded",
            "an agent that cannot run your tests cannot check its own work",
        )
        record(ui.FAIL)
        todo.append("add build and test commands to .agent/estate.yaml")

    # -- 4. Generated context files ----------------------------------------
    if not fatal:
        results = [check_file(root, r) for r in render_all(deed)]
        matched = [r for r in results if r.state == MATCHES]
        stale = [r for r in results if r.needs_sync]
        human = [r for r in results if r.needs_a_human]

        if len(matched) == len(results):
            ui.item(ui.PASS, f"All {len(results)} assistant files match the deed")
            record(ui.PASS)
        else:
            if stale:
                ui.item(
                    ui.FAIL, f"{len(stale)} assistant file(s) out of date",
                    ", ".join(r.path for r in stale),
                )
                record(ui.FAIL)
                todo.append("estate sync   to regenerate them")
            if human:
                ui.item(
                    ui.WARN, f"{len(human)} file(s) need a human",
                    "\n".join(f"{r.path}: {r.detail}" for r in human),
                )
                record(ui.WARN)

    # -- 5. Guardrails ------------------------------------------------------
    guard = root / ".agent" / "hooks" / "secret_guard.py"
    settings_file = root / ".claude" / "settings.json"
    settings = _read_json(settings_file)

    if guard.is_file() and _guard_is_wired(settings):
        ui.item(ui.PASS, "Secret guard installed and wired up")
        record(ui.PASS)
    elif guard.is_file():
        ui.item(
            ui.FAIL, "Secret guard present but not wired up",
            "the file is there but no hook runs it, so it blocks nothing",
        )
        record(ui.FAIL)
        todo.append("estate init   to wire the guard into .claude/settings.json")
    else:
        ui.item(ui.FAIL, "No secret guard", "nothing stops a credential leaking")
        record(ui.FAIL)
        todo.append("estate init   to install the guardrails")

    permissions = ((settings.get("permissions") or {}).get("deny") or [])
    if len(permissions) >= 10:
        ui.item(ui.PASS, f"Permission profile active ({len(permissions)} deny rules)")
        record(ui.PASS)
    else:
        ui.item(
            ui.WARN, "No permission profile",
            "force-pushes, deploys and secret reads are not blocked",
        )
        record(ui.WARN)
        todo.append("estate init   to install the permission profile")

    # -- 6. The estate map --------------------------------------------------
    graph_file = _find_upwards(root, Path("estate") / "graph.json")
    if graph_file:
        try:
            data = json.loads(graph_file.read_text(encoding="utf-8"))
            mine = [
                e for e in data.get("edges", [])
                if deed.name in (e.get("from"), e.get("to"))
            ]
            ui.item(
                ui.PASS, f"Estate map found ({len(data.get('repos', []))} repos)",
                f"{len(mine)} connections involve this repo",
            )
            record(ui.PASS)
        except (json.JSONDecodeError, OSError):
            ui.item(ui.WARN, "Estate map is unreadable")
            record(ui.WARN)
    else:
        ui.item(
            ui.WARN, "No estate map",
            "agents here cannot see which services call this one",
        )
        record(ui.WARN)
        todo.append("estate scan ~/work   to map the whole estate")

    # -- 7. Loop C: is the safety layer annoying anyone? --------------------
    _report_friction(root)

    # -- 8. Estate Agent's own health --------------------------------------
    if stacks_mod.LOAD_ERRORS:
        ui.item(
            ui.WARN, "Some stack profiles failed to load",
            "\n".join(f"{name}: {why}" for name, why in stacks_mod.LOAD_ERRORS),
        )
        record(ui.WARN)

    ui.summary(passed, failed, warned)
    _print_todo(todo)
    return 1 if failed else 0


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _report_detected_stack(root: Path) -> None:
    detections = stacks_mod.detect(root)
    if detections:
        best = detections[0]
        profile = stacks_mod.get(best.stack)
        ui.item(
            ui.INFO, f"Looks like {profile.display if profile else best.stack}",
            ", ".join(best.reasons),
        )
    else:
        ui.item(
            ui.WARN, "Stack not recognised",
            "estate init will still work, but you will need to fill in the "
            "build and test commands yourself",
        )


def _report_existing_context(root: Path) -> None:
    """Reassure people before they run init: nothing gets thrown away."""
    existing = [
        name for name in (
            "CLAUDE.md", "AGENTS.md", "GEMINI.md",
            ".github/copilot-instructions.md", ".cursorrules",
        )
        if (root / name).is_file()
    ]
    if existing:
        ui.item(
            ui.INFO, f"Found {len(existing)} existing context file(s)",
            f"{', '.join(existing)}\n"
            f"`estate init` folds these into the deed. Nothing is discarded.",
        )


def _broken_commands(root: Path, commands: dict[str, str]) -> list[str]:
    """Check the first word of each command actually exists."""
    broken: list[str] = []
    for name, command in commands.items():
        first = command.strip().split()[0] if command.strip() else ""
        if not first:
            continue
        if first.startswith("./") or first.startswith("../"):
            if not (root / first).exists():
                broken.append(f"{name}: {first} does not exist in this repo")
            continue
        if first in {"cd", "source", "export", "echo", "true"}:
            continue
        if shutil.which(first) is None:
            broken.append(f"{name}: `{first}` is not on PATH")
    return broken


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _guard_is_wired(settings: dict) -> bool:
    hooks = (settings.get("hooks") or {}).get("PreToolUse") or []
    for entry in hooks:
        for hook in (entry.get("hooks") or []):
            if "secret_guard" in str(hook.get("command", "")):
                return True
    return False


def _find_upwards(start: Path, relative: Path) -> Path | None:
    for candidate in [start, *start.parents]:
        target = candidate / relative
        if target.is_file():
            return target
    return None


def _report_friction(root: Path) -> None:
    """Loop C. A guard people fight with is a guard people disable."""
    path = root / FRICTION_PATH
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

    total_blocked = sum(blocked.values())
    total_overridden = sum(overridden.values())
    if not total_blocked and not total_overridden:
        return

    ui.item(
        ui.INFO,
        f"Secret guard: {total_blocked} blocked, {total_overridden} overridden",
    )

    # An override rate above a third means the rule is probably wrong, not the
    # people. Say so, and say what to do - but never relax it automatically.
    for kind, count in sorted(overridden.items(), key=lambda kv: -kv[1])[:3]:
        attempts = count + blocked.get(kind, 0)
        if attempts >= 3 and count / attempts > 0.34:
            ui.item(
                ui.WARN, f"'{kind}' is overridden {count} of {attempts} times",
                "this rule is probably too broad. Narrow it in "
                ".agent/secret-guard-allow.txt rather than turning the guard "
                "off - Estate Agent will not relax it for you.",
            )


def _print_todo(todo: list[str]) -> None:
    if not todo:
        ui.next_step("nothing - this repo is set up")
        return
    ui.say(f"  {ui.paint('To do:', 'bold')}")
    for line in dict.fromkeys(todo):
        ui.say(f"    - {line}")
    ui.say()
