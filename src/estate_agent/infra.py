"""Shared infrastructure: clusters, caches, datastores, queues, buckets.

Services do not only call each other. They also *share things* - a cache
cluster, a database, a Kafka topic - and "which services share this cluster"
is one of the questions that is hardest to answer and most expensive to get
wrong during an incident.

Infrastructure config is language-neutral, which is the same reason the rest
of Estate Agent reads contracts rather than parsing source: docker-compose,
Terraform, ECS task definitions, Kubernetes manifests and Spring properties
look the same whether the service behind them is Java or Rust.

The precision rule that governs this file
-----------------------------------------

A shared node is only created when two services name the *same instance* -
the same hostname, cluster identifier, or Terraform resource. A service that
merely mentions a technology (`image: redis` in its own compose file for local
development) gets that recorded against it, but it does **not** join a shared
node. Otherwise every repo with a local Postgres appears to share one
database with every other, which is both false and alarming.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Technologies worth recognising, and what kind of thing each one is.
TECHNOLOGIES: dict[str, str] = {
    "postgres": "database", "postgresql": "database", "mysql": "database",
    "mariadb": "database", "mssql": "database", "sqlserver": "database",
    "oracle": "database", "mongodb": "database", "mongo": "database",
    "cassandra": "database", "scylla": "database", "cockroach": "database",
    "dynamodb": "database", "clickhouse": "database", "db2": "database",
    "redis": "cache", "valkey": "cache", "memcached": "cache",
    "hazelcast": "cache", "elasticache": "cache",
    "kafka": "queue", "rabbitmq": "queue", "sqs": "queue", "nats": "queue",
    "pulsar": "queue", "activemq": "queue", "msk": "queue",
    "servicebus": "queue", "eventhub": "queue", "kinesis": "queue",
    "elasticsearch": "search", "opensearch": "search", "solr": "search",
    "s3": "storage", "gcs": "storage", "blob": "storage", "minio": "storage",
    "vault": "secrets", "consul": "discovery", "etcd": "discovery",
    "zookeeper": "discovery",
}

# Hosts that mean "on my laptop", never a shared production dependency.
LOCAL_HOSTS = {
    "localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal", "db",
    "cache", "redis", "postgres", "mysql", "kafka", "mongo", "::1",
}

_FILES = [
    "docker-compose.yml", "docker-compose.yaml", "compose.yml",
    "compose.yaml", "docker-compose.prod.yml",
    "src/main/resources/application.yml",
    "src/main/resources/application.yaml",
    "src/main/resources/application.properties",
    "application.yml", "application.properties", "appsettings.json",
    "config/default.toml", "serverless.yml",
]
_GLOBS = [
    "*.tf", "infra/*.tf", "terraform/*.tf", "deploy/*.tf",
    "*.taskdef.json", "task-definition.json", "deploy/*.json",
    "k8s/*.yaml", "k8s/*.yml", "deploy/*.yaml", "chart/values.yaml",
    "ecs/*.json",
]

MAX_FILE_BYTES = 512 * 1024


@dataclass
class InfraRef:
    """One service's reference to a piece of infrastructure."""

    identity: str          # shared key, or "" when it is local-only
    display: str
    kind: str              # database | cache | queue | search | storage | ...
    technology: str
    evidence: str
    shared: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity, "name": self.display, "kind": self.kind,
            "technology": self.technology, "evidence": self.evidence,
            "shared": self.shared,
        }


@dataclass
class InfraNode:
    """A piece of infrastructure, and everything that uses it."""

    identity: str
    display: str
    kind: str
    technology: str
    users: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    @property
    def is_shared(self) -> bool:
        return len(self.users) > 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity, "name": self.display, "kind": self.kind,
            "technology": self.technology, "used_by": sorted(self.users),
            "evidence": self.evidence[:6], "shared": self.is_shared,
        }


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------

_CONNECTION_URL = re.compile(
    r"""(?ix)
    \b(
        jdbc:(?P<jdbc>\w+)://(?P<jdbchost>[\w.\-]+)
      | (?P<scheme>postgres|postgresql|mysql|mongodb|redis|rediss|valkey|
                   amqp|amqps|kafka|clickhouse|cassandra)
        ://(?:[^@/\s]+@)?(?P<host>[\w.\-]+)
    )
    """
)

_SPRING_HOST = re.compile(
    r"(?im)^\s*(?:spring\.)?(redis|data\.redis|kafka|datasource|elasticsearch|"
    r"mongodb)[\w.]*\.(?:host|bootstrap-servers|uris?|url|nodes)\s*[:=]\s*"
    r"[\"']?([\w.\-:,/]+)"
)

_TF_RESOURCE = re.compile(
    r'resource\s+"(aws_(?:rds_cluster|rds_instance|db_instance|'
    r'elasticache_cluster|elasticache_replication_group|msk_cluster|'
    r'dynamodb_table|sqs_queue|s3_bucket|opensearch_domain|'
    r'elasticsearch_domain|documentdb_cluster)|google_(?:sql_database_instance|'
    r'redis_instance|pubsub_topic)|azurerm_(?:postgresql_server|redis_cache|'
    r'servicebus_queue))"\s+"([\w-]+)"'
)

_TF_IDENTIFIER = re.compile(
    r'(?:cluster_identifier|identifier|name|bucket|domain_name|'
    r'replication_group_id)\s*=\s*"([^"]+)"'
)

_IMAGE = re.compile(r"(?im)^\s*[\"']?image[\"']?\s*[:=]\s*[\"']?([\w.\-/]+)")

_TF_KIND = {
    "rds": "database", "db_instance": "database", "documentdb": "database",
    "dynamodb": "database", "sql_database": "database",
    "postgresql_server": "database",
    "elasticache": "cache", "redis": "cache",
    "msk": "queue", "sqs": "queue", "pubsub": "queue", "servicebus": "queue",
    "opensearch": "search", "elasticsearch": "search",
    "s3_bucket": "storage",
}


def _technology_of(text: str) -> tuple[str, str] | None:
    lowered = text.lower()
    for name, kind in TECHNOLOGIES.items():
        if name in lowered:
            return (name, kind)
    return None


def _tf_kind_of(resource: str) -> tuple[str, str]:
    for marker, kind in _TF_KIND.items():
        if marker in resource:
            technology = _technology_of(resource)
            return (technology[0] if technology else marker, kind)
    return ("infrastructure", "infrastructure")


def _is_local(host: str) -> bool:
    label = host.split(":")[0].strip().lower()
    return label in LOCAL_HOSTS or label.endswith(".local") or not label


def _identity(host: str) -> str:
    """Normalise a host into a shared key. Empty means not shareable."""
    label = host.split(":")[0].strip().lower().rstrip(".")
    if _is_local(label):
        return ""
    # A hostname with no dots and no dashes is usually a compose service name,
    # i.e. local to that file rather than a shared cluster.
    if "." not in label and "-" not in label:
        return ""
    return label


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


_HOST_KEYS = {
    "host", "hostname", "url", "uri", "uris", "endpoint", "address",
    "bootstrap-servers", "bootstrapservers", "nodes", "servers", "cluster",
}


def _nested_hosts(text: str) -> list[tuple[str, str, str]]:
    """(technology, kind, host) from nested YAML config.

    Uses Estate Agent's own YAML reader, so this needs no dependency. The
    technology comes from the ancestor keys - `spring.data.redis.host` is a
    cache even though the line itself only says `host`.
    """
    from . import yamlite

    try:
        data = yamlite.load(text)
    except (yamlite.YamliteError, ValueError, RecursionError):
        return []
    if not isinstance(data, dict):
        return []

    found: list[tuple[str, str, str]] = []

    def walk(node: Any, trail: list[str], depth: int = 0) -> None:
        if depth > 8 or not isinstance(node, dict):
            return
        for key, value in node.items():
            name = str(key).lower()
            if isinstance(value, dict):
                walk(value, trail + [name], depth + 1)
                continue
            if name not in _HOST_KEYS or not isinstance(value, str):
                continue
            candidate = value.split(",")[0].strip()
            if not candidate or "${" in candidate:
                continue
            technology = _technology_of(" ".join(trail + [name])) \
                or _technology_of(candidate)
            if not technology:
                continue
            host = candidate
            match = re.search(r"//([\w.\-]+)", host)
            if match:
                host = match.group(1)
            host = host.split(":")[0]
            if host:
                found.append((technology[0], technology[1], host))

    walk(data, [])
    return found


def _find_line(text: str, needle: str) -> int:
    index = text.find(needle)
    return _line_of(text, index) if index >= 0 else 1


def _candidate_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for name in _FILES:
        path = root / name
        if path.is_file():
            found.append(path)
    for pattern in _GLOBS:
        for path in list(root.glob(pattern))[:20]:
            if path.is_file():
                found.append(path)
    result: list[Path] = []
    for path in found:
        try:
            if path.stat().st_size <= MAX_FILE_BYTES:
                result.append(path)
        except OSError:
            continue
    return result[:60]


def survey_infra(root: Path) -> list[InfraRef]:
    """Everything this repo says about the infrastructure it uses."""
    refs: list[InfraRef] = []
    seen: set[tuple[str, str]] = set()

    def add(ref: InfraRef) -> None:
        key = (ref.identity or ref.display, ref.kind)
        if key in seen:
            return
        seen.add(key)
        refs.append(ref)

    for path in _candidate_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            where = str(path.relative_to(root))
        except ValueError:
            where = path.name

        # 1. Connection strings - the strongest signal, because they name the
        #    actual instance.
        for match in _CONNECTION_URL.finditer(text):
            host = match.group("jdbchost") or match.group("host") or ""
            scheme = match.group("jdbc") or match.group("scheme") or ""
            technology = _technology_of(scheme) or _technology_of(host)
            if not technology:
                continue
            identity = _identity(host)
            add(InfraRef(
                identity=identity, display=host if identity else technology[0],
                kind=technology[1], technology=technology[0],
                evidence=f"{where}:{_line_of(text, match.start())}",
                shared=bool(identity),
            ))

        # 2. Host properties. Flat first (`spring.redis.host=...`), then the
        #    nested YAML form, where the technology is an ancestor key rather
        #    than part of the same line:
        #
        #      spring:
        #        data:
        #          redis:
        #            host: shared-cache-prod.internal
        for match in _SPRING_HOST.finditer(text):
            technology = _technology_of(match.group(1))
            host = match.group(2).split(",")[0]
            if not technology or "${" in host:
                continue
            identity = _identity(host)
            add(InfraRef(
                identity=identity, display=host if identity else technology[0],
                kind=technology[1], technology=technology[0],
                evidence=f"{where}:{_line_of(text, match.start())}",
                shared=bool(identity),
            ))

        if path.suffix in (".yml", ".yaml"):
            for tech, kind, host in _nested_hosts(text):
                identity = _identity(host)
                add(InfraRef(
                    identity=identity, display=host if identity else tech,
                    kind=kind, technology=tech,
                    evidence=f"{where}:{_find_line(text, host)}",
                    shared=bool(identity),
                ))

        # 3. Terraform resources - a declared, named, shared instance.
        if path.suffix == ".tf":
            for match in _TF_RESOURCE.finditer(text):
                resource, label = match.group(1), match.group(2)
                technology, kind = _tf_kind_of(resource)
                tail = text[match.end():match.end() + 400]
                named = _TF_IDENTIFIER.search(tail)
                display = named.group(1) if named else label
                add(InfraRef(
                    identity=display.lower(), display=display, kind=kind,
                    technology=technology,
                    evidence=f"{where}:{_line_of(text, match.start())}",
                    shared=True,
                ))

        # 4. Container images - usually local development, so recorded but
        #    never shared unless a connection string agrees.
        for match in _IMAGE.finditer(text):
            technology = _technology_of(match.group(1).split(":")[0])
            if not technology:
                continue
            add(InfraRef(
                identity="", display=technology[0], kind=technology[1],
                technology=technology[0],
                evidence=f"{where}:{_line_of(text, match.start())}",
                shared=False,
            ))

    return refs


def build_nodes(per_repo: dict[str, list[InfraRef]]) -> list[InfraNode]:
    """Collapse references into shared nodes.

    Only references carrying an identity - a real hostname or a declared
    resource - can join. Local-only references stay attached to their repo.
    """
    nodes: dict[str, InfraNode] = {}
    for repo, refs in sorted(per_repo.items()):
        for ref in refs:
            if not ref.shared or not ref.identity:
                continue
            node = nodes.get(ref.identity)
            if node is None:
                node = InfraNode(
                    ref.identity, ref.display, ref.kind, ref.technology
                )
                nodes[ref.identity] = node
            if repo not in node.users:
                node.users.append(repo)
            marker = f"{repo}:{ref.evidence}"
            if marker not in node.evidence:
                node.evidence.append(marker)
    return sorted(nodes.values(), key=lambda n: (-len(n.users), n.display))
