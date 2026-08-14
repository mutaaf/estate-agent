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

**Self-healing.** Notes go stale; this is the part that fixes them. See
[docs/self-healing.md](docs/self-healing.md).

---

## Three levels — stop wherever you like

| | **1. Context & safety** | **2. The map** | **3. Optional extras** |
|---|---|---|---|
| Installs anything? | No | No | Yes |
| Sends data anywhere? | **No** | **No** | See [data-flow](docs/data-flow.md) |
| Works for all stacks? | Yes | Yes | No |
| Time | ~15 min/repo | ~30 min once | Half a day |

Levels 1 and 2 are plain Python and shell with zero dependencies. That is
deliberate: most companies will never approve a third-party code indexer, and
this has to work at those companies too.

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

## Documentation

| If you are… | Read |
|---|---|
| an engineer who wants to start | [docs/start-here.md](docs/start-here.md) |
| deciding whether your team should | [docs/adoption.md](docs/adoption.md) |
| reviewing this for security | [docs/data-flow.md](docs/data-flow.md) |
| new to AI coding agents | [docs/plain-english.md](docs/plain-english.md) |
| wondering what a word means | [docs/glossary.md](docs/glossary.md) |

Also: [tiers](docs/tiers.md) · [the map](docs/estate.md) ·
[self-healing](docs/self-healing.md) ·
[a worked example](docs/workflows/cross-repo-change.md) ·
[adding a language](docs/adding-a-stack.md)

---

## Status

v0.1.0, first release. Built by working through a real ten-stack estate, and
dogfooded on real repos rather than only on its own fixtures.

Contributions especially wanted for **stack profiles** — adding a language is
one YAML file and no code. See [CONTRIBUTING.md](CONTRIBUTING.md) and
[docs/adding-a-stack.md](docs/adding-a-stack.md).

MIT licensed.
