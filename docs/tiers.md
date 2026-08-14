# Tiers: how much rope the agent gets

**What this is for:** deciding, per repo, what an AI agent is allowed to do —
and writing that decision down where the agent will actually read it.

Set it in the deed:

```yaml
repo:
  tier: 2
```

---

## The three tiers

### Tier 1 — Restricted

**The agent may** read the code, explain it, and propose changes in
conversation.
**The agent may not** write to any file, open a pull request, or run anything
that changes state.

Use it when a mistake is expensive and hard to catch: anything regulated,
anything holding customer data, and anything effectively untestable. Legacy
systems belong here by default — an AS400 repo gets tier 1 automatically,
because nobody can review an agent's RPG change quickly, the test coverage to
catch a mistake usually does not exist, and the blast radius reaches the
general ledger.

Tier 1 is not "the agent is useless here". It is still worth a great deal: it
can explain a system nobody remembers, write the code on the *other* side of
the boundary, and generate tests around it. It simply does not edit it.

### Tier 2 — Reviewed

**The agent may** edit code and open pull requests.
**The agent may not** merge — every change needs passing CI and a human
reviewer.

This is the normal setting and should be most of your estate.

### Tier 3 — Autonomous

**The agent may** edit, open pull requests, and merge when CI is green.
**The agent may not** bypass CI or modify another repo's deed.

Use it where a bad change is cheap to revert and quickly noticed: internal
tooling, documentation, scripts, test fixtures. Tier 3 only makes sense where
CI genuinely tests the thing — otherwise "green CI" means nothing and you have
autonomy without a safety net.

---

## Choosing one

Ask one question: **if the agent gets this wrong and nobody notices for a week,
what happens?**

| Answer | Tier |
|---|---|
| Someone loses money, data, or a compliance position | 1 |
| A service misbehaves and we roll it back | 2 |
| Somebody is mildly annoyed | 3 |

If you are torn between two, pick the lower one. Raising a tier later takes ten
seconds; explaining an incident does not.

---

## What actually enforces it

Be clear about this: **the tier is written into every generated context file,
so the agent reads it in every session. That is instruction, not enforcement.**

The mechanisms that genuinely enforce are:

- the **permission profile**, which blocks irreversible commands at the tool
  layer whatever the agent intends
- the **secret guard**, which blocks credential access the same way
- your **branch protection and required reviews**, which is what actually stops
  a merge

Tiers make the intent explicit and legible. They are not a sandbox, and Estate
Agent does not pretend otherwise. For a tier-1 repo where the stakes justify
it, back the tier with branch protection rather than trusting the instruction.

---

## Tiers in a monorepo

The root deed sets the default; a package with different stakes overrides it.
A repo containing both a marketing site and a payments module should not have
one tier — split the deeds. See [monorepos](monorepo.md).
