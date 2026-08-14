#!/usr/bin/env python3
"""Contributing from a machine you do not control.

The scaffold is generated from real code on a work laptop and then sent
somewhere public. That makes its redaction a safety feature, not a
convenience: one sibling service name in a sample line is a leak that cannot
be taken back.

So the test plants identifying strings everywhere a real repo would have them
— hostnames, sibling project names, usernames, absolute paths, prose — and
asserts none reach the output.

Run:  python3 tests/test_contribute.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from estate_agent import contribute  # noqa: E402

COMPANY = "zzacmecorp"
SIBLING = "zzbilling-gateway"
HOSTNAME = "zzpayments.internal"
USER = "zzemployee"


def build_repo(root: Path) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "lib").mkdir(parents=True, exist_ok=True)
    (root / "mix.exs").write_text("defmodule App.MixProject do\nend\n", encoding="utf-8")

    (root / "src" / "client.ex").write_text(
        f'''defmodule Client do
  @base "https://{HOSTNAME}/api/v2"
  def charge(body) do
    HTTPoison.post("https://{HOSTNAME}/api/v2/charge", body)
  end
  def sibling do
    HTTPoison.get("https://{COMPANY}.example.com/{SIBLING}/status")
  end
end
''', encoding="utf-8")

    (root / "lib" / "router.ex").write_text(
        f'''defmodule Router do
  # deployed from /Users/{USER}/work/{COMPANY}
  get "/api/health"
  post "/api/charge"
end
''', encoding="utf-8")

    # Prose, which is where sibling names really live.
    (root / "README.md").write_text(
        f"# {COMPANY} payments\n\nTalks to [{SIBLING}](https://git.example.com/"
        f"{COMPANY}/{SIBLING}) and runs on {HOSTNAME}.\n",
        encoding="utf-8",
    )


class ScaffoldRedaction(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = Path(cls.tmp.name) / "zzsecret-service"
        build_repo(cls.repo)
        survey = contribute.survey_repo(cls.repo)
        cls.survey = survey
        cls.text = contribute.scaffold("elixir", survey)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_no_company_name(self) -> None:
        self.assertNotIn(COMPANY, self.text)

    def test_no_sibling_service_name(self) -> None:
        self.assertNotIn(SIBLING, self.text)

    def test_no_internal_hostname(self) -> None:
        self.assertNotIn(HOSTNAME, self.text)
        self.assertNotIn("zzpayments", self.text)

    def test_no_username_or_absolute_path(self) -> None:
        self.assertNotIn(USER, self.text)
        self.assertNotIn(f"/Users/{USER}", self.text)

    def test_no_repo_name(self) -> None:
        self.assertNotIn("zzsecret-service", self.text)

    def test_prose_is_never_sampled(self) -> None:
        """Documentation names siblings in sentences no redactor can clean."""
        for label, examples in self.survey["samples"].items():
            for example in examples:
                with self.subTest(label=label):
                    self.assertNotIn("Talks to", example)

    def test_samples_are_single_lines(self) -> None:
        for examples in self.survey["samples"].values():
            for example in examples:
                self.assertNotIn("\n", example)


class ScaffoldUsefulness(unittest.TestCase):
    """A perfectly redacted scaffold that says nothing is not worth having."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = Path(cls.tmp.name) / "zzsecret-service"
        build_repo(cls.repo)
        cls.survey = contribute.survey_repo(cls.repo)
        cls.text = contribute.scaffold("elixir", cls.survey)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_finds_the_marker_file(self) -> None:
        self.assertIn("mix.exs", self.survey["markers"])
        self.assertIn("mix.exs", self.text)

    def test_finds_the_dominant_extension(self) -> None:
        self.assertIn(".ex", [e for e, _ in self.survey["extensions"]])
        self.assertIn("- .ex", self.text)

    def test_keeps_the_shape_of_calls(self) -> None:
        """The whole point: enough to write a regex from."""
        blob = "\n".join(
            line for examples in self.survey["samples"].values()
            for line in examples
        )
        self.assertIn("HTTPoison", blob)
        self.assertIn("<host>", blob)

    def test_is_valid_yaml_for_the_loader(self) -> None:
        from estate_agent import yamlite

        data = yamlite.load(self.text)
        self.assertEqual("elixir", data["stack"])
        self.assertIn("detect", data)

    def test_prompts_for_what_only_a_human_knows(self) -> None:
        self.assertIn("TODO", self.text)
        self.assertIn("tier_default", self.text)
        self.assertIn("precision", self.text.lower())

    def test_warns_when_the_repo_already_matches_a_stack(self) -> None:
        """Otherwise the new profile silently competes with an existing one."""
        tmp = tempfile.TemporaryDirectory()
        repo = Path(tmp.name) / "node-thing"
        (repo / "src").mkdir(parents=True)
        (repo / "package.json").write_text('{"name":"x"}', encoding="utf-8")
        for i in range(4):
            (repo / "src" / f"f{i}.ts").write_text("export const a = 1\n", encoding="utf-8")
        survey = contribute.survey_repo(repo)
        text = contribute.scaffold("my-node", survey)
        self.assertIn("node", survey["known"])
        self.assertIn("requires_marker", text)
        tmp.cleanup()


class Denylist(unittest.TestCase):
    def test_local_terms_are_stripped(self) -> None:
        line = f"call('https://x/{SIBLING}') # for {COMPANY}"
        cleaned = contribute.redact(line, "", [COMPANY, SIBLING])
        self.assertNotIn(COMPANY, cleaned)
        self.assertNotIn(SIBLING, cleaned)
        self.assertIn("<redacted>", cleaned)


if __name__ == "__main__":
    unittest.main(verbosity=2)
