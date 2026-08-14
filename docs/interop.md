# Using this inside a documentation initiative you already have

**What this is for:** you, or someone on your team, has already proposed a
knowledge graph, a service catalogue, or a docs-generation project. This page
explains what Estate Agent covers, what it deliberately does not, and how to
use it as a component rather than as a competing proposal.

---

## Estate Agent is one layer, not a strategy

It generates the structural layer: what exists, what calls what, what shares
which cluster, and what breaks if you change something. That is the part a
machine can read out of your repos, and the part that is dull and mechanical
enough to be worth automating.

**It does not produce the knowledge that matters most**, and it should not
pretend to:

| Estate Agent generates | Only a person can write |
|---|---|
| What services exist, and their stacks | Why this design was chosen |
| Which service calls which, with evidence | What broke last time, and how it was found |
| Which services share a cache or database | How to reproduce a specific bug |
| What endpoints exist and who consumes them | Which cross-cutting concerns actually matter |
| Where the notes have gone stale | What "good" looks like for this team |

Any initiative that only does the left column will not survive contact with an
incident. Any initiative that only does the right column will go stale, because
nothing tells it when the code moved. **You need both, and they need to be kept
apart** — which is the next section.

---

## The rule that keeps automation and judgement from fighting

Generated and human-authored content must live in different places, with a
hard boundary.

`estate vault` implements this directly:

```
Generated/       overwritten wholesale on every run, do-not-edit header
  Services/
  Infrastructure/
  Endpoints/
Concepts/        curated by hand — what actually matters across services
Investigations/  what we learned chasing a problem
Decisions/       why we chose this, and what we rejected
Runbooks/        how to reproduce, debug, operate
```

Human notes link *into* the generated ones, so a service note surfaces the
relevant investigation through backlinks without anyone having to remember it
exists. The generator never touches the human trees.

Two implementation details worth stealing whether or not you use this tool:

**Do not put a timestamp in every generated note.** A `last generated` field
means every regeneration rewrites every file, so each run produces a
whole-vault diff and the pull request becomes unreviewable — at which point
nobody reviews it, and the automation is unsupervised. Put the generation time
in one index note. Then a diff shows only what actually changed.

**Consider detecting hand-edits rather than only forbidding them.** Segregating
trees is the right primary defence, but people will still edit a generated file
occasionally, and wholesale overwrite destroys that work silently. Estate Agent
stamps each generated file with a hash of its own content, which makes
"someone edited this" distinguishable from "the source changed" — so it can
refuse to overwrite and offer to promote the edit instead. It is about thirty
lines and it buys a lot of trust.

---

## The risk most proposals in this space are missing

Risk tables for documentation-generation projects usually cover: notes become
noise, notes rot, merge conflicts, secrets leaking, yet-another-place-to-look.
All real. But the one that actually kills the project is usually absent:

> **A generator that emits a confident wrong edge is worse than one that emits
> nothing.** The second false alarm is the point at which people stop reading
> the graph — including the parts that were right.

This is not hypothetical. Running Estate Agent against real repositories, in
order:

- The first scan produced **181 "unresolved" items**, almost all of them calls
  to third-party APIs. Nobody can adjudicate `ANTHROPIC_API_KEY`, so the list
  went unread. Fix: third-party references are classified as *external* and
  listed separately from things a human can actually answer.
- A catch-all route (`/{full_path:path}`) made one repo appear to own **every
  path in the estate**, producing a clean false dependency. Fix: routes with no
  literal segments are never used to identify a service.
- A repo's own artifact ID looked like a dependency **on itself**.
- A repo symlinked into the workspace was **silently skipped**, so it was
  missing from the map with no error.

Every one of those was invisible by reasoning and obvious within a minute of
running it on real code. If you are building something similar, run it against
your real repos before you demo it, and design the ranking before you design
the output.

What survived as the working design:

1. **Every edge cites `file:line`.** No evidence, no edge.
2. **Every edge records *how* it was resolved**, ranked: `declared` (the source
   names the service) > `dependency` (a generated client is a dependency) >
   `env` (a configured variable names it) > `host` > `path`. The rank is shown,
   so a reader can weigh it.
3. **Ambiguity becomes a question, not a guess.** If a call could plausibly
   mean two services, it resolves to neither and goes to a confirm list.
   Answering one is permanent.
4. **The confirm list must stay short**, or it goes unanswered and the map
   stays partial. This is a design constraint, not a nice-to-have.

---

## Mapping onto a maturity framework

Most organisations doing this seriously end up with a scorecard of levels. The
[five levels](levels.md) are shaped to slot into one:

| Estate Agent level | Typical framework equivalent |
|---|---|
| 1 — the repo explains itself | per-repo agent context exists and is current |
| 2 — mistakes are blocked | guardrails enforced mechanically |
| 3 — the estate is mapped | cross-service dependency linking, resolvable references |
| 4 — it stays true on its own | active drift-check in CI |

Two things worth knowing when you plan the sequence:

**Level 1 is the input to level 3.** A cross-repo generator reads each repo's
README, `AGENTS.md` and docs to describe it. If only a handful of repos have
any of those, the generator has thin material for the rest and the resulting
service notes are stubs. Generating per-repo context first makes the estate map
substantially better, and it is the cheaper of the two.

**Level 3 is where the network effect is.** Each repo added makes every other
repo's map more useful, which is the opposite of level 1, where each repo
benefits only itself. That asymmetry is worth stating explicitly when arguing
for scope.

---

## Using it as a component

Estate Agent is MIT licensed, has zero dependencies, contains no network code,
and stores nothing outside the repos you point it at. Reasonable ways to use
it inside an existing initiative:

- **Take the generator, keep your own output format.** `estate/graph.json` is
  the whole map — repos, edges with evidence and rank, infrastructure, external
  dependencies, unresolved questions. Render it however your project wants.
- **Take the vault as-is.** `estate vault` produces wikilinked markdown with
  YAML frontmatter and scaffolded human trees.
- **Take only the stack profiles.** `stacks/*.yaml` is a language-by-language
  catalogue of how each ecosystem declares endpoints and makes outbound calls.
  That research is most of the work, and it is reusable independently of any
  code here.
- **Take only the ideas.** The evidence ranking, the confirm list, the
  external/unresolved split, the hand-edit stamp, the no-timestamp rule. They
  are all documented here precisely so they can be copied.

Adding a language is [one YAML file and no code](adding-a-stack.md). If your
estate includes something not covered — a proxy layer, a mainframe, an
in-house framework — that is the cheapest possible contribution, and it makes
the tool better for whoever comes next.

---

## What it will not do for you

Stated plainly, so nobody discovers it at the wrong moment:

- It does not write your investigations, decisions or runbooks.
- It does not know why anything is the way it is.
- It does not replace review, ownership, or the person who has been there
  longest — it reduces how often you have to interrupt them.
- Its recall is not perfect, and is weakest on stacks with no parser. It says
  where it is less confident rather than letting you assume even coverage.
- It is a snapshot unless you keep it running. That is what level 4 is for.
