"""Turn raw signals into a service map, with evidence for every connection.

The rule this file exists to enforce: **precision beats coverage**. A map with
phantom connections gets ignored after the second false alarm, and then the
real ones go unread too. So:

  * Every edge records the file and line that proves it.
  * Every edge carries a confidence rank naming *how* it was resolved.
  * A signal that plausibly matches two services resolves to neither. It goes
    to the confirm list for a human to settle once.
  * Nothing is inferred by a model. This is grep plus a ranking ladder, which
    means the same estate always produces the same map.

The ladder, strongest first:

  declared    the source names the service outright (@FeignClient("payments"))
  dependency  a generated client library for that service is a dependency
  env         a configured variable names it (PAYMENTS_API_URL)
  host        a URL's hostname matches the service
  path        the called path matches exactly one service's declared endpoint
  (unresolved)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .discover import RepoRecord, Signal
from .infra import InfraNode, build_nodes

# How much each resolution method is trusted. These numbers are ordering, not
# probability: what matters is that a declared name always beats a guess.
CONFIDENCE = {
    "declared": 0.95,
    "dependency": 0.90,
    "env": 0.75,
    "host": 0.70,
    "path": 0.60,
    "topic": 0.65,
    "table": 0.65,
}

# Words that carry no identity. `payments-api` and `payments-service` are the
# same service; the distinguishing token is `payments`.
GENERIC_TOKENS = {
    "api", "apis", "service", "services", "svc", "srv", "server", "backend",
    "be", "app", "application", "client", "clients", "sdk", "lib", "library",
    "core", "common", "shared", "internal", "external", "gateway", "gw",
    "web", "www", "http", "https", "rest", "graphql", "grpc", "v1", "v2",
    "v3", "prod", "production", "staging", "stage", "dev", "development",
    "test", "qa", "uat", "url", "uri", "endpoint", "endpoints", "base",
    "baseurl", "host", "hostname", "port", "the", "our", "my", "main",
}

_SPLIT = re.compile(r"[^a-z0-9]+")


def tokens(name: str) -> list[str]:
    """Split an identifier into lowercase words, camelCase included."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(name))
    return [t for t in _SPLIT.split(spaced.lower()) if t]


def identity(name: str) -> frozenset[str]:
    """The tokens that actually identify a service."""
    parts = [t for t in tokens(name) if t not in GENERIC_TOKENS and len(t) > 1]
    return frozenset(parts)


def literal_segments(path: str) -> list[str]:
    """The parts of a path that actually name something."""
    return [p for p in path.split("/") if p and p != "*"]


def is_catch_all(path: str) -> bool:
    """True for routes that match everything and identify nothing."""
    return not literal_segments(path)


def normalise_path(path: str) -> str:
    """`/v2/charge/{id}`, `/v2/charge/:id` and `/v2/charge/<id>` are one path."""
    cleaned = path.strip()
    if not cleaned.startswith("/"):
        cleaned = "/" + cleaned
    cleaned = re.sub(r"\{[^}]*\}", "*", cleaned)
    cleaned = re.sub(r"<[^>]*>", "*", cleaned)
    cleaned = re.sub(r"(?<=/):[A-Za-z_]\w*", "*", cleaned)
    cleaned = re.sub(r"/+", "/", cleaned)
    return cleaned.rstrip("/") or "/"


@dataclass
class Edge:
    source: str
    target: str
    via: str
    method: str
    score: float
    evidence: list[str] = field(default_factory=list)
    detail: str = ""
    # Paths this caller was actually seen using. Empty means we know it
    # calls the service but not which endpoints - reported as such rather
    # than assumed to be all of them.
    paths: list[str] = field(default_factory=list)

    def key(self) -> tuple[str, str, str, str]:
        return (self.source, self.target, self.via, self.method)

    def as_dict(self) -> dict[str, Any]:
        return {
            "from": self.source, "to": self.target, "via": self.via,
            "resolved_by": self.method, "confidence": round(self.score, 2),
            "evidence": self.evidence[:6],
            "paths": sorted(self.paths),
            **({"detail": self.detail} if self.detail else {}),
        }


@dataclass
class Unresolved:
    source: str
    signal: str
    value: str
    via: str
    evidence: str
    reason: str
    candidates: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "from": self.source, "kind": self.signal, "value": self.value,
            "via": self.via, "evidence": self.evidence, "reason": self.reason,
            "candidates": self.candidates,
        }


@dataclass
class External:
    """Something a repo talks to that is not in this estate.

    Third-party APIs, vendor SDKs, and provider credentials are not questions
    anybody can usefully answer - they are simply outside the estate. Keeping
    them apart from the confirm list is what stops that list filling with
    noise nobody reads. They are still worth listing: "which outside services
    does this repo depend on" is a question people ask constantly.
    """

    source: str
    value: str
    via: str
    evidence: str
    kind: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "from": self.source, "value": self.value, "via": self.via,
            "evidence": self.evidence, "kind": self.kind,
        }


@dataclass
class EstateMap:
    repos: list[RepoRecord] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    unresolved: list[Unresolved] = field(default_factory=list)
    workspace: str = ""
    external: list[External] = field(default_factory=list)
    infrastructure: list[InfraNode] = field(default_factory=list)

    def repo(self, name: str) -> RepoRecord | None:
        for record in self.repos:
            if record.name == name:
                return record
        return None

    def callers_of(self, name: str) -> list[Edge]:
        return [e for e in self.edges if e.target == name]

    def callees_of(self, name: str) -> list[Edge]:
        return [e for e in self.edges if e.source == name]

    def as_dict(self) -> dict[str, Any]:
        return {
            "estate_agent_version": "0.1.0",
            "workspace": self.workspace,
            "repos": [r.as_dict() for r in self.repos],
            "edges": [e.as_dict() for e in self.edges],
            "unresolved": [u.as_dict() for u in self.unresolved],
            "external": [x.as_dict() for x in self.external],
            "infrastructure": [i.as_dict() for i in self.infrastructure],
        }


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------


class _Index:
    """Lookup tables built once from all repos."""

    def __init__(self, repos: list[RepoRecord]) -> None:
        self.by_name: dict[str, RepoRecord] = {r.name: r for r in repos}
        self.by_identity: dict[frozenset[str], list[str]] = {}
        self.by_host: dict[str, list[str]] = {}
        self.by_path: dict[str, list[str]] = {}
        self.by_topic: dict[str, list[str]] = {}

        for record in repos:
            ident = identity(record.name)
            if ident:
                self.by_identity.setdefault(ident, []).append(record.name)
            for host in record.hosts:
                first = host.split(".")[0].lower()
                self.by_host.setdefault(first, []).append(record.name)
            self.by_host.setdefault(record.name.lower(), []).append(record.name)
            for endpoint in record.endpoints:
                path = normalise_path(endpoint.path)
                if is_catch_all(path):
                    # A catch-all such as FastAPI's `/{full_path:path}` or a
                    # SPA fallback matches every path in the estate. Indexing
                    # it makes that repo look like the owner of everything.
                    continue
                self.by_path.setdefault(path, []).append(record.name)
            for signal in record.signals:
                if signal.kind == "topic":
                    self.by_topic.setdefault(
                        signal.value.lower(), []
                    ).append(record.name)

    def match_identity(self, name: str) -> list[str]:
        wanted = identity(name)
        if not wanted:
            return []
        exact = self.by_identity.get(wanted)
        if exact:
            return list(dict.fromkeys(exact))
        # Fall back to containment: `payments` matches `payments-api`.
        hits = [
            repo for ident, names in self.by_identity.items()
            if wanted and (wanted <= ident or ident <= wanted)
            for repo in names
        ]
        return list(dict.fromkeys(hits))


def _strip_url_words(name: str) -> str:
    parts = [
        t for t in tokens(name)
        if t not in {"url", "uri", "endpoint", "base", "host", "addr",
                     "address", "prefix"}
    ]
    return "-".join(parts)


def _host_of(url: str) -> str:
    match = re.match(r"https?://([^/:?#]+)", url)
    return match.group(1).lower() if match else ""


def _path_of(url: str) -> str:
    match = re.match(r"https?://[^/]+(/[^\s?#]*)", url)
    return match.group(1) if match else ""


LOCAL_HOSTS = {"localhost", "127", "0", "host", "example", "test"}


def _resolve(
    source: str, signal: Signal, index: _Index
) -> tuple[str, str, float] | tuple[None, str, list[str]]:
    """Return (target, method, score) or (None, reason, candidates)."""

    def decide(candidates: list[str], method: str):
        candidates = [c for c in dict.fromkeys(candidates) if c != source]
        if not candidates:
            return (None, "no repo in this workspace matches", [])
        if len(candidates) > 1:
            return (
                None,
                f"matches {len(candidates)} services equally well - "
                f"confirm which one is meant",
                candidates,
            )
        return (candidates[0], method, CONFIDENCE[method])

    if signal.kind == "service":
        return decide(index.match_identity(signal.value), "declared")

    if signal.kind == "dependency":
        return decide(index.match_identity(signal.value), "dependency")

    if signal.kind == "env":
        return decide(index.match_identity(_strip_url_words(signal.value)), "env")

    if signal.kind == "topic":
        producers = index.by_topic.get(signal.value.lower(), [])
        return decide([p for p in producers if p != source], "topic")

    if signal.kind == "table":
        return decide(index.match_identity(signal.value), "table")

    if signal.kind == "url":
        host = _host_of(signal.value)
        label = host.split(".")[0] if host else ""
        if label and label not in LOCAL_HOSTS and not label.isdigit():
            by_host = index.by_host.get(label, [])
            if by_host:
                return decide(by_host, "host")
            by_identity = index.match_identity(label)
            if by_identity:
                return decide(by_identity, "host")
        path = _path_of(signal.value)
        if path:
            return _resolve_path(source, path, index)
        return (None, "URL does not name a service in this workspace", [])

    if signal.kind == "path":
        return _resolve_path(source, signal.value, index)

    return (None, f"signal kind '{signal.kind}' cannot be resolved", [])


SELF_CALL = "__self__"


def _resolve_path(source: str, path: str, index: _Index):
    normalised = normalise_path(path)
    if normalised.count("/") < 2 and len(normalised) < 6:
        return (None, "path is too generic to identify a service", [])

    if len(literal_segments(normalised)) < 2:
        # A single-segment path such as `/health` or `/api` names a shape, not
        # a service. Matching on it produces confident nonsense.
        return (None, "path is too generic to identify a service", [])

    all_owners = index.by_path.get(normalised, [])
    if all_owners and set(all_owners) == {source}:
        # A repo calling its own route. Extremely common in Next.js and any
        # app with a backend-for-frontend, and not a connection at all.
        return (None, SELF_CALL, [])

    owners = [o for o in all_owners if o != source]

    if not owners:
        # A caller's `/v2/refund` and a provider's `/v2/refund/{id}` are the
        # same endpoint. Accept a prefix relationship, but only when it points
        # at exactly one service - the moment it is ambiguous it becomes a
        # question instead of a guess.
        prefixed = {
            owner
            for known, names in index.by_path.items()
            if known != normalised
            and (known.startswith(normalised + "/")
                 or normalised.startswith(known + "/"))
            # Both sides must share at least two named segments, so
            # `/v2/refund` matches `/v2/refund/{id}` but `/api/x/y` does not
            # match some unrelated repo's `/api`.
            and len(literal_segments(known)) >= 2
            for owner in names
            if owner != source
        }
        if len(prefixed) == 1:
            return (prefixed.pop(), "path", CONFIDENCE["path"] - 0.05)
        if len(prefixed) > 1:
            return (
                None,
                f"{len(prefixed)} services declare a matching path prefix - "
                f"confirm which one is meant",
                sorted(prefixed),
            )
        return (None, "no service in this workspace declares this path", [])
    if len(set(owners)) > 1:
        return (
            None,
            f"{len(set(owners))} services declare this path - confirm which "
            f"one is meant",
            sorted(set(owners)),
        )
    return (owners[0], "path", CONFIDENCE["path"])


def build(repos: list[RepoRecord], workspace: str = "") -> EstateMap:
    """Resolve every signal into an edge or a question."""
    index = _Index(repos)
    merged: dict[tuple[str, str, str, str], Edge] = {}
    unresolved: list[Unresolved] = []
    external: list[External] = []
    seen_questions: set[tuple[str, str, str]] = set()

    for record in repos:
        # A deed that declares its dependencies outranks anything inferred.
        for declared in record.declared_consumes:
            target = str(declared.get("service") or "")
            if not target or target == record.name:
                continue
            edge = Edge(
                record.name, target, str(declared.get("via") or "unknown"),
                "declared", CONFIDENCE["declared"],
                [str(declared.get("evidence") or ".agent/estate.yaml")],
                "declared in the deed",
            )
            merged[edge.key()] = edge

        source_identity = identity(record.name)
        for signal in record.signals:
            # A repo naming itself is not a connection. This happens routinely:
            # a pom.xml lists its own artifactId, a config file names its own
            # service. Dropping it silently keeps the confirm list to things a
            # human can actually answer.
            if (
                signal.kind in ("service", "dependency", "env")
                and source_identity
                and identity(_strip_url_words(signal.value)) == source_identity
            ):
                continue

            hint_method = "declared" if signal.hint == "declared" else ""
            target, method, score = _resolve(record.name, signal, index)

            if target is None:
                reason, candidates = method, score  # type: ignore[assignment]
                if reason == SELF_CALL:
                    continue
                question = (record.name, signal.kind, signal.value.lower())
                if question in seen_questions:
                    continue
                seen_questions.add(question)

                # Only genuine ambiguity becomes a question. A signal that
                # matches nothing at all is a third-party dependency, not
                # something a colleague can adjudicate - and filling the
                # confirm list with `ANTHROPIC_API_KEY` and `stripe.com` is
                # how the list stops being read.
                if candidates:
                    unresolved.append(Unresolved(
                        record.name, signal.kind, signal.value, signal.via,
                        signal.evidence, str(reason), list(candidates),
                    ))
                elif signal.kind in ("url", "dependency", "env", "service"):
                    external.append(External(
                        record.name, signal.value, signal.via,
                        signal.evidence, signal.kind,
                    ))
                continue

            if hint_method:
                method, score = "declared", CONFIDENCE["declared"]

            called_path = ""
            if signal.kind == "path":
                called_path = normalise_path(signal.value)
            elif signal.kind == "url":
                tail = _path_of(signal.value)
                if tail:
                    called_path = normalise_path(tail)

            edge = Edge(
                record.name, target, signal.via, method, float(score),
                [signal.evidence],
                paths=[called_path] if called_path else [],
            )
            existing = merged.get(edge.key())
            if existing is None:
                merged[edge.key()] = edge
            else:
                if edge.score > existing.score:
                    existing.score = edge.score
                    existing.method = edge.method
                if signal.evidence not in existing.evidence:
                    existing.evidence.append(signal.evidence)
                for known in edge.paths:
                    if known not in existing.paths:
                        existing.paths.append(known)

    edges = sorted(
        merged.values(), key=lambda e: (-e.score, e.source, e.target)
    )
    unresolved.sort(key=lambda u: (u.source, u.signal, u.value))
    external.sort(key=lambda x: (x.source, x.value))
    infrastructure = build_nodes({r.name: r.infra for r in repos})
    return EstateMap(repos, edges, unresolved, workspace, external,
                     infrastructure)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def write_json(estate: EstateMap, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(estate.as_dict(), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


KIND_LABEL = {
    "backend": "service", "client": "client app", "legacy": "legacy system",
}


def render_register(estate: EstateMap) -> str:
    """ESTATE.md - the human-readable register of the estate.

    Written to read like a property register, not a data dump: one entry per
    service, in plain sentences, with the connections spelled out.
    """
    lines: list[str] = []
    lines.append("# The estate")
    lines.append("")
    lines.append(
        "_Generated by `estate scan`. Every connection below cites the file "
        "and line that proves it. Do not edit by hand — rerun the scan._"
    )
    lines.append("")

    backends = [r for r in estate.repos if r.kind == "backend"]
    clients = [r for r in estate.repos if r.kind == "client"]
    legacy = [r for r in estate.repos if r.kind == "legacy"]
    unknown = [r for r in estate.repos if not r.primary_stack]

    lines.append("## At a glance")
    lines.append("")
    lines.append(f"- **{len(estate.repos)}** repos")
    lines.append(
        f"- **{len(backends)}** services, **{len(clients)}** client apps, "
        f"**{len(legacy)}** legacy systems"
    )
    lines.append(f"- **{len(estate.edges)}** connections found")
    if estate.unresolved:
        lines.append(
            f"- **{len(estate.unresolved)}** need confirming — see "
            f"[Needs confirming](#needs-confirming)"
        )
    if unknown:
        lines.append(f"- **{len(unknown)}** repos whose stack was not recognised")
    lines.append("")

    by_stack: dict[str, int] = {}
    for record in estate.repos:
        by_stack[record.primary_stack or "unrecognised"] = (
            by_stack.get(record.primary_stack or "unrecognised", 0) + 1
        )
    lines.append("| Stack | Repos |")
    lines.append("| --- | --- |")
    for stack, count in sorted(by_stack.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {stack} | {count} |")
    lines.append("")

    for heading, group in (
        ("Services", backends), ("Client apps", clients),
        ("Legacy systems", legacy), ("Unrecognised", unknown),
    ):
        group = [r for r in group if r not in (unknown if heading != "Unrecognised" else [])]
        if not group:
            continue
        lines.append(f"## {heading}")
        lines.append("")
        for record in sorted(group, key=lambda r: r.name):
            lines.extend(_render_repo(estate, record))
        lines.append("")

    if estate.external:
        lines.append("## Outside the estate")
        lines.append("")
        lines.append(
            "Third-party services and vendor SDKs these repos depend on. "
            "Nothing to confirm here — it is listed because \"what outside "
            "services do we rely on\" is a question people ask constantly."
        )
        lines.append("")
        grouped: dict[str, list[str]] = {}
        for item in estate.external:
            grouped.setdefault(item.source, []).append(item.value)
        lines.append("| Repo | Depends on |")
        lines.append("| --- | --- |")
        for repo_name in sorted(grouped):
            values = sorted(dict.fromkeys(grouped[repo_name]))
            shown = ", ".join(f"`{v}`" for v in values[:8])
            more = f" (+{len(values) - 8} more)" if len(values) > 8 else ""
            lines.append(f"| `{repo_name}` | {shown}{more} |")
        lines.append("")

    if estate.unresolved:
        lines.append("## Needs confirming")
        lines.append("")
        lines.append(
            "These look like connections but could not be pinned to one "
            "service. Confirming a line here once is worth more than any "
            "amount of guessing — add the answer to the calling repo's "
            "`.agent/estate.yaml` under `consumes:` and it will stop being "
            "asked."
        )
        lines.append("")
        lines.append("| From | Sees | Why it is unclear | Evidence |")
        lines.append("| --- | --- | --- | --- |")
        for item in estate.unresolved[:60]:
            candidates = (
                f" (maybe: {', '.join(item.candidates)})"
                if item.candidates else ""
            )
            value = item.value if len(item.value) < 60 else item.value[:57] + "…"
            lines.append(
                f"| `{item.source}` | `{value}` | {item.reason}{candidates} "
                f"| `{item.evidence}` |"
            )
        if len(estate.unresolved) > 60:
            lines.append(
                f"\n_…and {len(estate.unresolved) - 60} more in "
                f"`estate/graph.json`._"
            )
        lines.append("")

    lines.append("## How to read this")
    lines.append("")
    lines.append(
        "Connections are ranked by how they were found. `declared` means the "
        "code names the service outright; `dependency` means a generated "
        "client for it is a dependency; `env` means a configured variable "
        "names it; `host` means a URL pointed at it; `path` means the called "
        "path matches exactly one service's endpoint. Anything that could "
        "have meant two services is in *Needs confirming* rather than guessed."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


def _render_repo(estate: EstateMap, record: RepoRecord) -> list[str]:
    lines: list[str] = []
    label = KIND_LABEL.get(record.kind, record.kind)
    stack = record.primary_stack or "unrecognised"
    lines.append(f"### `{record.name}`")
    lines.append("")
    lines.append(f"{stack} · {label} · `{record.path}`")
    lines.append("")

    if record.contracts:
        shown = ", ".join(f"`{c}`" for c in record.contracts[:5])
        more = f" (+{len(record.contracts) - 5} more)" if len(record.contracts) > 5 else ""
        lines.append(f"**Contracts:** {shown}{more}")
        lines.append("")

    if record.endpoints:
        lines.append(f"**Exposes {len(record.endpoints)} endpoints**, including:")
        lines.append("")
        for endpoint in record.endpoints[:8]:
            method = endpoint.method or "ANY"
            lines.append(f"- `{method} {endpoint.path}` — `{endpoint.evidence}`")
        if len(record.endpoints) > 8:
            lines.append(f"- _…and {len(record.endpoints) - 8} more_")
        lines.append("")

    callers = estate.callers_of(record.name)
    if callers:
        lines.append("**Called by:**")
        lines.append("")
        for edge in callers:
            lines.append(
                f"- `{edge.source}` via {edge.via} "
                f"({edge.method}, {edge.score:.2f}) — `{edge.evidence[0]}`"
            )
        lines.append("")

    callees = estate.callees_of(record.name)
    if callees:
        lines.append("**Calls:**")
        lines.append("")
        for edge in callees:
            lines.append(
                f"- `{edge.target}` via {edge.via} "
                f"({edge.method}, {edge.score:.2f}) — `{edge.evidence[0]}`"
            )
        lines.append("")

    if not callers and not callees:
        lines.append("_No connections found._")
        lines.append("")

    for note in record.notes:
        lines.append(f"> {note}")
        lines.append("")

    if not record.has_deed:
        lines.append(
            "> No deed yet. Run `estate init` here so agents know how to work "
            "in this repo."
        )
        lines.append("")

    return lines
