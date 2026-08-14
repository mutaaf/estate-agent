"""The deed: one file per repo that every AI assistant reads from.

`.agent/estate.yaml` is the single source of truth. Five assistant-specific
context files are generated from it, so there is exactly one place to edit and
no way for the five to drift apart.

The name is deliberate. A deed is the authoritative record of a property, it
is short, and someone signs it. The same should be true of this file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import yamlite

DEED_PATH = Path(".agent") / "estate.yaml"

# Tiers decide how much rope an agent gets. Written out here because this is
# the field with real consequences, and people should not have to read the
# docs to understand what they just set.
TIERS: dict[int, dict[str, str]] = {
    1: {
        "name": "Restricted",
        "agent_may": "read the code, explain it, and propose changes in "
                     "conversation",
        "agent_may_not": "write to any file, open a pull request, or run "
                         "anything that mutates state",
        "why": "regulated, customer-data-bearing, or effectively untestable "
               "(legacy systems such as AS400 default here)",
    },
    2: {
        "name": "Reviewed",
        "agent_may": "edit code and open pull requests",
        "agent_may_not": "merge anything - every change needs passing CI and "
                         "a human reviewer",
        "why": "the normal setting for a service with tests and a review "
               "process",
    },
    3: {
        "name": "Autonomous",
        "agent_may": "edit, open pull requests, and merge when CI is green",
        "agent_may_not": "bypass CI or touch another repo's deed",
        "why": "internal tooling, docs, and scripts where a bad change is "
               "cheap to revert",
    },
}

VALID_VIA = {"rest", "grpc", "graphql", "queue", "database", "file", "unknown"}

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._\-]*$", re.IGNORECASE)


@dataclass
class Problem:
    """A validation finding. `fatal` means the deed cannot be used."""

    field: str
    message: str
    fatal: bool = True

    def __str__(self) -> str:
        mark = "error" if self.fatal else "warning"
        return f"{mark}: {self.field}: {self.message}"


@dataclass
class Deed:
    """A validated deed. Missing optional sections come back as empty."""

    name: str = ""
    summary: str = ""
    stack: str = ""
    tier: int = 2
    owners: list[str] = field(default_factory=list)
    commands: dict[str, str] = field(default_factory=dict)
    conventions: list[str] = field(default_factory=list)
    never_do: list[str] = field(default_factory=list)
    architecture: str = ""
    provides: dict[str, Any] = field(default_factory=dict)
    consumes: list[dict[str, Any]] = field(default_factory=list)
    related_repos: list[str] = field(default_factory=list)
    notes: str = ""
    version: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    # ---- derived helpers used by the renderers ---------------------------

    @property
    def tier_info(self) -> dict[str, str]:
        return TIERS.get(self.tier, TIERS[2])

    @property
    def contracts(self) -> list[str]:
        value = self.provides.get("contracts") or []
        return [str(v) for v in value]

    @property
    def endpoints(self) -> list[dict[str, Any]]:
        value = self.provides.get("endpoints") or []
        return [v for v in value if isinstance(v, dict)]

    def to_dict(self) -> dict[str, Any]:
        """Serialise back to the on-disk shape, dropping empty sections."""
        data: dict[str, Any] = {"estate_agent_version": self.version or "0.1.0"}
        repo: dict[str, Any] = {"name": self.name}
        if self.summary:
            repo["summary"] = self.summary
        repo["stack"] = self.stack
        repo["tier"] = self.tier
        if self.owners:
            repo["owners"] = self.owners
        data["repo"] = repo
        if self.commands:
            data["commands"] = self.commands
        if self.conventions:
            data["conventions"] = self.conventions
        if self.never_do:
            data["never_do"] = self.never_do
        if self.architecture:
            data["architecture"] = self.architecture
        if self.provides:
            data["provides"] = self.provides
        if self.consumes:
            data["consumes"] = self.consumes
        if self.related_repos:
            data["related_repos"] = self.related_repos
        if self.notes:
            data["notes"] = self.notes
        data.update(self.extra)
        return data

    def to_yaml(self) -> str:
        return yamlite.dump(self.to_dict())


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value).strip()] if str(value).strip() else []


def parse(data: Any) -> tuple[Deed, list[Problem]]:
    """Turn loaded YAML into a Deed plus a list of problems.

    Always returns a Deed, even when there are fatal problems, so callers can
    report everything wrong at once instead of one error per run.
    """
    problems: list[Problem] = []
    if not isinstance(data, dict):
        return Deed(), [Problem("deed", "file is empty or not a mapping")]

    known_top = {
        "estate_agent_version", "repo", "commands", "conventions", "never_do",
        "architecture", "provides", "consumes", "related_repos", "notes",
    }
    repo = data.get("repo")
    if not isinstance(repo, dict):
        problems.append(Problem("repo", "missing - the deed needs a `repo:` section"))
        repo = {}

    deed = Deed(
        version=str(data.get("estate_agent_version") or ""),
        name=str(repo.get("name") or "").strip(),
        summary=str(repo.get("summary") or "").strip(),
        stack=str(repo.get("stack") or "").strip(),
        owners=_as_list(repo.get("owners")),
        conventions=_as_list(data.get("conventions")),
        never_do=_as_list(data.get("never_do")),
        architecture=str(data.get("architecture") or "").strip(),
        related_repos=_as_list(data.get("related_repos")),
        notes=str(data.get("notes") or "").strip(),
        extra={k: v for k, v in data.items() if k not in known_top},
    )

    # -- name --------------------------------------------------------------
    if not deed.name:
        problems.append(Problem("repo.name", "missing"))
    elif not _NAME_RE.match(deed.name):
        problems.append(Problem(
            "repo.name",
            f"'{deed.name}' should look like a repo directory name "
            f"(letters, digits, dot, dash, underscore)",
        ))

    # -- stack -------------------------------------------------------------
    if not deed.stack:
        # A warning, not an error. A repo whose stack Estate Agent does not
        # recognise still benefits from everything else in the deed - the
        # summary, the never-do list, the tier, the estate connections - and
        # nothing in rendering needs the stack. Treating this as fatal meant
        # `init` announced "the deed will be written with blanks for you to
        # fill in" and then refused to continue because of those blanks,
        # leaving the repo half set up. Found by running it on a shell repo.
        problems.append(Problem(
            "repo.stack",
            "not recognised - set it by hand if you know it, or add a stack "
            "profile. Everything else still works.",
            fatal=False,
        ))

    # -- tier --------------------------------------------------------------
    raw_tier = repo.get("tier", 2)
    try:
        deed.tier = int(raw_tier)
    except (TypeError, ValueError):
        problems.append(Problem("repo.tier", f"'{raw_tier}' is not a number"))
        deed.tier = 2
    if deed.tier not in TIERS:
        problems.append(Problem(
            "repo.tier",
            f"{deed.tier} is not a tier. Use 1 (restricted), 2 (reviewed) "
            f"or 3 (autonomous)",
        ))
        deed.tier = 2

    # -- commands ----------------------------------------------------------
    commands = data.get("commands")
    if commands is None:
        problems.append(Problem(
            "commands",
            "missing - without a test command an agent cannot check its own "
            "work, which is the single biggest cause of bad agent changes",
            fatal=False,
        ))
    elif not isinstance(commands, dict):
        problems.append(Problem("commands", "should be a mapping of name to command"))
    else:
        deed.commands = {
            str(k): str(v).strip()
            for k, v in commands.items()
            if v is not None and str(v).strip()
        }
        if "test" not in deed.commands:
            problems.append(Problem(
                "commands.test",
                "no test command - the agent cannot verify its own changes",
                fatal=False,
            ))
        # Deliberately no warning for a missing build command. Most repos -
        # scripts, libraries, most Python and Node services - have no build
        # step, and warning about it on every run trains people to ignore the
        # warnings that matter. The test command is the one worth insisting on.

    # -- provides ----------------------------------------------------------
    provides = data.get("provides")
    if provides is not None:
        if not isinstance(provides, dict):
            problems.append(Problem("provides", "should be a mapping"))
        else:
            deed.provides = provides
            for i, endpoint in enumerate(provides.get("endpoints") or []):
                if not isinstance(endpoint, dict):
                    problems.append(Problem(
                        f"provides.endpoints[{i}]",
                        "should be a mapping with `path:` and optionally `method:`",
                    ))
                elif not endpoint.get("path"):
                    problems.append(Problem(
                        f"provides.endpoints[{i}]", "missing `path:`"
                    ))

    # -- consumes ----------------------------------------------------------
    consumes = data.get("consumes")
    if consumes is not None:
        if not isinstance(consumes, list):
            problems.append(Problem("consumes", "should be a list"))
        else:
            for i, item in enumerate(consumes):
                if not isinstance(item, dict):
                    problems.append(Problem(
                        f"consumes[{i}]",
                        "should be a mapping with at least `service:`",
                    ))
                    continue
                if not item.get("service"):
                    problems.append(Problem(f"consumes[{i}]", "missing `service:`"))
                via = str(item.get("via") or "unknown").lower()
                if via not in VALID_VIA:
                    problems.append(Problem(
                        f"consumes[{i}].via",
                        f"'{via}' is not one of {', '.join(sorted(VALID_VIA))}",
                        fatal=False,
                    ))
                deed.consumes.append(item)

    return deed, problems


def load(path: Path) -> tuple[Deed, list[Problem]]:
    """Read and validate a deed from disk."""
    if not path.is_file():
        return Deed(), [Problem(
            str(path),
            "no deed here yet - run `estate init` in this repo",
        )]
    try:
        raw = yamlite.load(path.read_text(encoding="utf-8"))
    except yamlite.YamliteError as exc:
        return Deed(), [Problem(str(path), f"could not be parsed. {exc}")]
    except OSError as exc:
        return Deed(), [Problem(str(path), f"could not be read: {exc}")]
    return parse(raw)


def find_deed(start: Path) -> Path | None:
    """Walk up from `start` looking for a deed, so commands work from any
    subdirectory of a repo the way git does."""
    current = start.resolve()
    for candidate in [current, *current.parents]:
        deed_file = candidate / DEED_PATH
        if deed_file.is_file():
            return deed_file
        if (candidate / ".git").exists():
            break  # Do not escape the repo boundary.
    return None
