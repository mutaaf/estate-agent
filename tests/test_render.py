#!/usr/bin/env python3
"""Tests for rendering and drift detection.

The property that matters most here is the one in the plan: a hand-edited
file must be *distinguishable* from a stale one, because syncing over a stale
file is correct and syncing over a hand-edited file destroys someone's work.

Run:  python3 tests/test_render.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from estate_agent import deed as deed_mod, render, yamlite  # noqa: E402

SAMPLE = """
estate_agent_version: 0.1.0
repo:
  name: payments-api
  summary: Handles card payments for the checkout flow.
  stack: java
  tier: 1
  owners:
    - payments-team
commands:
  build: ./gradlew build
  test: ./gradlew test
  lint: ./gradlew spotlessCheck
conventions:
  - Constructor injection, never field injection
never_do:
  - Modify anything under src/generated
architecture: |
  Spring Boot service behind the API gateway.
  Writes to Postgres, publishes to Kafka.
provides:
  contracts:
    - openapi/payments.yaml
  endpoints:
    - method: POST
      path: /v2/charge
      note: idempotent by Idempotency-Key
consumes:
  - service: ledger-rust
    via: grpc
    evidence: src/main/java/LedgerClient.java:42
related_repos:
  - checkout-node
"""


def sample_deed() -> deed_mod.Deed:
    parsed, problems = deed_mod.parse(yamlite.load(SAMPLE))
    assert not [p for p in problems if p.fatal], [str(p) for p in problems]
    return parsed


class DeedParsing(unittest.TestCase):
    def test_reads_every_section(self) -> None:
        d = sample_deed()
        self.assertEqual("payments-api", d.name)
        self.assertEqual("java", d.stack)
        self.assertEqual(1, d.tier)
        self.assertEqual("./gradlew test", d.commands["test"])
        self.assertEqual(["payments-team"], d.owners)
        self.assertEqual(["openapi/payments.yaml"], d.contracts)
        self.assertEqual("/v2/charge", d.endpoints[0]["path"])
        self.assertEqual("ledger-rust", d.consumes[0]["service"])
        self.assertIn("Spring Boot", d.architecture)

    def test_missing_test_command_warns_but_is_not_fatal(self) -> None:
        _d, problems = deed_mod.parse(yamlite.load(
            "repo:\n  name: x\n  stack: node\ncommands:\n  build: npm run build\n"
        ))
        warnings = [p for p in problems if not p.fatal]
        self.assertTrue(any("test" in p.field for p in warnings))
        self.assertEqual([], [p for p in problems if p.fatal])

    def test_bad_tier_is_reported_and_defaulted(self) -> None:
        d, problems = deed_mod.parse(yamlite.load(
            "repo:\n  name: x\n  stack: node\n  tier: 9\n"
        ))
        self.assertEqual(2, d.tier)
        self.assertTrue(any(p.field == "repo.tier" for p in problems))

    def test_round_trips_through_yaml(self) -> None:
        original = sample_deed()
        reparsed, problems = deed_mod.parse(yamlite.load(original.to_yaml()))
        self.assertEqual([], [p for p in problems if p.fatal])
        self.assertEqual(original.to_dict(), reparsed.to_dict())


class Rendering(unittest.TestCase):
    def test_generates_all_five_clients(self) -> None:
        files = {r.path for r in render.render_all(sample_deed())}
        self.assertEqual(
            {
                "CLAUDE.md",
                "AGENTS.md",
                "GEMINI.md",
                ".github/copilot-instructions.md",
                ".cursor/rules/00-estate.mdc",
            },
            files,
        )

    def test_every_file_carries_the_same_facts(self) -> None:
        """One source of truth means the five files must agree."""
        for rendered in render.render_all(sample_deed()):
            with self.subTest(path=rendered.path):
                self.assertIn("payments-api", rendered.text)
                self.assertIn("./gradlew test", rendered.text)
                self.assertIn("Modify anything under src/generated", rendered.text)
                self.assertIn("ledger-rust", rendered.text)
                self.assertIn("DO NOT EDIT", rendered.text)

    def test_tier_one_says_what_is_forbidden(self) -> None:
        text = render.render_claude(sample_deed()).text
        self.assertIn("Tier 1", text)
        self.assertIn("Restricted", text)
        self.assertIn("may not", text)

    def test_correction_protocol_is_present(self) -> None:
        """Loop B only works if the instruction reaches the agent."""
        text = render.render_claude(sample_deed()).text
        self.assertIn("If this file turns out to be wrong", text)
        self.assertIn("estate sync", text)
        self.assertIn("not this file", text)

    def test_cursor_file_has_frontmatter(self) -> None:
        text = render.render_cursor(sample_deed()).text
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("alwaysApply: true", text)

    def test_render_is_deterministic(self) -> None:
        """Otherwise `check` reports drift that is not there."""
        first = render.render_claude(sample_deed()).text
        second = render.render_claude(sample_deed()).text
        self.assertEqual(first, second)

    def test_empty_deed_still_renders_something_useful(self) -> None:
        d, _ = deed_mod.parse(yamlite.load("repo:\n  name: bare\n  stack: node\n"))
        text = render.render_claude(d).text
        self.assertIn("bare", text)
        self.assertIn("No commands recorded yet", text)


class DriftDetection(unittest.TestCase):
    """The core safety property of `estate check`."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.deed = sample_deed()
        self.rendered = render.render_claude(self.deed)
        target = self.root / self.rendered.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.rendered.text, encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_freshly_written_file_matches(self) -> None:
        result = render.check_file(self.root, self.rendered)
        self.assertEqual(render.MATCHES, result.state)
        self.assertFalse(result.needs_sync)
        self.assertFalse(result.needs_a_human)

    def test_missing_file_is_missing(self) -> None:
        (self.root / self.rendered.path).unlink()
        result = render.check_file(self.root, self.rendered)
        self.assertEqual(render.MISSING, result.state)
        self.assertTrue(result.needs_sync)

    def test_changed_deed_makes_the_file_stale_not_hand_edited(self) -> None:
        self.deed.commands["test"] = "./gradlew test --info"
        fresh = render.render_claude(self.deed)
        result = render.check_file(self.root, fresh)
        self.assertEqual(render.STALE, result.state)
        self.assertTrue(result.needs_sync)
        self.assertFalse(
            result.needs_a_human,
            "a stale file is safe to regenerate without asking anyone",
        )

    def test_hand_edited_file_is_detected_and_protected(self) -> None:
        path = self.root / self.rendered.path
        path.write_text(
            self.rendered.text + "\n## Local note\n\nAsk Priya before touching "
            "the reconciliation job.\n",
            encoding="utf-8",
        )
        result = render.check_file(self.root, self.rendered)
        self.assertEqual(render.HAND_EDITED, result.state)
        self.assertTrue(result.needs_a_human)
        self.assertFalse(
            result.needs_sync,
            "sync must not silently overwrite a hand-edited file",
        )

    def test_hand_edit_detected_even_when_deed_also_changed(self) -> None:
        """The dangerous case: both moved. Protecting the human wins."""
        path = self.root / self.rendered.path
        path.write_text(self.rendered.text + "\nlocal addition\n", encoding="utf-8")
        self.deed.commands["test"] = "./gradlew test --info"
        fresh = render.render_claude(self.deed)
        result = render.check_file(self.root, fresh)
        self.assertEqual(render.HAND_EDITED, result.state)
        self.assertTrue(result.needs_a_human)

    def test_pre_existing_file_is_unmanaged_not_clobbered(self) -> None:
        path = self.root / self.rendered.path
        path.write_text(
            "# CLAUDE.md\n\nRun `make test`. Ask the payments team first.\n",
            encoding="utf-8",
        )
        result = render.check_file(self.root, self.rendered)
        self.assertEqual(render.UNMANAGED, result.state)
        self.assertTrue(result.needs_a_human)
        self.assertIn("fold its content into the deed", result.detail)

    def test_cursor_frontmatter_does_not_look_like_drift(self) -> None:
        rendered = render.render_cursor(self.deed)
        target = self.root / rendered.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered.text, encoding="utf-8")
        self.assertEqual(
            render.MATCHES, render.check_file(self.root, rendered).state
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
