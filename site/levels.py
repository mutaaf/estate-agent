"""The adoption ladder, defined once.

Five levels, in plain language, describing how far a team has got rather than
how much of the tool they use. Someone who has never touched an AI coding
agent should be able to read any one of these and know whether it describes
them.

This is the single definition. `site/build.py` renders the interactive
explorer from it, `docs/levels.md` is the prose companion, and a test asserts
the two agree — so the page and the documentation cannot drift apart.

**Levels are not tiers.** A level is how far *you* have adopted. A tier is how
much a *repo* lets an agent do. They are numbered separately on purpose and
the glossary says so; conflating them is the most likely way for this
vocabulary to go wrong.
"""

from __future__ import annotations

LEVELS = [
    {
        "number": 0,
        "name": "Nothing",
        "tagline": "The agent is guessing.",
        "plain": (
            "No file tells the AI how this repo works, so it infers everything "
            "from the code it can see. It will often be right, confidently, "
            "and occasionally wrong in the same tone of voice. Nobody can tell "
            "the difference from the outside."
        ),
        "you_get": [],
        "still_wrong": [
            "It runs the wrong test command, or none",
            "It cannot see any other repo, so cross-service changes break things",
            "Nothing stops it reading a credentials file",
            "Every new person and every new agent starts from zero",
        ],
        "cost": "—",
        "command": "",
        "check": "Is there a .agent/estate.yaml in this repo? No.",
        "who": "Most repos, most companies, today.",
    },
    {
        "number": 1,
        "name": "The repo explains itself",
        "tagline": "One file, every assistant.",
        "plain": (
            "You write down how this repo works once — the build command, the "
            "test command, what it does, what not to touch. Estate Agent turns "
            "that one file into the five different files that Claude Code, "
            "Cursor, Copilot, Gemini and everything else expect. Change it "
            "once and all five update."
        ),
        "you_get": [
            "A single source of truth per repo (the deed)",
            "Context files for five assistants, generated not hand-written",
            "Existing CLAUDE.md content folded in, never discarded",
            "A tier saying what agents may do here",
        ],
        "still_wrong": [
            "The agent still cannot see any other repo",
            "Nothing yet stops a dangerous command",
        ],
        "cost": "About 15 minutes per repo. Nothing to install.",
        "command": "estate init",
        "check": "estate check exits 0, and every assistant reads the same facts.",
        "who": "Anyone. This is the floor, and it is worth having on its own.",
    },
    {
        "number": 2,
        "name": "Mistakes are blocked",
        "tagline": "Not by policy — at the moment they happen.",
        "plain": (
            "A guard inspects every action the agent is about to take and "
            "stops the ones that touch credentials. A permission list refuses "
            "the commands you cannot take back: force-pushes, deploys, "
            "deleting things. Neither depends on the AI behaving well; they "
            "stop the action at the point of execution."
        ),
        "you_get": [
            "A secret guard: 32/32 real credentials blocked, 0 false alarms "
            "on 44 pieces of ordinary code",
            "A reviewed permission profile with 105 deny rules",
            "A page you can hand your security team",
            "A record of which rules cause friction, so noisy ones get tuned "
            "instead of switched off",
        ],
        "still_wrong": [
            "The agent still cannot see across repos",
            "Your notes will start drifting from reality",
        ],
        "cost": "Included in setup. Nothing to install, nothing sent anywhere.",
        "command": "estate init  (installs the guardrails too)",
        "check": "estate doctor shows the guard installed and wired up.",
        "who": "Anyone letting an agent run commands. Which is everyone.",
    },
    {
        "number": 3,
        "name": "The estate is mapped",
        "tagline": "You can finally ask what breaks.",
        "plain": (
            "Estate Agent reads every repo and works out which services call "
            "which — from API specifications, client libraries and configured "
            "URLs rather than by parsing ten languages. Then you can ask the "
            "question nobody could answer before: if I change this endpoint, "
            "what breaks? The answer includes the phone and TV apps everyone "
            "forgets, and the order you would have to ship in."
        ),
        "you_get": [
            "A readable register of every service and who calls it",
            "Blast radius on demand, with the file and line proving each link",
            "Shared infrastructure: which services share a cache or database",
            "Anything ambiguous asked as a question, never guessed",
        ],
        "still_wrong": [
            "It is a snapshot; it goes stale unless you keep it running",
            "The map knows structure, not why anything was decided",
        ],
        "cost": "About 30 minutes, once, for the whole estate.",
        "command": "estate scan ~/work  →  estate impact <repo> <endpoint>",
        "check": "The map finds a dependency somebody on the team did not know about.",
        "who": "Any team with more than a handful of services that talk to each other.",
    },
    {
        "number": 4,
        "name": "It stays true on its own",
        "tagline": "The part everyone skips, and the reason the rest lasts.",
        "plain": (
            "Everything above is accurate the week you write it. This level is "
            "what stops it being quietly wrong nine months later. CI fails if "
            "the generated files drift. A repair command finds stale commands "
            "and deleted services. And when an agent trips over something "
            "wrong while working, it is instructed to fix the source as part "
            "of the same change — so the documentation improves as a "
            "by-product of normal work rather than waiting for someone to "
            "remember."
        ),
        "you_get": [
            "A CI check that fails on drift",
            "Self-repair that never overwrites something a human wrote",
            "A vault of linked notes for Obsidian, GitHub or an AI agent",
            "Somewhere for the knowledge code cannot hold: investigations, "
            "decisions, runbooks",
        ],
        "still_wrong": [
            "A human still has to write down why decisions were made — no "
            "tool can infer that",
        ],
        "cost": "One CI line, plus the habit of writing things down.",
        "command": "estate check --quiet  in CI  ·  estate upkeep  ·  estate vault",
        "check": "Nine months in, the notes are better than the day they were written.",
        "who": "Anyone who intends to still be doing this next year.",
    },
]

# The self-check. Four yes/no questions; the answers determine the level, and
# the level determines the single next thing to do.
QUESTIONS = [
    {
        "id": "context",
        "ask": "Does each repo have a file telling an AI how to build and test it?",
        "hint": "A CLAUDE.md, AGENTS.md or similar that is actually current.",
        "level": 1,
    },
    {
        "id": "guardrails",
        "ask": "Is there something that would stop an agent reading a credentials file?",
        "hint": "A mechanism, not a policy or a code review.",
        "level": 2,
    },
    {
        "id": "map",
        "ask": "Can you answer \"what breaks if I change this endpoint?\" in under a minute?",
        "hint": "Without asking the person who has been here longest.",
        "level": 3,
    },
    {
        "id": "fresh",
        "ask": "Would you notice if those answers went out of date?",
        "hint": "Something that fails, rather than someone remembering to check.",
        "level": 4,
    },
]

NEXT_STEP = {
    0: ("Start with one repo.",
        "Run <code>estate doctor</code> to see what is there, then "
        "<code>estate init</code>. Fifteen minutes, nothing installed, and it "
        "folds in any context file you already wrote."),
    1: ("Turn the guardrails on.",
        "You already have the context. <code>estate init</code> installs the "
        "secret guard and the permission profile at the same time — if you "
        "set the repo up by hand, run it again."),
    2: ("Map the estate.",
        "Run <code>estate scan</code> against the directory holding your "
        "repos. This is the step that usually surprises someone: there is "
        "almost always a consumer nobody remembered."),
    3: ("Stop it going stale.",
        "Add <code>estate check --quiet</code> to CI, and run "
        "<code>estate vault</code> to give the human knowledge — "
        "investigations, decisions, runbooks — somewhere to live that links "
        "to the services it concerns."),
    4: ("You are at the top of the ladder.",
        "The remaining work is not tooling: it is writing down why decisions "
        "were made, which nothing can infer for you. Consider contributing a "
        "stack profile for a language Estate Agent does not cover yet."),
}
