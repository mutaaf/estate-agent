#!/usr/bin/env python3
"""The vault: linked markdown for humans and agents alike.

Two properties matter most here, and both are about trust rather than
formatting:

  * **Human work is never overwritten.** Generated notes are regenerated
    wholesale; anything a person wrote is left alone.
  * **Regeneration produces a reviewable diff.** If every note changed on
    every run - because each carries a timestamp - nobody reads the pull
    request, and the automation becomes noise.

Run:  python3 tests/test_vault.py
"""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from estate_agent import graph, vault  # noqa: E402
from estate_agent.discover import find_repos, survey  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "estate"


def build_map() -> graph.EstateMap:
    repos = find_repos(FIXTURE)
    return graph.build([survey(r, FIXTURE) for r in repos], str(FIXTURE))


class VaultCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.estate = build_map()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "vault"
        vault.write(cls.estate, cls.out, "2026-01-01 00:00")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def read(self, relative: str) -> str:
        return (self.out / relative).read_text(encoding="utf-8")


class Structure(VaultCase):
    def test_one_note_per_service(self) -> None:
        for record in self.estate.repos:
            with self.subTest(repo=record.name):
                self.assertTrue(
                    (self.out / "Generated" / "Services" / f"{record.name}.md").is_file()
                )

    def test_shared_infrastructure_gets_a_note(self) -> None:
        note = self.read(
            "Generated/Infrastructure/shared-cache-prod.internal.md"
        )
        self.assertIn("shared: true", note)
        self.assertIn("[[ledger-rust]]", note)
        self.assertIn("[[payments-api]]", note)
        self.assertIn("Shared by 2 services", note)

    def test_human_trees_are_scaffolded(self) -> None:
        for tree in ("Investigations", "Decisions", "Runbooks", "Concepts"):
            with self.subTest(tree=tree):
                self.assertTrue((self.out / tree / "README.md").is_file())

    def test_endpoint_notes_only_for_endpoints_with_consumers(self) -> None:
        """Otherwise the vault fills with notes nothing links to."""
        notes = list((self.out / "Generated" / "Endpoints").glob("*.md"))
        self.assertTrue(notes)
        for note in notes:
            with self.subTest(note=note.name):
                self.assertIn("## Consumers", note.read_text(encoding="utf-8"))

    def test_concepts_come_from_the_curated_file(self) -> None:
        caching = self.read("Concepts/Caching.md")
        self.assertIn("[[payments-api]]", caching)
        self.assertIn("[[ledger-rust]]", caching)


class Content(VaultCase):
    def test_every_generated_note_warns_against_editing(self) -> None:
        for note in (self.out / "Generated").rglob("*.md"):
            with self.subTest(note=note.name):
                self.assertIn("Generated file", note.read_text(encoding="utf-8"))

    def test_notes_carry_yaml_frontmatter(self) -> None:
        for note in (self.out / "Generated").rglob("*.md"):
            with self.subTest(note=note.name):
                text = note.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\n"))
                self.assertIn("type:", text.split("---")[1])

    def test_service_notes_link_both_directions(self) -> None:
        payments = self.read("Generated/Services/payments-api.md")
        self.assertIn("## Calls", payments)
        self.assertIn("[[ledger-rust]]", payments)
        self.assertIn("## Called by", payments)
        self.assertIn("[[ios-app]]", payments)

    def test_client_notes_say_they_cannot_be_rolled_forward(self) -> None:
        for client in ("ios-app", "roku-app", "web-react"):
            with self.subTest(client=client):
                note = self.read(f"Generated/Services/{client}.md")
                self.assertIn("role: client", note)
                self.assertIn("own release cycle", note)

    def test_shared_infrastructure_is_called_out_on_the_service(self) -> None:
        note = self.read("Generated/Services/payments-api.md")
        self.assertIn("**shared with** [[ledger-rust]]", note)

    def test_local_infrastructure_is_not_claimed_as_shared(self) -> None:
        note = self.read("Generated/Services/checkout-node.md")
        self.assertNotIn("shared with", note)

    def test_evidence_is_carried_into_the_vault(self) -> None:
        note = self.read("Generated/Services/payments-api.md")
        self.assertRegex(note, r"`[\w/.]+\.(java|ts|tsx|cs|rs|brs|swift):\d+`")

    def test_every_wikilink_resolves_to_a_note(self) -> None:
        """A dead wikilink is the vault equivalent of a 404."""
        names = {p.stem for p in self.out.rglob("*.md")}
        broken: list[str] = []
        for note in self.out.rglob("*.md"):
            for target in re.findall(r"\[\[([^\]]+)\]\]", note.read_text(encoding="utf-8")):
                if target.split("#")[0].split("|")[0].strip() not in names:
                    broken.append(f"{note.name} -> {target}")
        self.assertEqual([], broken, f"dead wikilinks: {broken[:10]}")


class RegenerationIsReviewable(VaultCase):
    def test_regenerating_unchanged_estate_changes_nothing(self) -> None:
        """The property that decides whether anyone reads the pull request.

        A `last generated` timestamp in every note would rewrite every file on
        every run, so a regeneration diff would show the whole vault and tell
        you nothing about what actually changed.
        """
        before = {
            str(p.relative_to(self.out)): p.read_text(encoding="utf-8")
            for p in sorted((self.out / "Generated").rglob("*.md"))
        }
        vault.write(self.estate, self.out, "2099-12-31 23:59")
        after = {
            str(p.relative_to(self.out)): p.read_text(encoding="utf-8")
            for p in sorted((self.out / "Generated").rglob("*.md"))
        }
        changed = [k for k in before if before[k] != after.get(k)]
        self.assertEqual(
            [], changed,
            "a later generation time must not rewrite unchanged notes",
        )

    def test_generation_time_is_recorded_once(self) -> None:
        self.assertIn("2026-01-01", self.read("README.md"))

    def test_a_removed_service_does_not_linger(self) -> None:
        stale = self.out / "Generated" / "Services" / "deleted-service.md"
        stale.write_text("---\ntype: service\n---\n# gone\n", encoding="utf-8")
        vault.write(self.estate, self.out, "2026-01-01 00:00")
        self.assertFalse(
            stale.exists(),
            "the generated tree is rebuilt wholesale, so a deleted service "
            "must not survive as a note nobody notices",
        )


class NeverOverwritesHumanWork(VaultCase):
    def test_human_notes_survive_regeneration(self) -> None:
        note = self.out / "Investigations" / "cache-timeout.md"
        note.parent.mkdir(parents=True, exist_ok=True)
        original = (
            "# Cache timeout, March\n\n"
            "Root cause was eviction under load on [[shared-cache-prod.internal]].\n"
        )
        note.write_text(original, encoding="utf-8")

        vault.write(self.estate, self.out, "2026-02-02 00:00")

        self.assertEqual(original, note.read_text(encoding="utf-8"))

    def test_edited_concept_notes_are_preserved(self) -> None:
        note = self.out / "Concepts" / "Caching.md"
        edited = note.read_text(encoding="utf-8") + "\n## Why Redis\n\nHistory.\n"
        note.write_text(edited, encoding="utf-8")

        vault.write(self.estate, self.out, "2026-03-03 00:00")

        self.assertEqual(edited, note.read_text(encoding="utf-8"))

    def test_scaffold_readmes_are_not_rewritten(self) -> None:
        readme = self.out / "Runbooks" / "README.md"
        readme.write_text("# Runbooks\n\nOur own words.\n", encoding="utf-8")
        vault.write(self.estate, self.out, "2026-04-04 00:00")
        self.assertEqual("# Runbooks\n\nOur own words.\n",
                         readme.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
