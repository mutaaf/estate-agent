# In plain English

**What this is for:** understanding what Estate Agent does if you have never
used an AI coding assistant. No jargon, no prior knowledge.

---

## What an AI coding agent is

A programmer at your company opens a tool — Claude Code, Cursor, Copilot — and
types something like *"add a discount field to the checkout API"*. The tool
reads the code, writes the change, runs the tests, and opens it for review.
That tool is what everyone means by an **agent**: it acts, rather than just
answering questions.

It is genuinely useful, and it has three problems that get worse the bigger
your company is.

## Problem one: it only sees one folder

An agent sees the repository it was opened in. It cannot see the other ninety.

That matters because your systems call each other. If the agent changes how the
payments service replies, and the iPhone app was relying on the old reply, the
iPhone app breaks. The agent had no way to know the iPhone app existed. Neither,
often, does the person supervising it.

**What Estate Agent does:** it reads all your repositories once and works out
which ones call which — not by guessing, but by reading the API specifications
and the actual lines of code that make the calls. Then anyone can ask *"if I
change this, what breaks?"* and get a real list.

## Problem two: nobody told it the house rules

Every codebase has knowledge that is not in the code: which command runs the
tests, which module is fragile, who to ask before touching the billing logic.

Teams write this into a file the agent reads. But each AI tool wants its own
file with its own name, so people maintain three or four, and they slowly
disagree with each other. Then someone joins using a different tool and gets
nothing at all.

**What Estate Agent does:** you write it once, in one file. Estate Agent
produces the five different files the different tools expect, and a check that
fails if they ever fall out of step.

## Problem three: nothing stops a mistake

An agent runs real commands. Left unconstrained it can read a file full of
passwords, or run a command that cannot be undone.

**What Estate Agent does:** two things. A **secret guard** watches every action
before it happens and blocks anything touching credentials. A **permission
list** refuses the commands that cannot be taken back — force-pushes,
deployments, deleting things.

Neither is a matter of trusting the AI to behave. They stop the action at the
point of execution.

## Problem four: it all goes stale

The notes are right in month one. By month nine the build command has changed
and two systems have been renamed, and nobody updated anything. Now the agent
is confidently following instructions that are wrong — which is worse than
having no instructions, because with none it would have checked.

**What Estate Agent does:** it checks the notes against reality and repairs
what it safely can. And when an agent trips over something wrong while working,
it is instructed to fix the note as part of that same piece of work. The
documentation improves as a by-product of people doing their jobs, rather than
depending on someone remembering.

---

## What it is not

- **Not an AI itself.** It does not write code or make decisions. It is a set
  of files and a small program that reads your repositories.
- **Not a service.** Nothing is sent anywhere. No account, no subscription, no
  server. It runs on the laptop and stops there.
- **Not a replacement for review.** It makes the agent better informed and more
  constrained. A human still reads the change.

---

## What adopting it actually looks like

One engineer, one repository, about fifteen minutes: run one command to see
what is missing, a second to set it up, then read the generated file and correct
anything wrong. Repeat per repository; it gets faster.

Then one command maps everything, and the *"what breaks if I change this"*
question becomes answerable for the first time.

The whole thing is text files in your repositories. If you stop using it, you
delete them.

---

Next: [start here](start-here.md) to actually do it · [glossary](glossary.md)
for any word · [what data goes where](data-flow.md) for your security team.
