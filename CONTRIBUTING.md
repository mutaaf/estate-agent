# Contributing

**The most valuable contribution is a stack profile.** Estate Agent covers
thirteen stacks; there are hundreds. Adding one is a single YAML file and no
code — that is the extension model, and it is what lets this cover estates
nobody anticipated.

The people who can write one are, by definition, looking at a codebase in that
language. That codebase is usually at work, behind a policy that makes
contributing awkward and a confidentiality obligation that makes it risky. This
page is written for that situation.

---

## Contributing from a machine you do not control

### The tooling does the risky part

```bash
estate contribute stack ~/work/that-repo --name elixir
```

Scaffolds a profile from real code: the marker files it found, the extensions
that dominate, and a sample of the lines that look like outbound calls — which
is the raw material for writing the patterns.

**It is redacted before it reaches disk.** Repo names, hostnames, URL paths,
usernames and absolute paths are replaced. Documentation is never sampled at
all, because prose names sibling services in sentences no pattern can reliably
clean. Anything in a local `.publish-denylist` is stripped too:

```
# .publish-denylist — git-ignored, never leaves your machine
acmecorp
billing-gateway
```

Then fill in the TODOs and check it:

```bash
estate contribute check elixir.yaml ~/work/that-repo
```

That validates the file, compiles every regex, and runs the profile against a
real repo so you can see what it finds before anyone else does.

**Read the file before you send it.** Redaction is applied, but you know your
codebase and the linter does not. That is thirty seconds and it is the only
step that cannot be automated.

### Three ways to send it

**1. Pull request.** The normal path, if your machine can push to GitHub.

**2. Issue with the file pasted in.** If you cannot push but can reach
github.com, open an issue and paste the YAML. There is a template. This works
fine — a stack profile is one file, and a maintainer can commit it for you.

**3. No GitHub access at all.** Email the file to yourself, move it to a
machine that does have access, and use path 1 or 2 from there. The file is
plain text with nothing identifying in it; that is the whole point of the
redaction. If your policy forbids even that, describe the stack in an issue —
which marker files, which extensions, which library makes the HTTP calls — and
someone can write the profile from that.

You do not need to sign anything. Contributions are accepted under MIT, same
as the project.

---

## Adding a language

Read [docs/adding-a-stack.md](docs/adding-a-stack.md), then:

1. `estate contribute stack <repo>` to scaffold it.
2. Fill in commands, conventions, and the route and call patterns.
3. Add a small repo to `tests/fixtures/estate/` with a connection you know
   exists — invented, not copied from work.
4. Add the expected edge to `GROUND_TRUTH` in `tests/test_estate_map.py`.
5. `python3 tests/run_all.py --report`

**Precision must stay at 100%.** If your patterns invent a connection anywhere
in the fixture, the suite says so. That is the point: a map that cries wolf
twice stops being read, including the parts that were right. A pattern that
misses a connection is a much smaller problem — missed connections get added by
hand and stay added.

Stacks that would be genuinely useful: Go, Rails, Laravel, Scala, Elixir,
Flutter, React Native, Unity, COBOL on z/OS, Salesforce Apex, SAP ABAP,
embedded. The mainframe and enterprise-platform ones are the most valuable and
the least likely to be covered by anything else — follow the `as400` profile:
describe the interface rather than parse the language, and default the tier to
restricted.

---

## Reporting a bug found on a real estate

```bash
estate report ~/work --out report.md
```

Redacted by default: every repo becomes `repo-01`, every host `host-a`, every
path its basename and line. What survives is what makes a bug diagnosable —
coverage per stack, which resolution methods fired, what truncated, which repos
matched a stack but yielded nothing.

Ranked by how much they matter:

| Finding | Why |
|---|---|
| **A phantom connection** | The worst outcome. Two false alarms and nobody reads the map again. |
| **A silent stack** | The profile is not matching real code, so those repos are invisible. |
| **A confirm list nobody would answer** | The map stays permanently partial. |
| **A slow scan** | People stop running it, so it goes stale. |
| **A secret-guard false positive** | Equally valuable inverted: a noisy guard gets switched off, and then it protects nothing. Send the shape of the code that tripped it. |
| **A missed connection** | Real, but least severe: add it to the deed by hand and it stays added. |

A useful report says which connections you checked and how many were real.
"It found 40 connections" is not a finding; "I checked six, five were real, the
sixth pointed at a repo that merely shares a route name" is.

See [docs/field-testing.md](docs/field-testing.md) for the full loop, including
the bugs already found this way.

---

## Running the tests

```bash
python3 tests/run_all.py            # everything, seconds, nothing to install
python3 tests/run_all.py --report   # the measured numbers the docs quote
python3 tests/test_upkeep.py        # self-healing, by deliberately breaking things
```

No test runner to install. If a change requires adding a dependency, it is
almost certainly the wrong change.

---

## The constraints, and why each one exists

These are not style preferences. A pull request that breaks one will be asked
to change even if the feature is good. Most were learned the hard way.

**Zero dependencies, standard library only.** This is what makes Estate Agent
installable on a locked-down work laptop, and what keeps
[docs/data-flow.md](docs/data-flow.md) short enough for a security reviewer to
verify in a minute. Enforced by `tests/test_no_network.py`.

**No network code, ever.** No telemetry, no update check, no analytics.

**Python 3.9 is the floor**, because that is what is already on the machine you
cannot install things on. An f-string that reused its outer quote passed
locally and failed only on 3.9 — `tests/test_python_compat.py` now catches that
class.

**Precision over recall on the map.** Every edge cites a file and line.
Anything ambiguous becomes a question, never a guess.

**Never overwrite human work.** Generated files carry a content hash so a hand
edit is distinguishable from a stale file. Running `init` twice once destroyed
11,743 bytes of someone's documentation; there are three regression tests for
that now.

**Never loosen safety automatically.** Automated changes tighten or report.
Only a person relaxes a rule.

**Never truncate or skip silently.** A cap that hides what it dropped produces
confident wrong answers. One repo hit a 200-match limit, lost its own routes,
and its calls to them resolved to an unrelated project.

**The commands stay literal.** The project's name is a pun; `estate scan` is
not.

**Docs stay under two pages** and open with one sentence saying what they are
for.

---

## If you are an AI agent contributing here

This repo describes itself. Read `CLAUDE.md` (or `AGENTS.md` — same content,
generated from `.agent/estate.yaml`) before changing anything: it carries the
tier, the never-do list, the architecture, and how to make a change well.

If something in it turns out to be wrong, fix `.agent/estate.yaml` and run
`estate sync` as part of the same change. Do not edit the generated files
directly; they are overwritten.

---

## Pull requests

Small and focused. Explain what problem it solves, not only what it changes. If
it touches detection, say what it now finds that it did not before, **and what
you checked to make sure it does not find things that are not there.**
