# Estate Agent

**The standard for AI agents working across your repo estate.**

Your repos are the estate. The AI is the agent. Estate Agent is what tells it
where everything is, what it is allowed to touch, and what breaks if it
changes something.

```
$ estate scan ~/work
  34 repos · 10 stacks · 118 connections, each with evidence

$ estate impact payments-api /v2/charge
  Directly affected:
    checkout-node          (node)
    notifications-dotnet   (dotnet)
    ios-app                (CLIENT APP - ships on its own release cycle)
    roku-app               (CLIENT APP - ships on its own release cycle)
    web-react              (CLIENT APP - ships on its own release cycle)

  Ship in this order:
    1. Add the new shape to `payments-api` alongside the old one.
    2. Update and deploy: `checkout-node`, `notifications-dotnet`.
    3. Ship the client apps: `ios-app`, `roku-app`, `web-react`.
    4. Only then remove the old shape. Months, not days.
```

No installation. No dependencies. No account. **Nothing leaves your machine.**

---

## The problem

AI coding agents are good inside one well-described repo and bad across an
estate. Four reasons, and they compound:

1. **Every repo explains itself differently, or not at all.** Hand-written
   `CLAUDE.md` files, drifting apart, useless to a colleague on Cursor.
2. **No agent can see across repos.** An agent in the Java API has no idea the
   Rust service and three phone apps depend on the endpoint it is changing.
3. **Nothing stops the bad outcome.** No mechanism prevents a credential
   entering context or a force-push going through. "Be careful" is not a
   control.
4. **Whatever you write goes stale.** Right in month one, quietly wrong by
   month nine — at which point the agent is confidently wrong, fast.

Estate Agent is four small tools against those four problems, and it works the
same whether the repo is Java, Rust, .NET, Node, Swift, Kotlin, React, Roku,
or a 30-year-old AS400.

---

## Quickstart (15 minutes)

```bash
git clone https://github.com/mutaaf/estate-agent ~/.estate-agent
export PATH="$HOME/.estate-agent/bin:$PATH"

cd ~/work/payments-api
estate doctor        # what is here and what is missing. Changes nothing.
estate init          # set it up. Folds in your existing CLAUDE.md.
estate scan ~/work   # map the whole estate
```

Or, if you use Claude Code, just point it at this repo:

> read github.com/mutaaf/estate-agent and set this repo up

That works because [`AGENT.md`](AGENT.md) is written for an agent to follow,
not for a human to skim.

---

## What you get

**One file per repo, five assistants supported.** You maintain
`.agent/estate.yaml` — the deed. Estate Agent generates `CLAUDE.md`,
`AGENTS.md`, `.cursor/rules/`, `.github/copilot-instructions.md` and
`GEMINI.md` from it. Change one; all five update. CI fails on drift.

**A map of your estate, with evidence.** `estate scan` reads contracts
(OpenAPI, protobuf, GraphQL), client dependencies, configured URLs and call
sites across every stack, and writes `ESTATE.md` plus a queryable graph. Every
connection cites the file and line that proves it. Anything ambiguous becomes
a question rather than a guess.

**Guardrails that block.** A secret guard that stops credentials reaching the
agent, and a permission profile that denies force-pushes, deploys and secret
reads. Measured, not asserted: **32/32 real credentials blocked, 0 false
positives on 44 pieces of ordinary code** (`python3 tests/run_all.py --report`).

**Shared infrastructure.** Which services share a cache, a database or a
queue — identified by the actual host or cluster, so a local Postgres in one
repo's compose file never masquerades as a shared production database.

**A vault, if you want one.** `estate vault` writes the whole map as
wikilinked markdown with YAML frontmatter, plus scaffolded trees for the things
only a person can write. Open it in Obsidian, read it on GitHub, `rg` it, or
point an agent at it.

**Self-healing.** Notes go stale; this is the part that fixes them. See
[docs/self-healing.md](docs/self-healing.md).

---

## The five levels

Adoption is a ladder, not a switch. Each level is worth having on its own, and
you can stop at any of them.

| | | What it gets you | Cost |
|---|---|---|---|
| **0** | Nothing | The agent guesses, confidently, and you cannot tell when it is wrong | — |
| **1** | The repo explains itself | One file per repo → context for all five assistants | ~15 min/repo |
| **2** | Mistakes are blocked | Credentials and irreversible commands stopped at execution | included |
| **3** | The estate is mapped | *"What breaks if I change this endpoint?"* — answered, with evidence | ~30 min once |
| **4** | It stays true on its own | CI drift check, self-repair, and a home for human knowledge | one CI line |

**Not sure where you are?** The site has an [interactive version with a
four-question self-check](https://mutaaf.github.io/estate-agent/#levels) that
tells you your level and the single next step. The full description of each
level, in plain language, is in [docs/levels.md](docs/levels.md).

Levels 1–3 need nothing installed — plain Python and shell, zero dependencies.
That is deliberate: most companies will never approve a third-party code
indexer, and this has to work at those companies too.

> **Levels are not tiers.** A **level** is how far you have adopted. A **tier**
> is how much a single repo lets an agent do — read-only, pull requests, or
> merge on green CI. See [docs/tiers.md](docs/tiers.md).

---

## Why it does not just use a code-graph tool

Because none of them cover a real estate. The best available option parses
Java, Rust, .NET, Node and Kotlin — but not Swift, not BrightScript, not RPG,
and it does not link separate repos or read API specs at all. That is half of
a typical estate and none of the cross-service connections.

So Estate Agent does something different, and better:

> **Instead of trying to read ten languages, read the contracts between them.**

API specs, generated client libraries, configured service URLs, and a handful
of per-language call patterns. This works identically for Rust and for RPG,
because it never has to understand either one.

---

## What this is not

Estate Agent generates the **structural** layer — what exists, what calls what,
what shares which cluster. It does not produce the knowledge that matters most,
and does not pretend to:

| It generates | Only a person can write |
|---|---|
| What services exist and their stacks | Why this design was chosen |
| Which service calls which, with evidence | What broke last time, and how it was found |
| Which services share a cache or database | How to reproduce a specific bug |
| Where the notes have gone stale | Which cross-cutting concerns actually matter |

So it is a **component**, not a strategy. If you already have a documentation
or knowledge-graph initiative, `estate vault` emits linked markdown with
scaffolded human trees (`Investigations/`, `Decisions/`, `Runbooks/`) designed
to sit alongside it —
see [using this inside an initiative you already have](docs/interop.md).

It also will not: replace review or ownership; know why anything is the way it
is; or achieve perfect recall — it is weakest on stacks with no parser, and it
says where it is less confident rather than letting you assume even coverage.

---

## Documentation

| If you are… | Read |
|---|---|
| an engineer who wants to start | [docs/start-here.md](docs/start-here.md) |
| deciding whether your team should | [docs/adoption.md](docs/adoption.md) |
| reviewing this for security | [docs/data-flow.md](docs/data-flow.md) |
| new to AI coding agents | [docs/plain-english.md](docs/plain-english.md) |
| wondering what a word means | [docs/glossary.md](docs/glossary.md) |
| already running a docs initiative | [docs/interop.md](docs/interop.md) |
| trying it on real repos and hitting bugs | [docs/field-testing.md](docs/field-testing.md) |
| wanting to extend it | [CONTRIBUTING.md](CONTRIBUTING.md) |

Also: [the five levels](docs/levels.md) · [tiers](docs/tiers.md) · [the map](docs/estate.md) ·
[self-healing](docs/self-healing.md) ·
[a worked example](docs/workflows/cross-repo-change.md) ·
[adding a language](docs/adding-a-stack.md) ·
[field-testing](docs/field-testing.md)

---

## Found a problem?

```bash
estate report ~/work --out report.md
```

Redacted by default — repo names, hosts and paths are pseudonymised, so it is
safe to attach to a public issue. `--include-names` opts out and stamps the
report **UNREDACTED** so nobody forwards it by accident. See
[field-testing](docs/field-testing.md).

---

v0.1.0, first release. Built by working through a real ten-stack estate, and
dogfooded on real repos rather than only on its own fixtures.

## Contributing, including from a locked-down machine

The most valuable contribution is a **stack profile** for a language this does
not cover. Adding one is a single YAML file and no code.

```bash
estate contribute stack ~/work/that-repo --name elixir   # scaffold, redacted
estate contribute check elixir.yaml ~/work/that-repo     # validate and try it
```

The scaffold strips repo names, hostnames, URL paths and usernames, never
samples documentation, and honours a git-ignored `.publish-denylist` — so it is
safe to produce on a work machine. If you cannot push from there, paste it into
an issue; a stack profile is one file.

See [CONTRIBUTING.md](CONTRIBUTING.md) for all three routes and
[docs/adding-a-stack.md](docs/adding-a-stack.md) for the format.

---

## Status

MIT licensed.
