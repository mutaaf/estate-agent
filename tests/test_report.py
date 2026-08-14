#!/usr/bin/env python3
"""The field report, and the redaction it promises.

This exists so bugs found on a confidential estate can be reported publicly.
That only works if the redaction is airtight: a report that leaks one repo name
is worse than no report at all, because someone will have already pasted it
into an issue by the time anyone notices.

So the test is adversarial. Build a map whose names, hosts and paths are all
distinctive strings, render the report, and assert not one of them survives.

Run:  python3 tests/test_report.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from estate_agent import graph, report  # noqa: E402
from estate_agent.discover import Endpoint, RepoRecord, Signal  # noqa: E402
from estate_agent.infra import InfraNode  # noqa: E402

# Deliberately distinctive: if any of these appears in the output, the
# redaction has a hole.
SECRET_REPO = "zzconfidentialsvc"
SECRET_CALLER = "zzsecretclient"
SECRET_HOST = "zzvault-cluster.internal"
SECRET_DIR = "zzprivatedir"
SECRET_ROUTE = "/api/zzsecretroute/detail"


def sample_map() -> graph.EstateMap:
    provider = RepoRecord(
        name=SECRET_REPO, path=SECRET_REPO, primary_stack="java",
        kind="backend", call_sites=3,
    )
    provider.endpoints = [
        Endpoint("POST", SECRET_ROUTE, f"{SECRET_DIR}/Controller.java:41")
    ]
    provider.notes = [f"something odd about {SECRET_HOST}"]

    caller = RepoRecord(
        name=SECRET_CALLER, path=SECRET_CALLER, primary_stack="react-web",
        kind="client", call_sites=9,
    )
    caller.signals = [
        Signal("path", SECRET_ROUTE, "rest",
               f"{SECRET_DIR}/page.tsx:78", "fetch-call")
    ]

    edge = graph.Edge(
        SECRET_CALLER, SECRET_REPO, "rest", "path", 0.60,
        [f"{SECRET_DIR}/page.tsx:78"], paths=[SECRET_ROUTE],
    )
    unresolved = graph.Unresolved(
        SECRET_CALLER, "path", SECRET_ROUTE, "rest",
        f"{SECRET_DIR}/page.tsx:80",
        f"2 services declare this path - {SECRET_REPO} or something else",
        [SECRET_REPO],
    )
    external = graph.External(
        SECRET_CALLER, "https://api.stripe.com", "rest",
        f"{SECRET_DIR}/pay.ts:12", "url",
    )
    node = InfraNode(
        SECRET_HOST, SECRET_HOST, "cache", "redis",
        [SECRET_REPO, SECRET_CALLER],
        [f"{SECRET_REPO}:{SECRET_DIR}/application.yml:6"],
    )
    return graph.EstateMap(
        [provider, caller], [edge], [unresolved], "/home/someone/work",
        [external], [node],
    )


class Redaction(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = report.build(sample_map(), 12.3, redact=True)

    def test_no_repo_name_survives(self) -> None:
        self.assertNotIn(SECRET_REPO, self.text)
        self.assertNotIn(SECRET_CALLER, self.text)

    def test_no_hostname_survives(self) -> None:
        self.assertNotIn(SECRET_HOST, self.text)
        self.assertNotIn("zzvault-cluster", self.text)

    def test_no_directory_name_survives(self) -> None:
        self.assertNotIn(SECRET_DIR, self.text)

    def test_no_route_path_survives(self) -> None:
        self.assertNotIn("zzsecretroute", self.text)

    def test_workspace_path_is_not_leaked(self) -> None:
        self.assertNotIn("/home/someone", self.text)

    def test_pseudonyms_are_used_instead(self) -> None:
        self.assertIn("repo-01", self.text)
        self.assertIn("repo-02", self.text)
        self.assertIn("host-a", self.text)

    def test_pseudonyms_are_stable_across_runs(self) -> None:
        """Two reports from the same machine must be comparable."""
        again = report.build(sample_map(), 12.3, redact=True)
        self.assertEqual(self.text, again)

    def test_evidence_keeps_the_filename_and_line(self) -> None:
        """The bit that makes a pattern bug diagnosable must survive."""
        self.assertIn("page.tsx:78", self.text)
        self.assertIn("…/", self.text)

    def test_path_shape_is_preserved_without_the_words(self) -> None:
        """Depth matters for diagnosing path resolution; the words do not."""
        self.assertRegex(self.text, r"`/a/b/c`")


class Usefulness(unittest.TestCase):
    """A redacted report that says nothing is not worth sending."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = report.build(sample_map(), 12.3, redact=True)

    def test_reports_the_environment(self) -> None:
        self.assertIn("Estate Agent", self.text)
        self.assertIn("Python", self.text)
        self.assertIn("12.3s", self.text)

    def test_reports_coverage_per_stack(self) -> None:
        self.assertIn("java", self.text)
        self.assertIn("react-web", self.text)
        self.assertIn("Call sites", self.text)

    def test_reports_how_edges_were_resolved(self) -> None:
        self.assertIn("Resolved by", self.text)
        self.assertIn("path", self.text)
        self.assertIn("0.60", self.text)

    def test_flags_a_long_confirm_list(self) -> None:
        estate = sample_map()
        estate.unresolved = [estate.unresolved[0]] * 12
        text = report.build(estate, 1.0)
        self.assertIn("too many", text)

    def test_flags_a_slow_scan(self) -> None:
        self.assertIn("", report.build(sample_map(), 90.0))
        self.assertIn("slow", report.build(sample_map(), 90.0))

    def test_flags_silent_repos(self) -> None:
        estate = sample_map()
        for record in estate.repos:
            record.endpoints = []
            record.signals = []
            record.call_sites = 0
        self.assertIn("yielded nothing", report.build(estate, 1.0))

    def test_says_precision_is_what_to_judge(self) -> None:
        self.assertIn("phantom connection", self.text)


class Unredacted(unittest.TestCase):
    def test_opt_out_keeps_names_and_warns_loudly(self) -> None:
        text = report.build(sample_map(), 1.0, redact=False)
        self.assertIn(SECRET_REPO, text)
        self.assertIn("UNREDACTED", text)
        self.assertIn("Do not", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
