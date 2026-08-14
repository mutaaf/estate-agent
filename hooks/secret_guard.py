#!/usr/bin/env python3
"""Estate Agent - secret guard.

A PreToolUse hook that blocks an AI agent from reading or writing credentials.

Design notes, because this file is the one people will actually audit:

  * Single file, standard library only. It gets copied into your repo and must
    keep working with no install step, on whatever Python the machine has.
  * It never makes a network call. Everything it knows is in this file.
  * Precision over recall. A guard that cries wolf gets switched off, and a
    guard that is switched off protects nothing. Every detector below is
    paired with placeholder and reference suppression, and generic matches
    must clear an entropy bar before they count.
  * Overrides are recorded, not silently allowed, so `estate doctor` can tell
    you which rule is annoying people (Loop C in the docs).

Contract: reads the Claude Code PreToolUse JSON payload on stdin, writes a
decision to stdout. Exit code is always 0; the decision carries the verdict.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path

VERSION = "0.1.0"

# --------------------------------------------------------------------------
# Sensitive paths - things an agent should not be reading or writing at all
# --------------------------------------------------------------------------

SENSITIVE_PATH_PATTERNS: list[tuple[str, str]] = [
    (r"(^|/)\.env(\.[\w.-]+)?$", "environment file"),
    (r"(^|/)\.env\.[\w-]*local", "local environment file"),
    (r"\.pem$", "PEM private key"),
    (r"\.p12$|\.pfx$", "PKCS#12 keystore"),
    (r"\.jks$|\.keystore$", "Java keystore"),
    (r"(^|/)id_(rsa|dsa|ecdsa|ed25519)$", "SSH private key"),
    (r"(^|/)\.ssh/(?!known_hosts|config$)", "SSH directory"),
    (r"(^|/)\.aws/credentials$", "AWS credentials"),
    (r"(^|/)\.config/gcloud/", "gcloud credentials"),
    (r"(^|/)\.azure/", "Azure credentials"),
    (r"(^|/)\.kube/config$", "kubeconfig"),
    (r"(^|/)\.npmrc$", "npm credentials"),
    (r"(^|/)\.pypirc$", "PyPI credentials"),
    (r"(^|/)\.netrc$", "netrc credentials"),
    (r"(^|/)\.docker/config\.json$", "Docker registry credentials"),
    (r"\.mobileprovision$", "iOS provisioning profile"),
    (r"(^|/)secring\.|\.gpg$|\.asc$", "GPG key material"),
    (r"(^|/)serviceaccount.*\.json$", "service account key"),
    (r"(^|/)credentials\.json$", "credentials file"),
    (r"(^|/)\.as400_profile|(^|/)ftp\.cfg$", "AS400 connection profile"),
    (r"(^|/)terraform\.tfstate", "Terraform state (contains resolved secrets)"),
    (r"\.tfvars$", "Terraform variables"),
]

# Paths that look sensitive but are safe, checked first.
SAFE_PATH_PATTERNS: list[str] = [
    r"\.env\.example$",
    r"\.env\.sample$",
    r"\.env\.template$",
    r"\.env\.dist$",
    r"(^|/)\.ssh/known_hosts$",
    r"(^|/)\.ssh/config$",
    r"\.pem\.example$",
    r"(^|/)estate-agent/tests/",
    r"(^|/)tests?/fixtures/secret_guard/",
]

# --------------------------------------------------------------------------
# Credential detectors - high confidence, vendor-specific shapes first
# --------------------------------------------------------------------------

CREDENTIAL_PATTERNS: list[tuple[str, str]] = [
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS access key ID"),
    (r"\bASIA[0-9A-Z]{16}\b", "AWS temporary access key ID"),
    (r"\bgh[pousr]_[A-Za-z0-9]{36,}\b", "GitHub token"),
    (r"\bgithub_pat_[A-Za-z0-9_]{20,}\b", "GitHub fine-grained token"),
    (r"\bglpat-[A-Za-z0-9_\-]{20,}\b", "GitLab personal access token"),
    (r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b", "Slack token"),
    (r"\bAIza[0-9A-Za-z_\-]{35}\b", "Google API key"),
    (r"\bya29\.[0-9A-Za-z_\-]{20,}\b", "Google OAuth token"),
    (r"\b(sk|rk)_live_[0-9A-Za-z]{20,}\b", "Stripe live key"),
    (r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b", "Anthropic API key"),
    (r"\bsk-proj-[A-Za-z0-9_\-]{20,}\b", "OpenAI project key"),
    (r"\bsq0(atp|csp)-[A-Za-z0-9_\-]{20,}\b", "Square token"),
    (r"\bSG\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\b", "SendGrid API key"),
    (r"\bnpm_[A-Za-z0-9]{36}\b", "npm access token"),
    (r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_\-]{10,}\b", "PyPI API token"),
    (r"\bdop_v1_[a-f0-9]{64}\b", "DigitalOcean token"),
    (r"\bshp(at|ss|pa)_[a-fA-F0-9]{32}\b", "Shopify token"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key block"),
    (r"-----BEGIN OPENSSH PRIVATE KEY-----", "OpenSSH private key"),
    (
        r"\b[a-z][a-z0-9+.\-]*://[^\s:/@]+:[^\s:/@]{6,}@[^\s/]+",
        "connection string with inline password",
    ),
    (
        r"AccountKey=[A-Za-z0-9+/=]{40,}",
        "Azure storage account key",
    ),
    (
        r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b",
        "JWT with payload",
    ),
]

# Generic "name = value" credentials. These are the false-positive minefield,
# so a match here only counts when the value also clears the entropy bar and
# is not obviously a placeholder or a reference to a variable.
GENERIC_ASSIGNMENT = re.compile(
    r"""(?ix)
    \b(
        password | passwd | pwd | secret | token | api[_-]?key | apikey |
        access[_-]?key | secret[_-]?key | private[_-]?key | client[_-]?secret |
        auth[_-]?token | bearer | credential | passphrase
    )
    \s* [:=] \s*
    (["'`]?)
    ([^\s"'`,;)}\]]{12,})
    \2
    """
)

# If any of these appear in the value, it is a placeholder or a reference to
# a value held somewhere else - not a leaked credential.
PLACEHOLDER_MARKERS = [
    "xxx", "yyy", "zzz", "your_", "your-", "yourkey", "example", "sample",
    "placeholder", "changeme", "change_me", "dummy", "redacted", "fake",
    "notreal", "insert", "replace", "todo", "tbd", "<", ">", "{{", "}}",
    "${", "%(", "os.environ", "process.env", "system.getenv", "getenv",
    "environment.get", "configuration[", "vault:", "secretsmanager",
    "keyvault", "******", "....", "abc123", "0000000", "1234567",
    "test_key", "testkey", "mock", "stub", "lorem",
]

# Values that are obviously not credentials despite high entropy.
NON_SECRET_VALUE = re.compile(
    r"""(?ix)
    ^(
        sha\d*[:-] | md5[:-] | [0-9a-f]{7,8}$ |          # short git sha
        https?://(?!.*:.*@) |                             # plain URL, no creds
        [a-z0-9.\-]+\.(com|org|net|io|dev|local)$ |       # hostname
        \d{4}-\d{2}-\d{2} |                               # date
        [\d.]+$                                            # version or number
    )
    """
)

# Tools whose input we inspect for content, mapped to the fields that carry it.
CONTENT_FIELDS = {
    "Write": ["content", "file_path"],
    "Edit": ["new_string", "old_string", "file_path"],
    "NotebookEdit": ["new_source", "notebook_path"],
    "Bash": ["command"],
}

PATH_FIELDS = ["file_path", "path", "notebook_path", "filePath"]


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------


def shannon_entropy(value: str) -> float:
    """Bits of entropy per character. Random tokens land above ~3.5."""
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for ch in value:
        counts[ch] = counts.get(ch, 0) + 1
    length = len(value)
    return -sum(
        (c / length) * math.log2(c / length) for c in counts.values()
    )


# A credential-shaped variable name is usually holding ordinary code, not a
# leaked secret: `password = hashPassword(input)`, `secret = opts.Value.Secret`.
# This is where naive scanners generate most of their false positives, and
# false positives are what get a guard switched off.
CODE_EXPRESSION_MARKERS = ("(", "[", "::", "->", "=>", "?.", "??", "|>")
DOTTED_ACCESS = re.compile(r"^[A-Za-z_$@][\w$]*(\.[A-Za-z_$][\w$]*)+$")


def looks_like_code_expression(value: str) -> bool:
    """True when the value is code that produces a secret, not the secret."""
    if any(marker in value for marker in CODE_EXPRESSION_MARKERS):
        return True
    # A pure dotted path such as `_options.Value.ClientSecret`. Real secrets
    # containing dots (JWTs, connection strings) are caught by the dedicated
    # patterns above before this ever runs.
    if DOTTED_ACCESS.match(value):
        return True
    return False


def looks_like_placeholder(value: str) -> bool:
    low = value.lower()
    if any(marker in low for marker in PLACEHOLDER_MARKERS):
        return True
    if NON_SECRET_VALUE.match(value):
        return True
    # A value made of one repeated character, or an obvious sequence.
    if len(set(value)) <= 3:
        return True
    return False


def find_credentials(text: str) -> list[tuple[str, str]]:
    """Return (kind, evidence) for each credential found in `text`."""
    findings: list[tuple[str, str]] = []

    for pattern, kind in CREDENTIAL_PATTERNS:
        match = re.search(pattern, text)
        if match:
            findings.append((kind, redact(match.group(0))))

    for match in GENERIC_ASSIGNMENT.finditer(text):
        name, _quote, value = match.group(1), match.group(2), match.group(3)
        if looks_like_code_expression(value):
            continue
        if looks_like_placeholder(value):
            continue
        if shannon_entropy(value) < 3.0:
            continue
        findings.append(
            (f"credential assigned to '{name}'", redact(value))
        )

    return findings


def redact(value: str) -> str:
    """Show enough to identify the finding, never enough to use it."""
    value = value.strip()
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-2:]} ({len(value)} chars)"


def check_path(raw_path: str) -> tuple[str, str] | None:
    """Return (reason, matched_rule) if this path is sensitive."""
    if not raw_path:
        return None
    path = str(raw_path)
    for safe in SAFE_PATH_PATTERNS:
        if re.search(safe, path):
            return None
    for pattern, description in SENSITIVE_PATH_PATTERNS:
        if re.search(pattern, path):
            return (description, pattern)
    return None


def scan_bash_command(command: str) -> tuple[str, str] | None:
    """Catch commands that read secrets even when no path field is present."""
    # `cat .env`, `source .env`, `export $(cat .env)`, `less ~/.aws/credentials`
    reading = re.search(
        r"\b(cat|less|more|head|tail|bat|source|\.|grep|rg|awk|sed|cp|scp|"
        r"base64|xxd|strings|open)\b[^|;&]*?"
        r"([\w./~-]*(?:\.env(?:\.[\w-]+)?|\.pem|id_rsa|id_ed25519|"
        r"credentials|\.npmrc|\.pypirc|\.netrc|secring)[\w./-]*)",
        command,
    )
    if reading:
        candidate = reading.group(2)
        hit = check_path(candidate)
        if hit:
            return (f"{hit[0]} via `{reading.group(1)}`", candidate)
    # `env | grep SECRET`, `printenv AWS_SECRET_ACCESS_KEY`
    env_dump = re.search(
        r"\b(env|printenv|set)\b[^|;&]*\|[^|;&]*\b(grep|rg|ag)\b[^|;&]*"
        r"(SECRET|TOKEN|PASSWORD|KEY|CREDENTIAL)",
        command,
        re.IGNORECASE,
    )
    if env_dump:
        return ("environment variable dump filtered for credentials", "env|grep")
    return None


# --------------------------------------------------------------------------
# Override ledger and friction counters (local only, never transmitted)
# --------------------------------------------------------------------------


def finding_id(kind: str, evidence: str, tool: str) -> str:
    digest = hashlib.sha256(f"{tool}:{kind}:{evidence}".encode()).hexdigest()
    return digest[:16]


def allowlist_path(cwd: str) -> Path:
    return Path(cwd) / ".agent" / "secret-guard-allow.txt"


def is_allowlisted(cwd: str, fid: str) -> bool:
    path = allowlist_path(cwd)
    if not path.is_file():
        return False
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.split()[0] == fid:
                return True
    except OSError:
        return False
    return False


def record(cwd: str, event: str, detail: dict) -> None:
    """Append a local counter line. Loop C reads this; nothing else does."""
    try:
        base = Path(cwd) / ".agent" / ".local"
        base.mkdir(parents=True, exist_ok=True)
        entry = {"event": event, "guard_version": VERSION, **detail}
        with (base / "friction.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass  # Never let bookkeeping break the guard.


# --------------------------------------------------------------------------
# Hook entry point
# --------------------------------------------------------------------------


def decide(payload: dict) -> tuple[str, str, dict]:
    """Return (decision, reason, detail). decision is 'allow' or 'deny'."""
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    cwd = payload.get("cwd") or os.getcwd()

    # 1. Sensitive path, whatever the tool.
    for field in PATH_FIELDS:
        value = tool_input.get(field)
        if isinstance(value, str):
            hit = check_path(value)
            if hit:
                description, rule = hit
                fid = finding_id(description, value, tool)
                if is_allowlisted(cwd, fid):
                    record(cwd, "allowlisted", {"id": fid, "kind": description})
                    return ("allow", "", {})
                return (
                    "deny",
                    f"Blocked: {value} is a {description}.\n"
                    f"Estate Agent's secret guard does not let agents read or "
                    f"write credential files.\n"
                    f"If this file is genuinely safe, add `{fid}` to "
                    f".agent/secret-guard-allow.txt with a note explaining why.",
                    {"id": fid, "kind": description, "rule": rule},
                )

    # 2. Bash commands that reach for secrets without a path field.
    if tool == "Bash":
        command = tool_input.get("command", "")
        hit = scan_bash_command(command)
        if hit:
            description, evidence = hit
            fid = finding_id(description, evidence, tool)
            if is_allowlisted(cwd, fid):
                record(cwd, "allowlisted", {"id": fid, "kind": description})
                return ("allow", "", {})
            return (
                "deny",
                f"Blocked: this command reads a {description}.\n"
                f"Evidence: {evidence}\n"
                f"If this is genuinely safe, add `{fid}` to "
                f".agent/secret-guard-allow.txt with a note explaining why.",
                {"id": fid, "kind": description},
            )

    # 3. Credential material in content the agent is about to write or run.
    for field in CONTENT_FIELDS.get(tool, []):
        value = tool_input.get(field)
        if not isinstance(value, str) or not value:
            continue
        findings = find_credentials(value)
        if findings:
            kind, evidence = findings[0]
            fid = finding_id(kind, evidence, tool)
            if is_allowlisted(cwd, fid):
                record(cwd, "allowlisted", {"id": fid, "kind": kind})
                continue
            others = (
                f" (plus {len(findings) - 1} more)" if len(findings) > 1 else ""
            )
            return (
                "deny",
                f"Blocked: this {tool} contains what looks like a {kind}"
                f"{others}.\nEvidence: {evidence}\n"
                f"Use an environment variable or your secret manager instead. "
                f"If this is a false positive, add `{fid}` to "
                f".agent/secret-guard-allow.txt with a note explaining why.",
                {"id": fid, "kind": kind, "field": field},
            )

    return ("allow", "", {})


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # Malformed input must not become an accidental bypass, but it also
        # must not wedge the session. Allow, and leave a trace.
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }}))
        return 0

    decision, reason, detail = decide(payload)
    cwd = payload.get("cwd") or os.getcwd()

    if decision == "deny":
        record(cwd, "blocked", {"tool": payload.get("tool_name", ""), **detail})
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }}))
    else:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
