# The five levels

**What this is for:** working out how far you have got, and what the next step
is. No prior knowledge assumed.

Adoption is a ladder, not a switch. Each level is worth having on its own, and
you can stop at any of them. There is an [interactive version with a
"where am I?" check](https://mutaaf.github.io/estate-agent/#levels) if you
prefer to click.

> **Levels are not tiers.** A **level** is how far *you* have adopted. A
> **tier** is how much a single *repo* lets an agent do — read-only, pull
> requests, or merge on green CI. They are numbered separately on purpose.
> See [tiers](tiers.md).

---

## Level 0 — Nothing

*The agent is guessing.*

No file tells the AI how this repo works, so it infers everything from the code
it can see. It will often be right, confidently, and occasionally wrong in the
same tone of voice. Nobody can tell the difference from the outside.

**What is still wrong here**

- It runs the wrong test command, or none
- It cannot see any other repo, so cross-service changes break things
- Nothing stops it reading a credentials file
- Every new person and every new agent starts from zero

**Who is here:** most repos, at most companies, today. There is no shame in it
— it is the default.

---

## Level 1 — The repo explains itself

*One file, every assistant.*

You write down how this repo works once — the build command, the test command,
what it does, what not to touch. Estate Agent turns that one file into the five
different files that Claude Code, Cursor, Copilot, Gemini and everything else
expect. Change it once and all five update.

**What you get**

- A single source of truth per repo (the deed)
- Context files for five assistants, generated rather than hand-written
- Any existing `CLAUDE.md` content folded in, never discarded
- A tier saying what agents may do here

**What is still wrong here**

- The agent still cannot see any other repo
- Nothing yet stops a dangerous command

**Cost:** about 15 minutes per repo. Nothing to install.
**How:** `estate init`
**You are here when:** `estate check` exits 0, and every assistant reads the
same facts.

---

## Level 2 — Mistakes are blocked

*Not by policy — at the moment they happen.*

A guard inspects every action the agent is about to take and stops the ones
that touch credentials. A permission list refuses the commands you cannot take
back: force-pushes, deploys, deleting things. Neither depends on the AI
behaving well; they stop the action at the point of execution.

**What you get**

- A secret guard: 32/32 real credentials blocked, 0 false alarms on 44 pieces
  of ordinary code
- A reviewed permission profile with 105 deny rules
- A page you can hand your security team ([data-flow](data-flow.md))
- A record of which rules cause friction, so noisy ones get tuned instead of
  switched off

**What is still wrong here**

- The agent still cannot see across repos
- Your notes will start drifting from reality

**Cost:** included in setup. Nothing to install, nothing sent anywhere.
**How:** `estate init` installs the guardrails at the same time as the context.
**You are here when:** `estate doctor` shows the guard installed and wired up.

---

## Level 3 — The estate is mapped

*You can finally ask what breaks.*

Estate Agent reads every repo and works out which services call which — from
API specifications, client libraries and configured URLs rather than by parsing
ten languages. Then you can ask the question nobody could answer before: if I
change this endpoint, what breaks? The answer includes the phone and TV apps
everyone forgets, and the order you would have to ship in.

**What you get**

- A readable register of every service and who calls it
- Blast radius on demand, with the file and line proving each link
- Shared infrastructure: which services share a cache or a database
- Anything ambiguous asked as a question, never guessed

**What is still wrong here**

- It is a snapshot; it goes stale unless you keep it running
- The map knows structure, not why anything was decided

**Cost:** about 30 minutes, once, for the whole estate.
**How:** `estate scan ~/work`, then `estate impact <repo> <endpoint>`
**You are here when:** the map finds a dependency somebody on the team did not
know about. It usually does, and it is usually a client app.

---

## Level 4 — It stays true on its own

*The part everyone skips, and the reason the rest lasts.*

Everything above is accurate the week you write it. This level is what stops it
being quietly wrong nine months later. CI fails if the generated files drift. A
repair command finds stale commands and deleted services. And when an agent
trips over something wrong while working, it is instructed to fix the source as
part of the same change — so the documentation improves as a by-product of
normal work rather than waiting for someone to remember.

**What you get**

- A CI check that fails on drift
- Self-repair that never overwrites something a human wrote
- A vault of linked notes for Obsidian, GitHub or an AI agent
- Somewhere for the knowledge code cannot hold: investigations, decisions,
  runbooks

**What is still wrong here**

- A human still has to write down *why* decisions were made. No tool can infer
  that, and anything claiming otherwise is guessing.

**Cost:** one CI line, plus the habit of writing things down.
**How:** `estate check --quiet` in CI · `estate upkeep` · `estate vault`
**You are here when:** nine months in, the notes are better than the day they
were written.

---

## Where are you?

Four questions, in order. Stop at the first "no" — that is your level, and the
next level is your next step.

| # | Question | If yes |
|---|---|---|
| 1 | Does each repo have a file telling an AI how to build and test it? | Level 1 |
| 2 | Is there something that would *stop* an agent reading a credentials file? | Level 2 |
| 3 | Can you answer "what breaks if I change this endpoint?" in under a minute? | Level 3 |
| 4 | Would you notice if those answers went out of date? | Level 4 |

Question 2 means a mechanism, not a policy or a code review. Question 3 means
without asking the person who has been here longest. Question 4 means something
that fails, not someone remembering to check.

---

## If you are mapping this onto an internal maturity framework

Most organisations that take this seriously end up with a scorecard of their
own. The levels here are deliberately shaped to slot into one rather than
compete with it:

- Levels 1–2 are per-repo and can be assessed by looking at a repo.
- Level 3 is per-estate and is the one with the network effect — every repo
  added makes the next one more valuable.
- Level 4 is the drift-check dimension that most frameworks put at the top and
  most teams never reach.

Estate Agent implements the structural parts. It does not implement the human
parts — decisions, investigations, runbooks — and does not pretend to. See
[using this inside an existing documentation initiative](interop.md).
