#!/usr/bin/env python3
"""Estate map accuracy, measured against a fixture whose answer we know.

`tests/fixtures/estate/` is a small polyglot estate - Java, Rust, Node, .NET,
Swift, BrightScript, React - with connections chosen deliberately so that each
rung of the resolution ladder is exercised once, plus one connection that is
genuinely ambiguous.

The assertion that matters most is the negative one: **no edge that is not in
the ground truth**. Recall can be improved later; a map that invents
connections is worse than no map, because the second false alarm is the one
after which nobody reads it again.

Run:  python3 tests/test_estate_map.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from estate_agent import graph, stacks  # noqa: E402
from estate_agent.discover import find_repos, survey  # noqa: E402
from estate_agent.impact import blast_radius, landing_order  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "estate"

# (from, to, how it should be resolved). This is the whole truth: any edge the
# scanner produces that is not on this list is a false positive.
GROUND_TRUTH = {
    ("notifications-dotnet", "payments-api", "declared"),   # AddHttpClient name
    ("notifications-dotnet", "payments-api", "host"),       # BaseAddress URL
    ("payments-api", "ledger-rust", "declared"),            # gRPC stub
    ("payments-api", "ledger-rust", "dependency"),          # ledger-client dep
    ("checkout-node", "payments-api", "env"),               # PAYMENTS_API_URL
    ("web-react", "payments-api", "env"),                   # NEXT_PUBLIC_..._URL
    ("roku-app", "payments-api", "host"),                   # roUrlTransfer URL
    ("ios-app", "payments-api", "path"),                    # endpoint enum
}

EXPECTED_STACKS = {
    "payments-api": "java",
    "ledger-rust": "rust",
    "checkout-node": "node",
    "notifications-dotnet": "dotnet",
    "ios-app": "ios-swift",
    "roku-app": "roku-brightscript",
    "web-react": "react-web",
    "ambiguous-caller": "node",
}


def build_map() -> graph.EstateMap:
    repos = find_repos(FIXTURE)
    records = [survey(root, FIXTURE) for root in repos]
    return graph.build(records, str(FIXTURE))


class FixtureIsIntact(unittest.TestCase):
    def test_fixture_exists(self) -> None:
        self.assertTrue(FIXTURE.is_dir(), f"missing fixture at {FIXTURE}")

    def test_every_stack_profile_loads(self) -> None:
        loaded = stacks.all_stacks()
        self.assertEqual(
            [], stacks.LOAD_ERRORS,
            "a stack profile failed to load, so its repos would go unmapped",
        )
        for name in (
            "java", "rust", "dotnet", "node", "react-web", "ios-swift",
            "tvos", "android-kotlin", "roku-brightscript", "as400", "python",
        ):
            self.assertIn(name, loaded)


class Classification(unittest.TestCase):
    def test_each_repo_gets_the_right_stack(self) -> None:
        estate = build_map()
        found = {r.name: r.primary_stack for r in estate.repos}
        self.assertEqual(EXPECTED_STACKS, found)

    def test_client_apps_are_marked_as_clients(self) -> None:
        estate = build_map()
        kinds = {r.name: r.kind for r in estate.repos}
        for client in ("ios-app", "roku-app", "web-react"):
            self.assertEqual("client", kinds[client], f"{client} is a client app")
        self.assertEqual("backend", kinds["payments-api"])


class Endpoints(unittest.TestCase):
    def test_java_routes_are_found(self) -> None:
        estate = build_map()
        payments = estate.repo("payments-api")
        paths = {e.path for e in payments.endpoints}
        self.assertEqual({"/v2/charge", "/v2/refund/{id}", "/internal/metrics"}, paths)

    def test_rust_routes_are_found(self) -> None:
        estate = build_map()
        ledger = estate.repo("ledger-rust")
        self.assertEqual(
            {"/ledger/entry", "/internal/metrics"}, {e.path for e in ledger.endpoints}
        )

    def test_every_endpoint_cites_a_file_and_line(self) -> None:
        estate = build_map()
        for record in estate.repos:
            for endpoint in record.endpoints:
                self.assertRegex(
                    endpoint.evidence, r"^.+:\d+$",
                    f"{record.name} endpoint {endpoint.path} has no evidence",
                )


class MapAccuracy(unittest.TestCase):
    def test_finds_every_real_connection(self) -> None:
        estate = build_map()
        found = {(e.source, e.target, e.method) for e in estate.edges}
        missing = GROUND_TRUTH - found
        self.assertEqual(set(), missing, f"missed {len(missing)} real connection(s)")

    def test_invents_no_connections(self) -> None:
        """The assertion that decides whether anyone trusts the map."""
        estate = build_map()
        found = {(e.source, e.target, e.method) for e in estate.edges}
        invented = found - GROUND_TRUTH
        self.assertEqual(
            set(), invented,
            f"{len(invented)} phantom connection(s) - precision failure",
        )

    def test_ambiguous_call_is_asked_about_not_guessed(self) -> None:
        estate = build_map()
        sources = {u.source for u in estate.unresolved}
        self.assertIn(
            "ambiguous-caller", sources,
            "/internal/metrics is declared by two services and must not be resolved",
        )
        item = next(u for u in estate.unresolved if u.source == "ambiguous-caller")
        self.assertEqual(sorted(item.candidates), ["ledger-rust", "payments-api"])
        self.assertNotIn(
            "ambiguous-caller", {e.source for e in estate.edges},
            "an ambiguous signal must not become an edge",
        )

    def test_confirm_list_stays_short(self) -> None:
        """Noise in the confirm list is the other way this feature dies."""
        estate = build_map()
        self.assertLessEqual(
            len(estate.unresolved), 3,
            "too many questions - people stop answering them:\n  "
            + "\n  ".join(f"{u.source}: {u.value} ({u.reason})"
                          for u in estate.unresolved),
        )

    def test_every_edge_cites_evidence(self) -> None:
        estate = build_map()
        for edge in estate.edges:
            self.assertTrue(edge.evidence, f"{edge.key()} has no evidence")
            self.assertRegex(edge.evidence[0], r"^.+:\d+$")

    def test_no_self_connections(self) -> None:
        estate = build_map()
        for edge in estate.edges:
            self.assertNotEqual(edge.source, edge.target)


class BlastRadius(unittest.TestCase):
    def test_names_the_service_and_both_device_clients(self) -> None:
        estate = build_map()
        result = blast_radius(estate, "payments-api", "/v2/charge")
        affected = {c["repo"] for c in result["affected"]}
        for expected in (
            "checkout-node", "notifications-dotnet", "ios-app", "roku-app",
            "web-react",
        ):
            self.assertIn(expected, affected)

    def test_client_apps_are_flagged_as_clients(self) -> None:
        estate = build_map()
        result = blast_radius(estate, "payments-api", "/v2/charge")
        clients = {c["repo"] for c in result["clients"]}
        self.assertEqual({"ios-app", "roku-app", "web-react"}, clients)

    def test_landing_order_puts_clients_after_services(self) -> None:
        estate = build_map()
        result = blast_radius(estate, "payments-api", "/v2/charge")
        steps = " || ".join(landing_order(result))
        add_new = steps.index("Add the new shape")
        services = steps.index("services that call it")
        clients = steps.index("Ship the client apps")
        remove = steps.index("remove the old shape")
        self.assertLess(add_new, services)
        self.assertLess(services, clients)
        self.assertLess(
            clients, remove,
            "the old shape must not be removed before clients have shipped",
        )

    def test_expand_before_contract_when_clients_are_involved(self) -> None:
        estate = build_map()
        steps = landing_order(blast_radius(estate, "payments-api", "/v2/charge"))
        self.assertIn("Do not remove anything yet", steps[0])

    def test_transitive_reach(self) -> None:
        """Changing the ledger reaches the clients through payments-api."""
        estate = build_map()
        result = blast_radius(estate, "ledger-rust")
        affected = {c["repo"] for c in result["affected"]}
        self.assertIn("payments-api", affected)
        self.assertIn("ios-app", affected)

    def test_unknown_repo_is_an_error_not_an_empty_answer(self) -> None:
        estate = build_map()
        self.assertIn("error", blast_radius(estate, "does-not-exist"))


class Determinism(unittest.TestCase):
    def test_two_scans_agree(self) -> None:
        """Same estate, same map - no model, no randomness."""
        first = {(e.source, e.target, e.method, e.score) for e in build_map().edges}
        second = {(e.source, e.target, e.method, e.score) for e in build_map().edges}
        self.assertEqual(first, second)


def report() -> int:
    estate = build_map()
    found = {(e.source, e.target, e.method) for e in estate.edges}
    missing = GROUND_TRUTH - found
    invented = found - GROUND_TRUTH

    print("\nEstate map - measured against a known answer")
    print("=" * 58)
    print(f"  Repos classified            {len(estate.repos)}")
    print(f"  Real connections found      {len(GROUND_TRUTH) - len(missing)}"
          f"/{len(GROUND_TRUTH)}   (recall "
          f"{(len(GROUND_TRUTH) - len(missing)) / len(GROUND_TRUTH):.0%})")
    print(f"  Phantom connections         {len(invented)}"
          f"          (precision "
          f"{(len(found) - len(invented)) / max(len(found), 1):.0%})")
    print(f"  Sent for confirmation       {len(estate.unresolved)}")
    for item in missing:
        print(f"    MISSED   {item}")
    for item in invented:
        print(f"    PHANTOM  {item}")
    print()
    return 1 if (missing or invented) else 0


if __name__ == "__main__":
    if "--report" in sys.argv:
        sys.exit(report())
    unittest.main(verbosity=2)
