"""`estate init` - set one repo up.

The design constraint that shapes this whole file: **most repos worth setting
up already have a hand-written CLAUDE.md, and it is often good.** Someone
wrote it, and it encodes things no detector will ever infer - which team to
ask, which module is a minefield, which test is flaky.

So init never overwrites it. It reads it, pulls the commands and rules it can
recognise into the deed, keeps the rest verbatim, and only then generates.
A tool that destroys someone's writing on first run does not get a second.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from . import stacks as stacks_mod, ui, yamlite
from .deed import DEED_PATH, TIERS
from .render import UNMANAGED, check_file, render_all, render_claude, split_stamp

PACKAGE_ROOT = Path(__file__).resolve().parents[2]

EXISTING_CONTEXT_FILES = [
    "CLAUDE.md", "AGENTS.md", "GEMINI.md", ".cursorrules",
    ".github/copilot-instructions.md", ".cursor/rules/00-estate.mdc",
]

# Commands hidden in fenced blocks or inline code in a hand-written file.
_COMMAND_HINTS = {
    "test": re.compile(
        r"(?im)^\s*[-*#>\s]*(?:run\s+)?tests?\s*[:=-]\s*`?([^\n`]{3,80})`?"
    ),
    "build": re.compile(
        r"(?im)^\s*[-*#>\s]*build\s*[:=-]\s*`?([^\n`]{3,80})`?"
    ),
    "lint": re.compile(
        r"(?im)^\s*[-*#>\s]*lint\s*[:=-]\s*`?([^\n`]{3,80})`?"
    ),
    "run": re.compile(
        r"(?im)^\s*[-*#>\s]*(?:run|start|dev)\s*[:=-]\s*`?([^\n`]{3,80})`?"
    ),
}

_NEVER_LINE = re.compile(
    r"(?im)^\s*[-*]\s*((?:never|do not|don't|avoid|no)\b[^\n]{5,120})$"
)


def cmd_init(args: list[str]) -> int:
    positional = [a for a in args if not a.startswith("-")]
    root = Path(positional[0] if positional else ".").expanduser().resolve()
    force = "--force" in args
    dry_run = "--dry-run" in args

    if not root.is_dir():
        ui.error(f"{root} is not a directory")
        return 1

    ui.title(f"Setting up {root.name}")

    deed_file = root / DEED_PATH
    if deed_file.is_file() and not force:
        ui.item(
            ui.WARN, "This repo already has a deed",
            "run `estate doctor` to see its state, `estate sync` to "
            "regenerate, or `estate init --force` to rebuild the deed",
        )
        ui.say()
        return 2

    # -- 1. What is this? ---------------------------------------------------
    detections = stacks_mod.detect(root)
    profile = stacks_mod.get(detections[0].stack) if detections else None
    if profile:
        ui.item(
            ui.PASS, f"Detected {profile.display}",
            ", ".join(detections[0].reasons),
        )
        if len(detections) > 1:
            ui.item(
                ui.INFO, "Also present: "
                + ", ".join(d.stack for d in detections[1:]),
            )
    else:
        ui.item(
            ui.WARN, "Stack not recognised",
            "the deed will be written with blanks for you to fill in",
        )

    # -- 2. Read what is already here, and keep it --------------------------
    salvaged = _salvage(root)
    if salvaged["sources"]:
        ui.item(
            ui.PASS,
            f"Read {len(salvaged['sources'])} existing context file(s)",
            f"{', '.join(salvaged['sources'])}\n"
            f"kept {len(salvaged['commands'])} command(s), "
            f"{len(salvaged['never_do'])} rule(s), and the rest verbatim",
        )

    # -- 3. Build the deed --------------------------------------------------
    deed_data = _build_deed(root, profile, salvaged)

    if dry_run:
        ui.say()
        ui.say(yamlite.dump(deed_data))
        ui.next_step("run without --dry-run to write these files")
        return 0

    deed_file.parent.mkdir(parents=True, exist_ok=True)
    deed_file.write_text(yamlite.dump(deed_data), encoding="utf-8")
    ui.item(ui.PASS, str(DEED_PATH), "written")

    # -- 4. Guardrails ------------------------------------------------------
    installed = _install_guardrails(root)
    for message in installed:
        ui.item(ui.PASS, message)

    # -- 5. Generate the assistant files ------------------------------------
    from .deed import load as load_deed

    deed, problems = load_deed(deed_file)
    fatal = [p for p in problems if p.fatal]
    if fatal:
        ui.item(ui.FAIL, "The generated deed has errors", "\n".join(
            f"{p.field}: {p.message}" for p in fatal
        ))
        return 1

    preserved: list[str] = []
    for rendered in render_all(deed):
        result = check_file(root, rendered)
        if result.state == UNMANAGED:
            # Hand-written and already folded into the deed above. Keep a copy
            # so nothing is lost, then generate.
            backup = root / f"{rendered.path}.before-estate-agent"
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / rendered.path, backup)
            preserved.append(str(backup.relative_to(root)))
        target = root / rendered.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered.text, encoding="utf-8")

    ui.item(ui.PASS, f"{len(render_all(deed))} assistant files generated")
    if preserved:
        ui.item(
            ui.INFO, "Kept a copy of what was there before",
            "\n".join(preserved),
        )

    _ensure_gitignore(root)

    ui.summary(4 + len(installed), 0, 0)

    tier = TIERS[deed.tier]
    ui.note(f"Tier {deed.tier} ({tier['name']}): agents may {tier['agent_may']}.")
    ui.say()
    ui.next_step(
        "open .agent/estate.yaml and check it — especially the commands, "
        "the tier, and anything under `never_do`"
    )
    return 0


# --------------------------------------------------------------------------
# Salvage: read existing context files without destroying them
# --------------------------------------------------------------------------


def _salvage(root: Path) -> dict[str, Any]:
    """Pull what we can recognise out of hand-written context files."""
    result: dict[str, Any] = {
        "sources": [], "commands": {}, "never_do": [], "prose": "",
    }
    chunks: list[str] = []

    for name in EXISTING_CONTEXT_FILES:
        path = root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue

        recorded, body = split_stamp(text)
        if recorded is not None:
            continue  # Already ours; nothing to salvage.

        result["sources"].append(name)

        for key, pattern in _COMMAND_HINTS.items():
            if key in result["commands"]:
                continue
            match = pattern.search(body)
            if match:
                candidate = match.group(1).strip().strip("`.,")
                if 2 < len(candidate) < 80 and not candidate.startswith("<"):
                    result["commands"][key] = candidate

        for match in _NEVER_LINE.finditer(body):
            rule = match.group(1).strip().rstrip(".")
            if rule and rule not in result["never_do"]:
                result["never_do"].append(rule)

        chunks.append(f"From {name}:\n\n{body.strip()}")

    if chunks:
        result["prose"] = "\n\n---\n\n".join(chunks)
    return result


# --------------------------------------------------------------------------
# Deed construction
# --------------------------------------------------------------------------


def _build_deed(root: Path, profile, salvaged: dict[str, Any]) -> dict[str, Any]:
    commands = profile.commands_for(root) if profile else {}
    # What a human wrote beats what we inferred from the build system.
    commands.update(salvaged["commands"])

    tier = profile.tier_default if profile else 2

    repo: dict[str, Any] = {
        "name": root.name,
        "summary": _summarise(root, profile),
        "stack": profile.name if profile else "",
        "tier": tier,
    }

    data: dict[str, Any] = {
        "estate_agent_version": "0.1.0",
        "repo": repo,
        "commands": commands or {"build": "", "test": ""},
    }

    conventions = list(profile.conventions) if profile else []
    if conventions:
        data["conventions"] = conventions

    never_do = list(salvaged["never_do"])
    if profile and profile.is_legacy:
        never_do.insert(
            0, "Modify RPG, CL or DDS source - read and explain only"
        )
    if never_do:
        data["never_do"] = never_do

    contracts = _contracts(root)
    if contracts:
        data["provides"] = {"contracts": contracts}

    if profile and profile.declared_interface_template:
        data.setdefault("provides", {})["declared_interface"] = (
            profile.declared_interface_template
        )
        data["notes"] = (
            "REVIEW ME: the declared interface above is a template, not "
            "detected fact. Fill it in with the real programs, tables and "
            "queues. It is the only description of this system an agent can "
            "read.\n"
        )

    if salvaged["prose"]:
        existing = data.get("notes", "")
        data["notes"] = (
            existing
            + "Kept from the context files that were here before Estate "
              "Agent. Edit freely - this is now the source of truth.\n\n"
            + salvaged["prose"]
            + "\n"
        )

    return data


def _summarise(root: Path, profile) -> str:
    """A one-line description, from the README if there is one."""
    for name in ("README.md", "readme.md", "README.rst", "docs/README.md"):
        path = root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "!", "[", "<", "---")):
                continue
            if len(stripped) > 15:
                return re.sub(r"[`*_\[\]]", "", stripped)[:200]
    return f"{profile.display} repo." if profile else ""


def _contracts(root: Path) -> list[str]:
    from .discover import find_contracts

    return find_contracts(root)[:10]


# --------------------------------------------------------------------------
# Guardrails
# --------------------------------------------------------------------------


def _install_guardrails(root: Path) -> list[str]:
    done: list[str] = []

    # The guard is copied in, not referenced, so it keeps working on a machine
    # that cannot clone or install anything.
    source = PACKAGE_ROOT / "hooks" / "secret_guard.py"
    if source.is_file():
        target = root / ".agent" / "hooks" / "secret_guard.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        target.chmod(0o755)
        done.append(".agent/hooks/secret_guard.py installed")

    settings_file = root / ".claude" / "settings.json"
    settings = _read_json(settings_file)
    changed = False

    baseline = _read_json(PACKAGE_ROOT / "templates" / "settings" / "permissions.json")
    baseline_perms = baseline.get("permissions") or {}
    if baseline_perms:
        current = settings.setdefault("permissions", {})
        for bucket in ("deny", "ask", "allow"):
            incoming = [str(x) for x in (baseline_perms.get(bucket) or [])]
            if not incoming:
                continue
            existing = list(current.get(bucket) or [])
            merged = list(dict.fromkeys(existing + incoming))
            if merged != existing:
                current[bucket] = merged
                changed = True
        if changed:
            done.append(
                f"permission profile merged into .claude/settings.json "
                f"({len(current.get('deny', []))} deny rules)"
            )

    hooks = settings.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])
    already = any(
        "secret_guard" in str(h.get("command", ""))
        for entry in pre for h in (entry.get("hooks") or [])
    )
    if not already:
        pre.append({
            "matcher": "*",
            "hooks": [{
                "type": "command",
                "command": '"$CLAUDE_PROJECT_DIR"/.agent/hooks/secret_guard.py',
            }],
        })
        changed = True
        done.append("secret guard wired into PreToolUse")

    if changed:
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        settings_file.write_text(
            json.dumps(settings, indent=2) + "\n", encoding="utf-8"
        )

    return done


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _ensure_gitignore(root: Path) -> None:
    """`.agent/.local/` holds counters and caches; it should not be committed."""
    path = root / ".gitignore"
    line = ".agent/.local/"
    try:
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        if line in existing:
            return
        prefix = "" if existing.endswith("\n") or not existing else "\n"
        path.write_text(
            existing + prefix + "\n# Estate Agent local state (counters, cache)\n"
            + line + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass
