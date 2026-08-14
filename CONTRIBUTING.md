# Contributing

**The most valuable contribution is a stack profile.** Estate Agent covers
eleven stacks; there are hundreds. Adding one is a single YAML file and no
code, and it is what lets this cover estates nobody anticipated.

---

## Adding a language

Read [docs/adding-a-stack.md](docs/adding-a-stack.md), then:

1. Copy the closest existing profile from `stacks/` and edit it.
2. Add a small repo to `tests/fixtures/estate/` with a connection you know
   exists.
3. Add the expected edge to `GROUND_TRUTH` in `tests/test_estate_map.py`.
4. Run `python3 tests/run_all.py --report`.

**Precision must stay at 100%.** If your patterns invent a connection anywhere
in the fixture, the suite will say so. That is the point: a map that cries wolf
twice stops being read, including the parts that were right. A pattern that
misses a connection is a much smaller problem than one that invents one —
missed connections get added by hand and stay added.

Stacks that would be genuinely useful: Go, Rails, Laravel, Scala, Elixir,
Flutter, React Native, Unity, COBOL on z/OS, Salesforce Apex, SAP ABAP,
embedded. The mainframe and enterprise-platform ones are the most valuable and
the least likely to be covered by anything else — follow the `as400` profile's
approach for those: describe the interface rather than parse the language.

---

## Running the tests

```bash
python3 tests/run_all.py            # everything, 108 tests
python3 tests/run_all.py --report   # the measured numbers the docs quote
python3 tests/test_upkeep.py        # self-healing, by deliberately breaking things
```

No test runner to install. If a change requires adding a dependency, it is
almost certainly the wrong change — see below.

---

## The constraints

These are not style preferences. Each one is load-bearing, and a pull request
that breaks one will be asked to change even if the feature is good.

**Zero dependencies, standard library only.** This is what makes Estate Agent
installable on a locked-down work laptop, and what keeps
[docs/data-flow.md](docs/data-flow.md) short enough for a security reviewer to
verify in a minute. `tests/test_no_network.py` fails the build if a networking
import appears.

**No network calls, ever.** No telemetry, no update check, no analytics.

**Precision over recall on the map.** Every edge cites a file and line.
Anything ambiguous becomes a question, never a guess.

**Never overwrite human work.** If someone hand-edited a generated file, the
tool detects it and refuses. Destroying someone's writing once loses their
trust permanently, and they are right to withdraw it.

**Never loosen safety automatically.** Automated changes may tighten or report.
Only a human relaxes a rule.

**The commands stay literal.** The project's name is a pun; `estate scan` and
`estate init` are not. A cute CLI is a CLI people mistype.

**Docs stay under two pages** and open with one sentence saying what they are
for. Anything longer becomes an appendix.

---

## Reporting a phantom connection

If the map invents a connection, that is the most important bug you can report.
Include:

- the edge it produced (`from`, `to`, `resolved_by`)
- the evidence line it cited
- what the code at that line actually does

Those become fixture cases, so the same false positive cannot come back.

---

## Reporting a secret-guard false positive

Equally valuable, for the same reason inverted: a guard that fires on ordinary
code gets switched off, and then it protects nothing. Send the code that
tripped it — redacted if need be, as long as the *shape* survives — and it
becomes a case in `MUST_ALLOW` in `tests/test_secret_guard.py`.

---

## Pull requests

Small and focused. Explain what problem it solves, not only what it changes.
If it touches detection, say what it now finds that it did not before, and what
you checked to make sure it does not find things that are not there.

MIT licensed; contributions are accepted under the same licence.
