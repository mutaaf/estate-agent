"""Walk a workspace, identify repos, and pull out the evidence.

This is the half of the estate map that reads files. It produces raw signals -
"this line looks like a call to something" - and deliberately does no
resolution. Deciding which service a signal points at happens in graph.py,
where the ranking rules live and can be reasoned about on their own.

Nothing here makes a network call, and nothing here calls a model. It is grep
and file reads, which is why the results are reproducible and auditable: every
edge on the finished map can be traced back to a file and a line number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from . import stacks as stacks_mod
from .stacks import IGNORED_DIRS, Stack

# Hard caps. A hundred-repo estate must map in seconds, and a runaway walk
# through a vendored dependency tree helps nobody.
MAX_FILE_BYTES = 512 * 1024
MAX_FILES_PER_REPO = 4000
MAX_MATCHES_PER_PATTERN = 200

TEXT_SUFFIXES = {
    ".java", ".kt", ".kts", ".swift", ".rs", ".cs", ".ts", ".tsx", ".js",
    ".jsx", ".mjs", ".cjs", ".py", ".go", ".rb", ".php", ".scala", ".m",
    ".mm", ".brs", ".bs", ".xml", ".json", ".yaml", ".yml", ".toml", ".env",
    ".properties", ".gradle", ".plist", ".xcconfig", ".graphql", ".proto",
    ".rpgle", ".sqlrpgle", ".rpg", ".clle", ".clp", ".dds", ".pf", ".lf",
    ".sql", ".tf", ".conf", ".ini", ".cfg", ".md",
}
TEXT_NAMES = {
    "manifest", "Dockerfile", "docker-compose.yml", "Makefile", "Podfile",
    ".env.example", ".env.sample", "package.json", "pom.xml", "Cargo.toml",
}

CONTRACT_GLOBS = [
    "openapi.yaml", "openapi.yml", "openapi.json", "swagger.yaml",
    "swagger.json", "api.yaml", "api.yml",
    "**/openapi.yaml", "**/openapi.yml", "**/openapi.json",
    "**/swagger.json", "**/*.proto", "**/*.graphql", "**/schema.graphql",
    "**/asyncapi.yaml", "**/asyncapi.yml",
]


@dataclass
class Endpoint:
    method: str
    path: str
    evidence: str
    source: str = "route"

    def key(self) -> str:
        return f"{self.method or 'ANY'} {self.path}"


@dataclass
class Signal:
    """One piece of evidence that a repo talks to something else."""

    kind: str          # service | url | path | topic | env | dependency | table
    value: str
    via: str
    evidence: str      # path/to/file.ext:LINE
    pattern: str
    hint: str = ""     # e.g. "declared" from the profile

    def as_dict(self) -> dict[str, Any]:
        data = {
            "kind": self.kind, "value": self.value, "via": self.via,
            "evidence": self.evidence, "pattern": self.pattern,
        }
        if self.hint:
            data["hint"] = self.hint
        return data


@dataclass
class RepoRecord:
    name: str
    path: str
    stacks: list[str] = field(default_factory=list)
    primary_stack: str = ""
    kind: str = "backend"
    contracts: list[str] = field(default_factory=list)
    endpoints: list[Endpoint] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    hosts: list[str] = field(default_factory=list)
    declared_consumes: list[dict[str, Any]] = field(default_factory=list)
    has_deed: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def is_client(self) -> bool:
        return self.kind == "client"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "stack": self.primary_stack,
            "stacks": self.stacks,
            "kind": self.kind,
            "has_deed": self.has_deed,
            "contracts": self.contracts,
            "endpoints": [
                {"method": e.method, "path": e.path, "evidence": e.evidence}
                for e in self.endpoints
            ],
            "hosts": self.hosts,
            "notes": self.notes,
        }


# --------------------------------------------------------------------------
# Finding repos
# --------------------------------------------------------------------------


def find_repos(workspace: Path, max_depth: int = 3) -> list[Path]:
    """Every git repo under the workspace, plus the workspace itself if it is
    one. Nested repos (a submodule inside a repo) are not descended into.

    Symlinked directories are followed. People really do symlink repos into a
    workspace, and skipping them means a repo silently missing from the map -
    which is worse than the loop risk, so cycles are handled by tracking
    resolved paths instead of refusing to look.
    """
    workspace = workspace.resolve()
    found: list[Path] = []
    visited: set[Path] = set()

    def walk(directory: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(d for d in directory.iterdir() if d.is_dir())
        except OSError:
            return
        for entry in entries:
            if entry.name in IGNORED_DIRS:
                continue
            try:
                real = entry.resolve()
            except OSError:
                continue
            if real in visited:
                continue  # Already seen it, by this name or another.
            visited.add(real)
            if (entry / ".git").exists():
                found.append(entry)
                continue  # Do not descend into a repo looking for more.
            if entry.name.startswith("."):
                continue
            walk(entry, depth + 1)

    if (workspace / ".git").exists():
        found.append(workspace)
    else:
        walk(workspace, 1)

    # A directory with a build file but no git is still a repo worth mapping.
    if not found:
        markers = ("package.json", "pom.xml", "Cargo.toml", "pyproject.toml")
        for entry in sorted(p for p in workspace.iterdir() if p.is_dir()):
            if entry.name in IGNORED_DIRS or entry.name.startswith("."):
                continue
            if any((entry / m).exists() for m in markers):
                found.append(entry)

    return found


# --------------------------------------------------------------------------
# Reading files
# --------------------------------------------------------------------------


def _is_text(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_NAMES


def iter_source_files(root: Path) -> Iterator[Path]:
    count = 0
    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if count >= MAX_FILES_PER_REPO:
                return
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name not in IGNORED_DIRS and entry.name != ".git":
                    stack.append(entry)
                continue
            if not _is_text(entry):
                continue
            try:
                if entry.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            count += 1
            yield entry


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------

_URL_LITERAL = re.compile(r"https?://[^\s\"'`,)\]}<>]+")
_ENV_REF = re.compile(
    r"(?:process\.env\.|import\.meta\.env\.|os\.environ\[?['\"]?|"
    r"System\.getenv\(['\"]|std::env::var\(['\"]|Environment\."
    r"GetEnvironmentVariable\(['\"]|\$\{?)([A-Z][A-Z0-9_]{2,})"
)
_PATH_LITERAL = re.compile(r"^/[A-Za-z0-9._~\-/{}:]*$")


def _classify_value(raw: str) -> tuple[str, str] | None:
    """Turn a captured expression into (kind, value), or None if useless.

    Call sites capture whatever was in the source: a URL, a template literal,
    a variable, a constant. Each tells us something different about which
    service is meant, so they are kept apart rather than flattened.
    """
    value = raw.strip().strip("(),;")
    if not value or len(value) > 300:
        return None

    url = _URL_LITERAL.search(value)
    if url:
        return ("url", url.group(0))

    env = _ENV_REF.search(value)
    if env:
        return ("env", env.group(1))

    # A quoted path fragment: "/v2/charge" or `/v2/charge`
    unquoted = value.strip("\"'`")
    if _PATH_LITERAL.match(unquoted) and len(unquoted) > 1:
        return ("path", unquoted)

    # A template literal with a path fragment: `${base}/v2/charge`
    fragment = re.search(r"\}(/[A-Za-z0-9._\-/{}:]+)", value)
    if fragment:
        return ("path", fragment.group(1))

    # A bare identifier is too weak to act on but worth keeping as a hint.
    if re.fullmatch(r"[A-Za-z_][\w.]{2,60}", value):
        return ("symbol", value)

    return None


def extract_endpoints(root: Path, stack: Stack, files: list[tuple[Path, str]]) -> list[Endpoint]:
    endpoints: list[Endpoint] = []
    seen: set[str] = set()
    for pattern in stack.routes:
        if pattern.regex is None:
            continue
        hits = 0
        for path, text in files:
            for match in pattern.regex.finditer(text):
                if hits >= MAX_MATCHES_PER_PATTERN:
                    break
                route = pattern.group("path", match) or ""
                method = (pattern.group("method", match) or "").upper()
                if pattern.path_from_filename and not route:
                    route = _route_from_filename(root, path)
                if not route:
                    continue
                endpoint = Endpoint(
                    method=method,
                    path=route,
                    evidence=(
                        f"{path.relative_to(root)}:{_line_of(text, match.start())}"
                    ),
                    source=pattern.name,
                )
                if endpoint.key() in seen:
                    continue
                seen.add(endpoint.key())
                endpoints.append(endpoint)
                hits += 1
    return endpoints


def _route_from_filename(root: Path, path: Path) -> str:
    """Next.js style: the file's location is the route."""
    try:
        parts = list(path.relative_to(root).parts)
    except ValueError:
        return ""
    for anchor in ("app", "pages", "api"):
        if anchor in parts:
            parts = parts[parts.index(anchor) + 1:]
            break
    else:
        return ""
    if parts and parts[-1].split(".")[0] in ("route", "index", "handler"):
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].split(".")[0]
    cleaned = [p for p in parts if p and not p.startswith("_")]
    return "/" + "/".join(cleaned) if cleaned else "/"


def extract_signals(root: Path, stack: Stack, files: list[tuple[Path, str]]) -> list[Signal]:
    signals: list[Signal] = []
    seen: set[tuple[str, str, str]] = set()

    for pattern in stack.consumers:
        if pattern.regex is None or pattern.marker_only:
            continue
        hits = 0
        for path, text in files:
            if hits >= MAX_MATCHES_PER_PATTERN:
                break
            for match in pattern.regex.finditer(text):
                if hits >= MAX_MATCHES_PER_PATTERN:
                    break
                evidence = (
                    f"{path.relative_to(root)}:{_line_of(text, match.start())}"
                )
                found = _signal_from_match(pattern, match, evidence)
                if found is None:
                    continue
                key = (found.kind, found.value.lower(), found.via)
                if key in seen:
                    continue
                seen.add(key)
                signals.append(found)
                hits += 1

    signals.extend(_extract_dependencies(root, stack))
    signals.extend(_extract_config_urls(root, stack))
    return signals


def _signal_from_match(pattern, match, evidence: str) -> Signal | None:
    def make(kind: str, value: str) -> Signal:
        return Signal(
            kind=kind, value=value, via=pattern.via, evidence=evidence,
            pattern=pattern.name, hint=pattern.confidence,
        )

    service = pattern.group("service", match)
    if service:
        return make("service", service)

    topic = pattern.group("topic", match)
    if topic:
        return make("topic", topic)

    table = pattern.group("table", match)
    if table:
        return make("table", table)

    env = pattern.group("env", match)
    if env:
        return make("env", env)

    for key in ("url", "path"):
        raw = pattern.group(key, match)
        if raw:
            classified = _classify_value(raw)
            if classified:
                kind, value = classified
                if kind == "symbol" and pattern.confidence != "declared":
                    continue  # Too weak on its own.
                return make(kind, value)

    if pattern.service_hint:
        return make("service", pattern.service_hint)
    return None


def _extract_dependencies(root: Path, stack: Stack) -> list[Signal]:
    """A dependency named `payments-client` is strong evidence of a caller."""
    signals: list[Signal] = []
    for rule in stack.client_dependencies:
        file_pattern = str(rule.get("file") or "")
        expression = str(rule.get("regex") or "")
        group = int(rule.get("name_group") or 1)
        if not file_pattern or not expression:
            continue
        try:
            compiled = re.compile(expression, re.MULTILINE)
        except re.error:
            continue
        candidates = (
            list(root.glob(file_pattern))
            if any(ch in file_pattern for ch in "*?[")
            else [root / file_pattern]
        )
        for candidate in candidates[:5]:
            if not candidate.is_file():
                continue
            text = _read(candidate)
            for match in compiled.finditer(text):
                try:
                    name = match.group(group)
                except (IndexError, re.error):
                    continue
                if not name:
                    continue
                signals.append(Signal(
                    kind="dependency", value=name, via="rest",
                    evidence=(
                        f"{candidate.relative_to(root)}:"
                        f"{_line_of(text, match.start())}"
                    ),
                    pattern="client-dependency", hint="dependency",
                ))
    return signals


def _extract_config_urls(root: Path, stack: Stack) -> list[Signal]:
    signals: list[Signal] = []
    for rule in stack.base_urls:
        file_pattern = str(rule.get("file") or "")
        expression = str(rule.get("regex") or "")
        if not file_pattern or not expression:
            continue
        try:
            compiled = re.compile(expression, re.MULTILINE)
        except re.error:
            continue
        candidates = (
            list(root.glob(file_pattern))
            if any(ch in file_pattern for ch in "*?[")
            else [root / file_pattern]
        )
        for candidate in candidates[:5]:
            if not candidate.is_file():
                continue
            text = _read(candidate)
            for match in compiled.finditer(text):
                groups = [g for g in match.groups() if g]
                if not groups:
                    continue
                evidence = (
                    f"{candidate.relative_to(root)}:"
                    f"{_line_of(text, match.start())}"
                )
                name = groups[0]
                value = groups[1] if len(groups) > 1 else ""
                classified = _classify_value(value) if value else None
                if classified and classified[0] == "url":
                    signals.append(Signal(
                        "url", classified[1], "rest", evidence, "config-url",
                    ))
                # The variable name is often the better clue: PAYMENTS_API_URL
                # names the service even when the value is a placeholder.
                if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{2,60}", name):
                    signals.append(Signal(
                        "env", name.upper(), "rest", evidence, "config-name",
                    ))
    return signals


def find_contracts(root: Path) -> list[str]:
    found: list[str] = []
    for pattern in CONTRACT_GLOBS:
        for path in list(root.glob(pattern))[:20]:
            if not path.is_file():
                continue
            if any(part in IGNORED_DIRS for part in path.parts):
                continue
            relative = str(path.relative_to(root))
            if relative not in found:
                found.append(relative)
        if len(found) >= 40:
            break
    return found


def find_hosts(root: Path, files: list[tuple[Path, str]]) -> list[str]:
    """Hostnames this repo publishes itself under, from deployment config."""
    hosts: list[str] = []
    for name in (
        "docker-compose.yml", "docker-compose.yaml", "Chart.yaml",
        "k8s/service.yaml", "deploy/service.yaml", "serverless.yml",
    ):
        path = root / name
        if not path.is_file():
            continue
        text = _read(path)
        for match in re.finditer(
            r"^\s*(?:name|host|hostname)\s*:\s*[\"']?([a-z0-9][a-z0-9.\-]{2,60})",
            text, re.MULTILINE,
        ):
            candidate = match.group(1)
            if candidate not in hosts:
                hosts.append(candidate)
    return hosts[:10]


# --------------------------------------------------------------------------
# One repo, end to end
# --------------------------------------------------------------------------


def survey(root: Path, workspace: Path) -> RepoRecord:
    """Read one repo and return everything we can prove about it."""
    detections = stacks_mod.detect(root)
    record = RepoRecord(
        name=root.name,
        path=str(root.relative_to(workspace)) if root != workspace else ".",
        stacks=[d.stack for d in detections],
        primary_stack=detections[0].stack if detections else "",
        has_deed=(root / ".agent" / "estate.yaml").is_file(),
    )

    if not detections:
        record.notes.append("no known stack detected")
        return record

    profiles = [
        stacks_mod.get(d.stack) for d in detections
        if stacks_mod.get(d.stack) is not None
    ]
    record.kind = profiles[0].kind if profiles else "backend"
    record.contracts = find_contracts(root)

    # Read every source file once, then run all patterns over the text.
    wanted_suffixes: set[str] = set()
    for profile in profiles:
        wanted_suffixes.update(
            str(e).lower() for e in (profile.detect.get("extensions") or [])
        )
    files: list[tuple[Path, str]] = []
    for path in iter_source_files(root):
        if wanted_suffixes and path.suffix.lower() not in wanted_suffixes:
            if path.name not in TEXT_NAMES:
                continue
        text = _read(path)
        if text:
            files.append((path, text))

    for profile in profiles:
        record.endpoints.extend(extract_endpoints(root, profile, files))
        record.signals.extend(extract_signals(root, profile, files))

    record.hosts = find_hosts(root, files)

    if record.kind == "legacy":
        record.notes.append(
            "legacy system - described rather than parsed; agents may read and "
            "call it but not modify it"
        )
    if record.primary_stack == "roku-brightscript":
        record.notes.append(
            "BrightScript has no parser; connection coverage here is weaker "
            "than for other stacks"
        )
    return record
