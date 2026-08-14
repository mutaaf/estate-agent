"""Command dispatch for `estate`.

Commands are literal and boring on purpose. The name of the project is a pun;
the interface people type fifty times a day should not be.
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import ui
from .deed import DEED_PATH, find_deed, load as load_deed
from .render import (
    HAND_EDITED, MATCHES, MISSING, STALE, UNMANAGED, check_file, render_all,
)

VERSION = "0.1.0"

USAGE = """estate - the standard for AI agents working across your repo estate

  Set up a repo
    estate init [path]        set this repo up: detect the stack, write the
                              deed, install the guardrails, generate the files
    estate doctor [path]      what is set up here and what is missing

  Keep it true
    estate sync [path]        regenerate the assistant files from the deed
    estate check [path]       fail if anything has drifted (use this in CI)
    estate upkeep [path]      find what has gone stale and repair what is safe

  Map the estate
    estate scan [workspace]   find every repo and map which services call which
    estate impact <repo> [endpoint]
                              what breaks if you change this
    estate vault [workspace]  write the estate as linked markdown notes
                              (Obsidian, GitHub, rg, or an AI agent)

  Report a problem, or extend it
    estate report [workspace] a diagnostic with names and paths removed,
                              safe to attach to a bug report
    estate contribute stack <repo>
                              scaffold a profile for a language it does
                              not cover yet, redacted for sharing
    estate contribute check <profile.yaml> [repo]
                              validate a profile and try it on real code

  Other
    estate version
    estate help [command]

Start with `estate doctor`. It tells you where you are before it changes
anything.
"""


def resolve_root(args: list[str]) -> Path:
    """Commands accept an optional path; default to the enclosing repo."""
    if args and not args[0].startswith("-"):
        return Path(args[0]).expanduser().resolve()
    found = find_deed(Path.cwd())
    if found:
        return found.parent.parent
    return Path.cwd()


# --------------------------------------------------------------------------
# sync
# --------------------------------------------------------------------------


def cmd_sync(args: list[str]) -> int:
    root = resolve_root(args)
    force = "--force" in args
    deed_file = root / DEED_PATH

    deed, problems = load_deed(deed_file)
    fatal = [p for p in problems if p.fatal]
    if fatal:
        ui.title(f"Cannot read the deed at {deed_file}")
        for problem in fatal:
            ui.item(ui.FAIL, problem.message, problem.field)
        ui.next_step("fix .agent/estate.yaml, or run `estate init` to rebuild it")
        return 1

    ui.title(f"Generating assistant files for {deed.name or root.name}")

    written = skipped = unchanged = 0
    blocked: list[str] = []

    for rendered in render_all(deed):
        result = check_file(root, rendered)

        if result.state == MATCHES:
            ui.item(ui.INFO, rendered.path, "already up to date")
            unchanged += 1
            continue

        if result.needs_a_human and not force:
            # The rule that keeps self-healing from becoming self-harm.
            ui.item(ui.WARN, rendered.path, result.detail)
            blocked.append(rendered.path)
            skipped += 1
            continue

        target = root / rendered.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered.text, encoding="utf-8")
        ui.item(
            ui.PASS, rendered.path,
            "created" if result.state == MISSING else "updated",
        )
        written += 1

    ui.summary(written + unchanged, 0, skipped)

    if blocked:
        ui.note("These files were left alone because someone edited them by hand.")
        ui.note("Move the edit into .agent/estate.yaml, then run sync again.")
        ui.note("To overwrite anyway (this discards the edit): estate sync --force")
        ui.say()
        return 2

    if written:
        ui.next_step("commit the generated files alongside the deed")
    else:
        ui.next_step("nothing to do - everything already matches the deed")
    return 0


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------


def cmd_check(args: list[str]) -> int:
    """Exit non-zero on drift. Designed to be wired into CI."""
    root = resolve_root(args)
    quiet = "--quiet" in args
    deed_file = root / DEED_PATH

    deed, problems = load_deed(deed_file)
    fatal = [p for p in problems if p.fatal]
    if fatal:
        if not quiet:
            ui.title("Deed problems")
            for problem in fatal:
                ui.item(ui.FAIL, f"{problem.field}: {problem.message}")
            ui.summary(0, len(fatal))
        return 1

    results = [check_file(root, r) for r in render_all(deed)]
    stale = [r for r in results if r.needs_sync]
    human = [r for r in results if r.needs_a_human]
    warnings = [p for p in problems if not p.fatal]

    if not quiet:
        ui.title(f"Checking {deed.name or root.name}")
        for result in results:
            if result.state == MATCHES:
                ui.item(ui.PASS, result.path)
            elif result.state in (STALE, MISSING):
                ui.item(ui.FAIL, result.path, result.detail)
            else:
                ui.item(ui.WARN, result.path, result.detail)
        for warning in warnings:
            ui.item(ui.WARN, warning.field, warning.message)
        ui.summary(
            len(results) - len(stale) - len(human),
            len(stale),
            len(human) + len(warnings),
        )
        if stale:
            ui.next_step("run `estate sync` and commit the result")
        elif human:
            ui.next_step(
                "move the hand-edits into .agent/estate.yaml, then `estate sync`"
            )
        else:
            ui.next_step("nothing to do")

    return 1 if stale else 0


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def cmd_version(_args: list[str]) -> int:
    print(f"estate {VERSION}")
    return 0


def cmd_help(args: list[str]) -> int:
    print(USAGE)
    return 0


def _not_built_yet(name: str):
    def run(_args: list[str]) -> int:
        ui.error(f"`estate {name}` is not implemented in this build yet")
        return 1
    return run


COMMANDS = {
    "sync": cmd_sync,
    "check": cmd_check,
    "version": cmd_version,
    "help": cmd_help,
    "--version": cmd_version,
    "-h": cmd_help,
    "--help": cmd_help,
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(USAGE)
        return 0

    name, args = argv[0], argv[1:]

    # Late imports so a broken optional module cannot stop `estate check`
    # from running in CI.
    if name == "doctor":
        from .doctor import cmd_doctor
        return cmd_doctor(args)
    if name == "init":
        from .initialise import cmd_init
        return cmd_init(args)
    if name in ("scan", "map"):
        from .scan import cmd_scan
        return cmd_scan(args)
    if name == "impact":
        from .impact import cmd_impact
        return cmd_impact(args)
    if name == "upkeep":
        from .upkeep import cmd_upkeep
        return cmd_upkeep(args)
    if name == "vault":
        from .vault import cmd_vault
        return cmd_vault(args)
    if name == "report":
        from .report import cmd_report
        return cmd_report(args)
    if name == "contribute":
        from .contribute import cmd_contribute
        return cmd_contribute(args)

    handler = COMMANDS.get(name)
    if handler is None:
        ui.error(f"unknown command `{name}`")
        ui.say()
        print(USAGE)
        return 64

    try:
        return handler(args)
    except KeyboardInterrupt:
        ui.say()
        return 130
    except BrokenPipeError:
        return 0
