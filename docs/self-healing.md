# Self-healing: why these notes do not rot

**What this is for:** explaining the mechanism that keeps context files true
after month one — and the four rules that stop self-repair becoming
self-damage.

Every documentation effort dies the same way. It is accurate the week it is
written. Six months later a build command has changed, a service has been
renamed, two repos have been added and one deleted, and nothing complains. The
agent then acts on stale instructions **confidently**, which is worse than
having no instructions at all: with no instructions it explores and finds out;
with wrong ones it proceeds directly to the wrong answer.

So repair is a feature here, not a chore assigned to a person who will not do
it.

---

## Three loops

### Loop A — check the notes still match reality

Runs on `estate doctor` and `estate upkeep`. It asks the boring, checkable
questions:

- Does the documented build command exist on this machine?
- Does the test command exist?
- Do the repos in `related_repos` still exist?
- Do the generated files still match the deed?
- Does the evidence behind each map connection still exist on disk?

Safe fixes are applied. Judgement calls are reported. Notably, a **broken
command is reported, never rewritten** — choosing the replacement requires
knowing what you meant, and silently rewriting someone's build command is worse
than telling them it is broken.

### Loop B — learn from being wrong

The valuable one, and it runs during ordinary work rather than during
maintenance.

Every generated context file ends with a section addressed to the agent: if
reality contradicts these notes, fix `.agent/estate.yaml`, run `estate sync`,
and mention the correction in the pull request. Do not silently work around a
wrong instruction — correcting it is part of the task.

The effect is that **documentation improves as a side effect of normal work**.
Every time an agent trips over a stale fact, that fact gets fixed by the person
who tripped over it, in the same change, while they still have the context. Nine
months in the notes are better than the day they were written, not worse.

### Loop C — notice when the guardrails are annoying people

The real failure mode of a safety tool is not being wrong. It is being
irritating enough that somebody switches it off — and a disabled guard protects
nothing at all.

So the secret guard counts, in a local file, how often it fires and how often
someone overrides it. When one rule accounts for most of the friction,
`estate doctor` says so:

```
warn  'environment file' is overridden 7 of 9 times
      this rule is probably too broad. Narrow it in
      .agent/secret-guard-allow.txt rather than turning the guard off -
      Estate Agent will not relax it for you.
```

Counters live in `.agent/.local/friction.jsonl`, which is git-ignored. Nothing
is transmitted anywhere; see [what data goes where](data-flow.md).

---

## The four rules

Automated repair that can damage things is worse than no automated repair. Four
rules, each enforced by a test that deliberately breaks something and checks the
outcome (`tests/test_upkeep.py`).

### 1. Never overwrite human work

If someone hand-edited a generated file, Estate Agent detects it — the stamp at
the top of each file records the hash of what it generated — and leaves the file
completely alone. It then shows you exactly which lines are yours:

```
warn  CLAUDE.md was edited by hand
      This file has not been touched. The lines below are yours:
        ## Local note
        Ask Priya before touching reconciliation.
      Move them into .agent/estate.yaml (`notes:` or `conventions:`),
      then run `estate sync`.
```

The other four files still heal normally around the protected one. Destroying
someone's writing once loses their trust in the tool permanently, and they are
right to withdraw it.

### 2. Never loosen a safety rule automatically

Loop C may *suggest* that a rule is too broad. Only a human applies the change.
Nothing in Estate Agent adds an allowlist entry, widens a permission, or
disables a guard on its own. Automated changes only ever tighten or report.

Otherwise the guardrails erode by themselves, quietly, in the direction of
whatever generates least friction — which is exactly the direction you do not
want them to drift.

### 3. Only touch its own files

`upkeep` writes to `.agent/`, the five generated context files,
`.claude/settings.json`, `.gitignore`, and the estate map. Never to source
code. A test snapshots every file in the repo and fails if anything outside
that list changes.

### 4. Old setups keep working

Each deed records the version that wrote it. Upgrading runs migrations, so a
repo set up today still works after Estate Agent changes. The migration
machinery shipped in the very first release — with no migrations in it —
because retro-fitting it onto files already sitting in a hundred repos is the
kind of thing that never actually gets done.

---

## Running it

```bash
estate upkeep             # repair what is safe, report the rest
estate upkeep --dry-run   # show what it would do, change nothing
```

It is idempotent: running it twice changes nothing the second time. Every
change it makes is an ordinary diff you review and commit.
