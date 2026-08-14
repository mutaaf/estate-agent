#!/usr/bin/env python3
"""Self-healing, tested by deliberately breaking things.

Self-healing is the feature nobody can verify by reading the code, so it is
tested by doing damage and checking the repair. Each test breaks one thing in
a real repo on disk and asserts both halves of the contract: that the damage
is noticed, and that the four safety rules hold while it is repaired.

  Rule 1  never overwrite human work
  Rule 2  never loosen a safety rule automatically
  Rule 3  never touch source code
  Rule 4  old setups keep working after an upgrade

Run:  python3 tests/test_upkeep.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from estate_agent import ui, yamlite  # noqa: E402
from estate_agent.deed import DEED_PATH  # noqa: E402
from estate_agent.initialise import cmd_init  # noqa: E402
from estate_agent.upkeep import cmd_upkeep  # noqa: E402

ui.COLOUR = False

DEED = """
estate_agent_version: 0.0.1
repo:
  name: payments-api
  summary: Handles card payments.
  stack: java
  tier: 2
commands:
  build: echo building
  test: echo testing
never_do:
  - Modify anything under src/generated
related_repos:
  - ledger-rust
  - a-repo-that-was-deleted
"""


class HealingCase(unittest.TestCase):
    """A real repo on disk, set up, then damaged."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.repo = self.workspace / "payments-api"
        (self.repo / "src" / "main" / "java").mkdir(parents=True)
        (self.repo / ".git").mkdir()
        (self.repo / "pom.xml").write_text(
            "<project><artifactId>payments-api</artifactId></project>",
            encoding="utf-8",
        )
        self.source = self.repo / "src" / "main" / "java" / "App.java"
        self.source.write_text(
            "class App { void run() { System.out.println(1); } }\n",
            encoding="utf-8",
        )
        (self.workspace / "ledger-rust").mkdir()

        (self.repo / ".agent").mkdir(parents=True, exist_ok=True)
        (self.repo / DEED_PATH).write_text(DEED, encoding="utf-8")
        self._sync()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    # -- helpers ---------------------------------------------------------

    def _sync(self) -> None:
        from estate_agent.cli import cmd_sync

        cmd_sync([str(self.repo), "--force"])

    def _upkeep(self, *extra: str) -> int:
        return cmd_upkeep([str(self.repo), *extra])

    def _deed(self) -> dict:
        return yamlite.load((self.repo / DEED_PATH).read_text(encoding="utf-8"))

    def _source_hash(self) -> str:
        return hashlib.sha256(self.source.read_bytes()).hexdigest()


class NoticesDamage(HealingCase):
    def test_regenerates_files_after_the_deed_changes(self) -> None:
        data = self._deed()
        data["commands"]["test"] = "echo different"
        (self.repo / DEED_PATH).write_text(yamlite.dump(data), encoding="utf-8")

        self._upkeep()

        self.assertIn(
            "echo different",
            (self.repo / "CLAUDE.md").read_text(encoding="utf-8"),
        )

    def test_drops_a_related_repo_that_no_longer_exists(self) -> None:
        self.assertIn("a-repo-that-was-deleted", self._deed()["related_repos"])
        self._upkeep()
        remaining = self._deed().get("related_repos", [])
        self.assertNotIn("a-repo-that-was-deleted", remaining)
        self.assertIn(
            "ledger-rust", remaining, "a repo that still exists must be kept"
        )

    def test_reports_a_command_that_no_longer_works(self) -> None:
        data = self._deed()
        data["commands"]["test"] = "./mvnw-that-was-deleted test"
        (self.repo / DEED_PATH).write_text(yamlite.dump(data), encoding="utf-8")

        self._upkeep()

        # Reported, not silently rewritten: choosing the replacement is a
        # judgement call, and guessing at someone's build command is worse
        # than telling them it is broken.
        self.assertEqual(
            "./mvnw-that-was-deleted test", self._deed()["commands"]["test"]
        )

    def test_prunes_a_connection_whose_evidence_was_deleted(self) -> None:
        graph_dir = self.workspace / "estate"
        graph_dir.mkdir()
        (graph_dir / "graph.json").write_text(json.dumps({
            "repos": [{"name": "payments-api", "path": "payments-api"}],
            "edges": [
                {"from": "payments-api", "to": "ledger-rust",
                 "evidence": ["src/main/java/App.java:1"]},
                {"from": "payments-api", "to": "ghost-service",
                 "evidence": ["src/main/java/Deleted.java:9"]},
            ],
        }), encoding="utf-8")

        self._upkeep()

        edges = json.loads(
            (graph_dir / "graph.json").read_text(encoding="utf-8")
        )["edges"]
        targets = {e["to"] for e in edges}
        self.assertIn("ledger-rust", targets, "evidence still on disk")
        self.assertNotIn(
            "ghost-service", targets, "evidence file is gone, so is the claim"
        )


class Rule1_NeverOverwriteHumanWork(HealingCase):
    def test_hand_edited_file_is_left_untouched(self) -> None:
        path = self.repo / "CLAUDE.md"
        edited = path.read_text(encoding="utf-8") + (
            "\n## Local note\n\nAsk Priya before touching reconciliation.\n"
        )
        path.write_text(edited, encoding="utf-8")

        data = self._deed()
        data["commands"]["test"] = "echo changed"
        (self.repo / DEED_PATH).write_text(yamlite.dump(data), encoding="utf-8")

        self._upkeep()

        after = path.read_text(encoding="utf-8")
        self.assertEqual(edited, after, "the hand-edited file must not change")
        self.assertIn("Ask Priya", after)

    def test_other_files_still_heal_around_the_protected_one(self) -> None:
        (self.repo / "CLAUDE.md").write_text(
            (self.repo / "CLAUDE.md").read_text(encoding="utf-8") + "\nmine\n",
            encoding="utf-8",
        )
        data = self._deed()
        data["commands"]["test"] = "echo changed"
        (self.repo / DEED_PATH).write_text(yamlite.dump(data), encoding="utf-8")

        self._upkeep()

        self.assertIn(
            "echo changed",
            (self.repo / "AGENTS.md").read_text(encoding="utf-8"),
            "protecting one file must not stop the others healing",
        )

    def test_init_keeps_a_copy_of_a_pre_existing_file(self) -> None:
        other = self.workspace / "checkout"
        (other / ".git").mkdir(parents=True)
        (other / "package.json").write_text('{"name":"checkout"}', encoding="utf-8")
        (other / "src").mkdir()
        (other / "src" / "a.ts").write_text("export const a = 1\n", encoding="utf-8")
        (other / "CLAUDE.md").write_text(
            "# Checkout\n\nAsk Sam before changing the basket logic.\n",
            encoding="utf-8",
        )

        cmd_init([str(other)])

        backup = other / "CLAUDE.md.before-estate-agent"
        self.assertTrue(backup.is_file(), "the original must be kept")
        self.assertIn("Ask Sam", backup.read_text(encoding="utf-8"))
        # And it must also survive into the new generated file, via the deed.
        self.assertIn(
            "Ask Sam", (other / "CLAUDE.md").read_text(encoding="utf-8")
        )


class Rule2_NeverLoosenSafety(HealingCase):
    def test_upkeep_does_not_relax_a_noisy_secret_rule(self) -> None:
        local = self.repo / ".agent" / ".local"
        local.mkdir(parents=True, exist_ok=True)
        (local / "friction.jsonl").write_text(
            "\n".join(
                json.dumps({"event": "allowlisted", "kind": "environment file"})
                for _ in range(9)
            ) + "\n",
            encoding="utf-8",
        )
        allow = self.repo / ".agent" / "secret-guard-allow.txt"

        self._upkeep()

        self.assertFalse(
            allow.is_file(),
            "an overridden rule must never be auto-allowlisted",
        )

    def test_upkeep_does_not_widen_permissions(self) -> None:
        settings = self.repo / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        original = {"permissions": {"deny": ["Bash(git push --force:*)"]}}
        settings.write_text(json.dumps(original), encoding="utf-8")

        self._upkeep()

        after = json.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual(
            original["permissions"]["deny"], after["permissions"]["deny"]
        )


class Rule3_NeverTouchSource(HealingCase):
    def test_source_files_are_untouched(self) -> None:
        before = self._source_hash()
        data = self._deed()
        data["commands"]["test"] = "echo changed"
        (self.repo / DEED_PATH).write_text(yamlite.dump(data), encoding="utf-8")

        self._upkeep()

        self.assertEqual(before, self._source_hash())

    def test_only_estate_agent_files_change(self) -> None:
        def snapshot() -> dict[str, str]:
            out = {}
            for path in sorted(self.repo.rglob("*")):
                if path.is_file():
                    out[str(path.relative_to(self.repo))] = hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest()
            return out

        before = snapshot()
        data = self._deed()
        data["commands"]["test"] = "echo changed"
        (self.repo / DEED_PATH).write_text(yamlite.dump(data), encoding="utf-8")
        self._upkeep()
        after = snapshot()

        changed = {
            name for name in set(before) | set(after)
            if before.get(name) != after.get(name)
        }
        allowed_prefixes = (
            ".agent/", "CLAUDE.md", "AGENTS.md", "GEMINI.md",
            ".cursor/", ".github/copilot-instructions.md", ".claude/",
            ".gitignore",
        )
        stray = [
            name for name in changed
            if not name.startswith(allowed_prefixes)
        ]
        self.assertEqual([], stray, f"touched files outside its remit: {stray}")


class Rule4_OldSetupsKeepWorking(HealingCase):
    def test_deed_is_migrated_to_the_current_version(self) -> None:
        self.assertEqual("0.0.1", str(self._deed()["estate_agent_version"]))
        self._upkeep()
        from estate_agent.upkeep import CURRENT_VERSION

        self.assertEqual(
            CURRENT_VERSION, str(self._deed()["estate_agent_version"])
        )

    def test_migration_preserves_everything_else(self) -> None:
        before = self._deed()
        self._upkeep()
        after = self._deed()
        self.assertEqual(before["repo"], after["repo"])
        self.assertEqual(before["never_do"], after["never_do"])
        self.assertEqual(before["commands"], after["commands"])


class DryRun(HealingCase):
    def test_dry_run_changes_nothing(self) -> None:
        data = self._deed()
        data["commands"]["test"] = "echo changed"
        (self.repo / DEED_PATH).write_text(yamlite.dump(data), encoding="utf-8")
        before = (self.repo / "CLAUDE.md").read_text(encoding="utf-8")

        self._upkeep("--dry-run")

        self.assertEqual(
            before, (self.repo / "CLAUDE.md").read_text(encoding="utf-8")
        )


class Idempotent(HealingCase):
    def test_running_twice_changes_nothing_the_second_time(self) -> None:
        self._upkeep()
        after_first = {
            str(p.relative_to(self.repo)): p.read_bytes()
            for p in sorted(self.repo.rglob("*")) if p.is_file()
        }
        self._upkeep()
        after_second = {
            str(p.relative_to(self.repo)): p.read_bytes()
            for p in sorted(self.repo.rglob("*")) if p.is_file()
        }
        self.assertEqual(after_first, after_second)


class ReInitKeepsHumanContent(HealingCase):
    """`init --force` must not be the thing that loses someone's writing.

    On a second run the live CLAUDE.md is already generated, so it is skipped
    as ours - and without reading the `.before-estate-agent` copy the salvaged
    prose vanished from the deed. On a real repo that was 11,743 bytes of
    hand-written documentation reduced to nothing, silently.
    """

    def _fresh_repo(self, body: str) -> Path:
        repo = self.workspace / "with-notes"
        (repo / "src").mkdir(parents=True, exist_ok=True)
        (repo / ".git").mkdir(exist_ok=True)
        (repo / "package.json").write_text('{"name":"with-notes"}', encoding="utf-8")
        (repo / "src" / "a.ts").write_text("export const a = 1\n", encoding="utf-8")
        (repo / "CLAUDE.md").write_text(body, encoding="utf-8")
        return repo

    def test_content_survives_a_second_init(self) -> None:
        marker = "Ask Devi before touching the reconciliation job."
        repo = self._fresh_repo(f"# With notes\n\n{marker}\n")

        cmd_init([str(repo)])
        self.assertIn(marker, (repo / "CLAUDE.md").read_text(encoding="utf-8"))

        cmd_init([str(repo), "--force"])
        self.assertIn(
            marker, (repo / "CLAUDE.md").read_text(encoding="utf-8"),
            "re-running init lost the salvaged human content",
        )

    def test_content_survives_a_third_init(self) -> None:
        marker = "The settlement module is a minefield."
        repo = self._fresh_repo(f"# Notes\n\n{marker}\n")
        for _ in range(3):
            cmd_init([str(repo), "--force"])
        self.assertIn(marker, (repo / "CLAUDE.md").read_text(encoding="utf-8"))

    def test_hand_edited_deed_notes_survive_a_rebuild(self) -> None:
        """Notes edited directly in the deed are human work too."""
        repo = self._fresh_repo("# Notes\n\nOriginal line.\n")
        cmd_init([str(repo)])

        deed_file = repo / DEED_PATH
        data = yamlite.load(deed_file.read_text(encoding="utf-8"))
        data["notes"] = (data.get("notes") or "") + "\nAdded by hand later.\n"
        deed_file.write_text(yamlite.dump(data), encoding="utf-8")

        cmd_init([str(repo), "--force"])

        self.assertIn(
            "Added by hand later",
            yamlite.load(deed_file.read_text(encoding="utf-8")).get("notes", ""),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
