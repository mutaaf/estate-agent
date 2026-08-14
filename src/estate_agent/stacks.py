"""Stack profiles: how Estate Agent recognises and understands a language.

Everything the tool knows about a stack lives in one file under `stacks/`.
Adding support for a new language means writing one YAML file and nothing
else - no code change, no registration list. That is the extension model, and
it is why this project can plausibly cover an estate nobody anticipated.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import yamlite

# Where the profiles live, relative to the installed project root.
STACKS_DIR = Path(__file__).resolve().parents[2] / "stacks"

# Directories never worth scanning. Skipping these is most of the reason a
# scan of a hundred repos finishes in seconds rather than minutes.
IGNORED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "vendor", "target", "build",
    "dist", "out", ".gradle", ".idea", ".vs", ".vscode", "bin", "obj",
    "__pycache__", ".venv", "venv", "env", ".tox", ".mypy_cache",
    ".pytest_cache", ".next", ".nuxt", ".svelte-kit", "Pods", "Carthage",
    "DerivedData", ".terraform", "coverage", ".cache", "tmp", ".dart_tool",
    "graphify-out", "site-packages", ".eggs", "htmlcov", ".ruff_cache",
}

# Order matters for detection: more specific stacks are tested first, so a
# React app is not mistaken for a generic Node service.
PRIORITY = [
    "as400", "roku-brightscript", "tvos", "ios-swift", "android-kotlin",
    "react-web", "dotnet", "rust", "java", "python", "node",
]


@dataclass
class Pattern:
    """One detection rule from a profile, with its regex compiled."""

    name: str
    regex: re.Pattern[str] | None
    via: str = "unknown"
    confidence: str = ""
    groups: dict[str, int] = field(default_factory=dict)
    marker_only: bool = False
    service_hint: str = ""
    path_from_filename: bool = False

    def group(self, kind: str, match: re.Match[str]) -> str | None:
        index = self.groups.get(kind)
        if not index:
            return None
        try:
            value = match.group(index)
        except (IndexError, error_types):
            return None
        return value.strip() if value else None


error_types = re.error


@dataclass
class Stack:
    name: str
    display: str
    kind: str = "backend"
    detect: dict[str, Any] = field(default_factory=dict)
    commands: dict[str, Any] = field(default_factory=dict)
    conventions: list[str] = field(default_factory=list)
    tier_default: int = 2
    routes: list[Pattern] = field(default_factory=list)
    consumers: list[Pattern] = field(default_factory=list)
    contracts: list[str] = field(default_factory=list)
    client_dependencies: list[dict[str, Any]] = field(default_factory=list)
    base_urls: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""
    declared_interface_template: dict[str, Any] = field(default_factory=dict)

    @property
    def is_client(self) -> bool:
        return self.kind == "client"

    @property
    def is_legacy(self) -> bool:
        return self.kind == "legacy"

    def commands_for(self, root: Path) -> dict[str, str]:
        """Base commands, with any matching alternative applied.

        A Java repo with a pom.xml should get Maven commands, not Gradle ones.
        """
        result = {
            k: str(v) for k, v in self.commands.items()
            if k != "alternatives" and isinstance(v, (str, int))
        }
        for alt in self.commands.get("alternatives") or []:
            if not isinstance(alt, dict):
                continue
            marker = str(alt.get("when") or "")
            if marker and _has_file(root, marker):
                result.update({
                    k: str(v) for k, v in alt.items()
                    if k != "when" and v is not None
                })
        return {k: v for k, v in result.items() if v}


_GROUP_KEYS = (
    "path_group", "method_group", "url_group", "service_group",
    "topic_group", "env_group", "table_group", "name_group",
    "operation_group",
)


def _to_pattern(raw: dict[str, Any], default_via: str = "unknown") -> Pattern | None:
    if not isinstance(raw, dict):
        return None
    expression = raw.get("regex")
    compiled: re.Pattern[str] | None = None
    if expression:
        try:
            compiled = re.compile(str(expression), re.MULTILINE)
        except re.error:
            # A broken pattern in one profile must not take the whole scan
            # down. `estate doctor` surfaces it; the rest keeps working.
            return None
    groups = {
        key.replace("_group", ""): int(raw[key])
        for key in _GROUP_KEYS
        if isinstance(raw.get(key), int)
    }
    return Pattern(
        name=str(raw.get("name") or "unnamed"),
        regex=compiled,
        via=str(raw.get("via") or default_via),
        confidence=str(raw.get("confidence") or ""),
        groups=groups,
        marker_only=bool(raw.get("marker_only")),
        service_hint=str(raw.get("service_hint") or ""),
        path_from_filename=bool(raw.get("path_from_filename")),
    )


def _parse_stack(data: dict[str, Any]) -> Stack:
    provides = data.get("provides") or {}
    consumes = data.get("consumes") or {}
    config = data.get("config") or {}
    if not isinstance(provides, dict):
        provides = {}
    if not isinstance(consumes, dict):
        consumes = {}
    if not isinstance(config, dict):
        config = {}

    routes = [
        p for p in (_to_pattern(r) for r in (provides.get("routes") or []))
        if p is not None
    ]
    consumers = [
        p for p in (_to_pattern(c) for c in (consumes.get("patterns") or []))
        if p is not None
    ]

    return Stack(
        name=str(data.get("stack") or ""),
        display=str(data.get("display") or data.get("stack") or ""),
        kind=str(data.get("kind") or "backend"),
        detect=data.get("detect") or {},
        commands=data.get("commands") or {},
        conventions=[str(c) for c in (data.get("conventions") or [])],
        tier_default=int(data.get("tier_default") or 2),
        routes=routes,
        consumers=consumers,
        contracts=[str(c) for c in (provides.get("contracts") or [])],
        client_dependencies=[
            d for d in (consumes.get("client_dependencies") or [])
            if isinstance(d, dict)
        ],
        base_urls=[
            b for b in (config.get("base_urls") or []) if isinstance(b, dict)
        ],
        notes=str(data.get("notes") or "").strip(),
        declared_interface_template=(
            provides.get("declared_interface_template") or {}
        ),
    )


_CACHE: dict[str, Stack] | None = None

# Profiles that failed to load, and why. A stack that silently fails to load
# is a stack whose repos silently go unmapped, which is a far worse outcome
# than a loud error - so the failures are kept and `estate doctor` reports
# them rather than being swallowed here.
LOAD_ERRORS: list[tuple[str, str]] = []


def all_stacks(directory: Path | None = None) -> dict[str, Stack]:
    """Load every profile once and cache it."""
    global _CACHE
    if _CACHE is not None and directory is None:
        return _CACHE

    base = directory or STACKS_DIR
    loaded: dict[str, Stack] = {}
    errors: list[tuple[str, str]] = []

    if not base.is_dir():
        errors.append((str(base), "stack profile directory not found"))
    else:
        for path in sorted(base.glob("*.yaml")):
            try:
                data = yamlite.load(path.read_text(encoding="utf-8"))
            except yamlite.YamliteError as exc:
                errors.append((path.name, str(exc)))
                continue
            except OSError as exc:
                errors.append((path.name, f"could not be read: {exc}"))
                continue
            if not isinstance(data, dict) or not data.get("stack"):
                errors.append((path.name, "missing a top-level `stack:` key"))
                continue
            stack = _parse_stack(data)
            # A regex that fails to compile is dropped by _to_pattern. Say so,
            # rather than quietly detecting fewer connections than expected.
            declared = len(
                ((data.get("provides") or {}).get("routes") or [])
            ) + len(((data.get("consumes") or {}).get("patterns") or []))
            actual = len(stack.routes) + len(stack.consumers)
            if actual < declared:
                errors.append((
                    path.name,
                    f"{declared - actual} pattern(s) have an invalid regex and "
                    f"were skipped",
                ))
            loaded[stack.name] = stack

    if directory is None:
        _CACHE = loaded
        LOAD_ERRORS[:] = errors
    return loaded


def get(name: str) -> Stack | None:
    return all_stacks().get(name)


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------


def _has_file(root: Path, pattern: str) -> bool:
    """Marker files may be globs (`*.csproj`) or paths (`app/build.gradle`)."""
    if any(ch in pattern for ch in "*?["):
        if any(root.glob(pattern)):
            return True
        return any(root.glob(f"*/{pattern}"))
    if (root / pattern).exists():
        return True
    # One level down covers the common `app/`, `src/`, `ios/` layouts.
    return any((child / pattern).exists() for child in _shallow_dirs(root))


def _shallow_dirs(root: Path) -> list[Path]:
    try:
        return [
            d for d in root.iterdir()
            if d.is_dir() and d.name not in IGNORED_DIRS
            and not d.name.startswith(".")
        ][:40]
    except OSError:
        return []


def _count_extensions(root: Path, extensions: list[str], cap: int = 400) -> dict[str, int]:
    """Count source files per extension, cheaply and with a hard cap."""
    wanted = {e.lower() for e in extensions}
    counts: dict[str, int] = {}
    seen = 0
    stack: list[Path] = [root]
    while stack and seen < cap:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if seen >= cap:
                break
            if entry.is_dir():
                if entry.name not in IGNORED_DIRS and not entry.name.startswith("."):
                    stack.append(entry)
                continue
            suffix = entry.suffix.lower()
            if suffix in wanted:
                counts[suffix] = counts.get(suffix, 0) + 1
                seen += 1
    return counts


def _content_marker_hit(root: Path, markers: list[str]) -> bool:
    """Look for a marker string in the small files at the repo root."""
    if not markers:
        return False
    candidates = [
        "package.json", "manifest", "build.gradle", "build.gradle.kts",
        "app/build.gradle", "app/build.gradle.kts", "Package.swift",
        "pyproject.toml", "Cargo.toml", "AndroidManifest.xml",
        "app/src/main/AndroidManifest.xml", "project.pbxproj",
    ]
    texts: list[str] = []
    for name in candidates:
        path = root / name
        if path.is_file():
            try:
                texts.append(path.read_text(encoding="utf-8", errors="replace")[:20000])
            except OSError:
                continue
    for pbx in list(root.glob("*.xcodeproj/project.pbxproj"))[:2]:
        try:
            texts.append(pbx.read_text(encoding="utf-8", errors="replace")[:40000])
        except OSError:
            continue
    blob = "\n".join(texts)
    return any(marker in blob for marker in markers)


@dataclass
class Detection:
    stack: str
    confidence: float
    reasons: list[str] = field(default_factory=list)


def detect(root: Path) -> list[Detection]:
    """Identify the stacks present in a repo, best guess first.

    Returns every plausible match rather than one answer, because polyglot
    repos are real: an Android repo with a Kotlin backend module, or a Next.js
    app that is also a Node service.
    """
    profiles = all_stacks()
    results: list[Detection] = []

    for name in PRIORITY:
        stack = profiles.get(name)
        if stack is None:
            continue
        detect_rules = stack.detect or {}
        reasons: list[str] = []
        score = 0.0

        for marker in detect_rules.get("files") or []:
            if _has_file(root, str(marker)):
                score += 0.5
                reasons.append(f"found {marker}")
                break

        for marker in detect_rules.get("not_files") or []:
            if _has_file(root, str(marker)):
                score -= 0.6
                reasons.append(f"but also found {marker}")

        # Some stacks share every marker file with a sibling: a tvOS repo and
        # an iOS repo both have an .xcodeproj and .swift files. Those stacks
        # set `requires_marker`, which makes the distinguishing signal
        # mandatory rather than merely additive - otherwise the first one in
        # priority order swallows every repo belonging to the second.
        marker_found = False

        any_dirs = detect_rules.get("any_dirs") or []
        if any_dirs:
            for directory in any_dirs:
                if (root / str(directory)).is_dir() or any(
                    d.name == str(directory) for d in _shallow_dirs(root)
                ):
                    score += 0.3
                    marker_found = True
                    reasons.append(f"has a {directory}/ directory")
                    break

        extensions = [str(e) for e in (detect_rules.get("extensions") or [])]
        if extensions:
            counts = _count_extensions(root, extensions)
            total = sum(counts.values())
            minimum = int(detect_rules.get("min_source_files") or 1)
            if total >= minimum:
                score += min(0.4, 0.1 + total / 100)
                listed = ", ".join(
                    f"{n}{ext}" for ext, n in sorted(
                        counts.items(), key=lambda kv: -kv[1]
                    )[:3]
                )
                reasons.append(f"{listed} source files")
            elif total == 0:
                score -= 0.35

        markers = [str(m) for m in (detect_rules.get("content_markers") or [])]
        if markers and _content_marker_hit(root, markers):
            score += 0.35
            marker_found = True
            reasons.append("matched a content marker")

        if detect_rules.get("requires_marker") and not marker_found:
            continue

        if score >= 0.5:
            results.append(Detection(name, round(min(score, 1.0), 2), reasons))

    results.sort(key=lambda d: (-d.confidence, PRIORITY.index(d.stack)))
    return results


def primary(root: Path) -> Detection | None:
    found = detect(root)
    return found[0] if found else None
