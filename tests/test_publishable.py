#!/usr/bin/env python3
"""Is this repo safe to publish?

Estate Agent is a public repo whose design was shaped by looking at a real,
private, ten-stack estate. That is exactly the situation where a company
hostname or an internal service name leaks into a commit and stays there
forever.

So the project points its own secret detector at itself, and CI fails if
anything identifying appears. The rule this enforces: **your estate shapes the
detection patterns, never the names.**

Run:  python3 tests/test_publishable.py
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks"))
sys.path.insert(0, str(ROOT / "src"))

import secret_guard  # noqa: E402

# Files that legitimately contain credential-shaped strings.
EXEMPT = {
    "tests/test_secret_guard.py",   # the adversarial battery, by definition
    "hooks/secret_guard.py",        # the detectors themselves
    "tests/test_publishable.py",    # this file
    # Plants identifying-looking strings on purpose and asserts the field
    # report strips them. The fakes have to be there for the test to mean
    # anything.
    "tests/test_report.py",
    # Estate Agent runs `estate init` on itself, which installs a copy of the
    # guard here. Same file, same reason for exemption. A test below asserts
    # the copy has not drifted from its source.
    ".agent/hooks/secret_guard.py",
}

SCANNED_SUFFIXES = {
    ".py", ".md", ".yaml", ".yml", ".json", ".html", ".css", ".js", ".txt",
    ".toml", ".sh", ".mdc",
}

# Things that identify a person, a company, or a machine.
IDENTIFYING = [
    (r"/Users/[a-z]", "an absolute path from someone's laptop"),
    (r"/home/[a-z][\w-]{2,}", "an absolute home directory path"),
    (r"C:\\\\Users\\\\", "a Windows user path"),
    (
        r"\b[\w.+-]+@(?!example\.com|example\.org)[\w-]+\.[a-z]{2,}\b",
        "an email address",
    ),
    (
        r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b",
        "a private IP address",
    ),
    (
        # An internal hostname, but not a filename that happens to look like
        # one: docker-compose.prod.yml and shared-cache-prod.internal.md are
        # not hosts. A linter that cries wolf gets ignored, which is the same
        # rule the secret guard lives by.
        r"\b[\w-]+\.(?:corp|internal|intranet|local|lan|prod|priv)\."
        r"(?!ya?ml\b|md\b|json\b|txt\b|py\b|[jt]sx?\b|toml\b|cfg\b|"
        r"properties\b|html\b|css\b|sh\b|lock\b)[\w-]{2,}\b",
        "an internal hostname",
    ),
]


# Addresses that are meant to be public: git's own no-reply forms, and the
# co-authorship trailer. Flagging these would make the check cry wolf on every
# commit, and a check people learn to ignore protects nothing.
ALLOWED_EMAIL_HOSTS = (
    "users.noreply.github.com", "noreply.github.com", "noreply@github.com",
    "noreply@anthropic.com", "example.com", "example.org",
)

_DIFF_HEADER = re.compile(r"^diff --git a/(\S+) b/(\S+)$", re.MULTILINE)


def _diff_sections(diff: str) -> list[tuple[str, str]]:
    """Split `git log -p` output into (path, hunk) pairs.

    The working-tree check exempts files by path. History has to do the same,
    or the fake credentials in the adversarial battery are reported forever.
    """
    sections: list[tuple[str, str]] = []
    matches = list(_DIFF_HEADER.finditer(diff))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(diff)
        sections.append((match.group(2), diff[start:end]))
    return sections


def _is_allowed_in_history(text: str) -> bool:
    return any(host in text for host in ALLOWED_EMAIL_HOSTS)


def publishable_paths() -> set[str] | None:
    """Exactly the files that would end up in the published repo.

    Asking git is the only correct answer: walking the filesystem also picks
    up generated scan output and other ignored files, which are not published
    and whose contents are not our problem. Returns None when git is
    unavailable, and the caller falls back to walking.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    return set(result.stdout.split())


def scanned_files() -> list[Path]:
    published = publishable_paths()
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if published is not None and str(relative) not in published:
            continue  # git ignores it, so it is never published
        parts = set(relative.parts)
        if parts & {".git", "__pycache__", "_build", ".venv", "node_modules"}:
            continue
        if str(relative) in EXEMPT:
            continue
        if path.suffix.lower() not in SCANNED_SUFFIXES and path.name != "estate":
            continue
        files.append(path)
    return sorted(files)


def private_terms() -> list[str]:
    """Terms from a local, git-ignored `.publish-denylist`.

    A public repo cannot contain a list of your employer's internal service
    names - writing them down to check for them would leak them, which is the
    whole problem. So the list lives in a git-ignored file that never leaves
    your machine, and only the mechanism is public.

    One term per line, `#` for comments. Matching is case-insensitive and
    whole-word.
    """
    path = ROOT / ".publish-denylist"
    if not path.is_file():
        return []
    terms: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if len(line) >= 3:
            terms.append(line)
    return terms


class NothingIdentifying(unittest.TestCase):
    def test_no_private_terms(self) -> None:
        """Checks your own denylist, if you have one. Skips if you do not."""
        terms = private_terms()
        if not terms:
            self.skipTest(
                "no .publish-denylist - create one (git-ignored) to check for "
                "your organisation's internal names"
            )
        offences: list[str] = []
        for path in scanned_files():
            text = path.read_text(encoding="utf-8", errors="replace").lower()
            for term in terms:
                if re.search(rf"\b{re.escape(term.lower())}\b", text):
                    offences.append(f"{path.relative_to(ROOT)}: {term}")
        self.assertEqual(
            [], offences,
            "private terms found in a public repo:\n  " + "\n  ".join(offences),
        )

    def test_no_personal_or_company_identifiers(self) -> None:
        offences: list[str] = []
        for path in scanned_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern, description in IDENTIFYING:
                for match in re.finditer(pattern, text):
                    line = text[: match.start()].count("\n") + 1
                    offences.append(
                        f"{path.relative_to(ROOT)}:{line} contains "
                        f"{description}: {match.group(0)[:60]}"
                    )
        self.assertEqual(
            [], offences,
            "This repo is published. These would be public forever:\n  "
            + "\n  ".join(offences),
        )

    def test_no_credentials_anywhere(self) -> None:
        """Point the project's own secret detector at the project."""
        offences: list[str] = []
        for path in scanned_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            for kind, evidence in secret_guard.find_credentials(text):
                offences.append(
                    f"{path.relative_to(ROOT)}: {kind} ({evidence})"
                )
        self.assertEqual([], offences, "credential material in a public repo")


class LicensedAndDocumented(unittest.TestCase):
    def test_has_a_licence(self) -> None:
        licence = ROOT / "LICENSE"
        self.assertTrue(licence.is_file())
        self.assertIn("MIT License", licence.read_text(encoding="utf-8"))

    def test_entry_points_exist(self) -> None:
        for name in ("README.md", "AGENT.md", "docs/data-flow.md"):
            self.assertTrue((ROOT / name).is_file(), f"missing {name}")

    def test_readme_links_resolve(self) -> None:
        """A broken link on the landing page is the first thing people hit."""
        broken: list[str] = []
        for name in ("README.md", "AGENT.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            for match in re.finditer(r"\]\((?!https?://|#)([^)]+)\)", text):
                target = match.group(1).split("#")[0]
                if target and not (ROOT / target).exists():
                    broken.append(f"{name} -> {target}")
        self.assertEqual([], broken, f"broken links: {broken}")

    def test_docs_link_to_each_other_correctly(self) -> None:
        broken: list[str] = []
        for path in (ROOT / "docs").rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"\]\((?!https?://|#)([^)]+)\)", text):
                target = match.group(1).split("#")[0]
                if not target:
                    continue
                if not (path.parent / target).resolve().exists():
                    broken.append(f"{path.relative_to(ROOT)} -> {target}")
        self.assertEqual([], broken, f"broken doc links: {broken}")


class HistoryIsClean(unittest.TestCase):
    def test_git_history_has_no_identifiers(self) -> None:
        """A file cleaned up in a later commit is still public in an earlier
        one. Checking the working tree alone is not enough."""
        if not (ROOT / ".git").exists():
            self.skipTest("not a git repo yet")
        try:
            diff = subprocess.run(
                ["git", "log", "-p", "--all", "--no-color"],
                cwd=ROOT, capture_output=True, text=True, timeout=120,
            ).stdout
        except (subprocess.SubprocessError, OSError):
            self.skipTest("git unavailable")

        if not diff.strip():
            self.skipTest("no commits yet")

        offences: list[str] = []
        for path, section in _diff_sections(diff):
            if path in EXEMPT:
                continue  # The adversarial battery contains fakes by design.
            # Only added content counts. Scanning the whole section would also
            # sweep in the next commit's Author line, which trails the last
            # diff of the previous one and is not part of any file.
            added = "\n".join(
                line for line in section.splitlines()
                if line.startswith("+") and not line.startswith("+++")
            )
            for pattern, description in IDENTIFYING:
                for item in set(re.findall(pattern, added)):
                    text = item if isinstance(item, str) else str(item)
                    if _is_allowed_in_history(text):
                        continue
                    offences.append(f"{path}: {description}: {text[:60]}")
        self.assertEqual(
            [], offences,
            "git history contains identifying information - it must be "
            "rewritten before publishing, not just deleted:\n  "
            + "\n  ".join(offences),
        )


class NothingImportantIsIgnored(unittest.TestCase):
    """Files the test suite needs must actually be committed.

    An over-broad .gitignore excluded `tests/fixtures/estate/` and
    `docs/estate.md` from the first push: the pattern `estate/` matches any
    directory of that name at any depth. Everything passed locally and the
    published repo was broken. Anchoring the patterns fixed it; this test
    stops it coming back.
    """

    REQUIRED = [
        "tests/fixtures/estate/payments-api/pom.xml",
        "tests/fixtures/estate/ios-app/Sources/Endpoints.swift",
        "tests/fixtures/estate/roku-app/source/Api.brs",
        "docs/estate.md",
        "docs/data-flow.md",
        "stacks/java.yaml",
        "stacks/as400.yaml",
        "hooks/secret_guard.py",
        "templates/settings/permissions.json",
        "bin/estate",
    ]

    def test_required_files_are_tracked(self) -> None:
        if not (ROOT / ".git").exists():
            self.skipTest("not a git repo")
        try:
            tracked = set(subprocess.run(
                ["git", "ls-files"], cwd=ROOT, capture_output=True,
                text=True, timeout=60,
            ).stdout.split())
        except (subprocess.SubprocessError, OSError):
            self.skipTest("git unavailable")
        missing = [p for p in self.REQUIRED if p not in tracked]
        self.assertEqual(
            [], missing,
            "these exist on disk but are not committed - check .gitignore:\n  "
            + "\n  ".join(missing),
        )

    def test_the_installed_guard_matches_its_source(self) -> None:
        """This repo dogfoods itself, so it carries an installed copy of the
        secret guard. A copy that drifts from its source is a copy that stops
        being the thing under test."""
        source = ROOT / "hooks" / "secret_guard.py"
        installed = ROOT / ".agent" / "hooks" / "secret_guard.py"
        if not installed.is_file():
            self.skipTest("not initialised on itself")
        self.assertEqual(
            source.read_text(encoding="utf-8"),
            installed.read_text(encoding="utf-8"),
            "run `estate init . --force` to refresh the installed copy",
        )

    def test_every_stack_profile_is_tracked(self) -> None:
        if not (ROOT / ".git").exists():
            self.skipTest("not a git repo")
        tracked = set(subprocess.run(
            ["git", "ls-files", "stacks"], cwd=ROOT, capture_output=True,
            text=True,
        ).stdout.split())
        on_disk = {
            str(p.relative_to(ROOT)) for p in (ROOT / "stacks").glob("*.yaml")
        }
        self.assertEqual(on_disk, tracked, "a stack profile is not committed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
