# Should your team do this?

**What this is for:** deciding whether Estate Agent is worth adopting, with the
costs stated honestly and a clear description of what failure looks like.

---

## What it costs

| | Time |
|---|---|
| Install | 2 minutes, once, per person |
| Set up one repo | 10–15 minutes, mostly checking the generated deed |
| Map the estate | 30 minutes, once |
| Ongoing | a `estate check` line in CI; occasional `estate upkeep` |

No licence, no server, no account, no dependencies to get approved. That last
point is usually the difference between adopting this quarter and adopting
never.

## What it buys

- **"What breaks if I change this"** becomes answerable in seconds, across
  every language, including the mobile and TV clients everybody forgets.
- **One context file per repo instead of five**, so nobody hand-maintains
  drift, and a colleague on a different AI tool gets the same guidance.
- **Credentials and irreversible commands blocked** at the point of execution,
  not by policy.
- **A page you can hand a security reviewer** that says precisely what goes
  where.
- **Notes that improve rather than rot**, because correcting them is part of
  the work rather than a chore.

---

Adoption is a ladder of five levels, and this page is the "should we" case
for climbing it. The levels themselves — what each one gets you, what it costs,
and what is still wrong once you are there — are in
[the five levels](levels.md), which also has a four-question self-check.

## Adopt it in this order

**1. One person, one repo, one afternoon.** Pick a repo you know well, ideally
one that already has a hand-written `CLAUDE.md` — the interesting question is
whether the generated deed is better than what you had. Live with it for a week.

**2. Your repos.** Repeat, then run `estate scan` and read `ESTATE.md`. The map
is where you find out whether it is telling you anything you did not know. It
usually is, and it is usually a client app.

**3. Your team.** Add `estate check` to CI. Send
[data-flow.md](data-flow.md) to whoever owns security *before* anyone asks, not
after.

**4. Wider.** Only once you can point at something concrete that it caught.

Resist doing all of this in one week. The point of the staging is that each
step produces evidence for the next.

---

## Judge it on these

Before rolling it beyond your own repos, check honestly:

| Question | A good answer |
|---|---|
| Did the map find connections people did not know about? | at least one, and it should surprise someone |
| Is the *Needs confirming* list short enough that you actually answered it? | under ~10 for a real estate |
| Did the map invent anything? | **zero.** One phantom connection and nobody trusts it again |
| Did anyone turn the secret guard off? | no. If yes, find out which rule and narrow it |
| Are agent changes needing less rework? | noticeably, or the context is not good enough yet |
| Did anyone lose work they had written? | **no.** This one is not negotiable |

---

## What failure looks like

Worth writing down in advance, so it is recognisable rather than rationalised.

**The confirm list is ignored.** If nobody answers the questions, the map stays
partial and the impact reports stay incomplete. This is a real risk and the
usual cause is the list being too long. Answer them in one sitting when you
first scan; after that they trickle.

**The permission profile gets disabled.** If it interrupts ordinary work
constantly, someone will turn it off, and then there is no profile at all.
Narrow the offending rule instead — `estate doctor` names it for you.

**Deeds go stale anyway.** Self-healing catches the mechanical drift, but not
"this summary no longer describes what the service does". That still needs a
human occasionally. If the deeds are wrong six months in, the discipline did
not stick and you should know that rather than trusting them.

**It solves a problem you do not have.** If you have four repos that barely
talk to each other, the map will find nothing and you have gained only the
context generation and the guardrails. That is still worth the fifteen minutes,
but it is not worth a rollout plan. Be honest about which situation you are in.

---

## Objections worth taking seriously

**"We already have CLAUDE.md files and they work."** Then adopt level 1 only,
and `init` will fold them in rather than replace them. The value is one file
instead of five, plus a CI check that stops the drift you have not noticed yet.

**"Our security team will never approve a new tool."** It has no dependencies,
no network code, and no account. `docs/data-flow.md` is written to be forwarded
unedited, and the no-network claim is enforced by a test in the project's own
CI rather than asserted in a README.

**"We are not letting agents write to our repos at all."** Then set every repo
to tier 1. The map and the guardrails are still worth having, and the day you
change your mind the groundwork is done.

**"This is a lot of process."** It is one YAML file per repo and two commands.
If it feels like more than that in practice, that is a bug — say so.
