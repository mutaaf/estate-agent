# Instructions for an AI agent installing Estate Agent

**You are reading this because someone told you to set up their repo using
Estate Agent.** This file is written for you, not for a human. Follow it in
order. Do not improvise, and do not skip the verification steps.

If you are a human: you want [README.md](README.md) instead.

---

## Before anything else: three rules

1. **Never overwrite a hand-written context file.** If the repo already has a
   `CLAUDE.md`, `AGENTS.md`, `.cursorrules` or similar, its content is
   valuable and someone wrote it deliberately. `estate init` folds it into the
   deed automatically. Do not delete it yourself, and do not "tidy it up".
2. **Never guess at a build or test command.** If you cannot determine one
   from the build files, leave it blank and tell the human what you could not
   work out. A wrong test command is worse than a missing one, because the
   agent that follows will trust it.
3. **Stop and ask** rather than proceeding, whenever this file says to.

---

## Step 0 — work out which install path applies

Try them in order and use the first that works.

**Path A — the repo can be cloned.** Preferred.

```bash
git clone https://github.com/mutaaf/estate-agent ~/.estate-agent
~/.estate-agent/bin/estate version
```

If that prints a version, use `~/.estate-agent/bin/estate` as the `estate`
command for every step below, and go to Step 1.

**Path B — Claude Code with plugin support.**

```
/plugin marketplace add mutaaf/estate-agent
/plugin install estate-agent
```

**Path C — the machine cannot clone or install anything.** This is common on
locked-down work laptops. Estate Agent is plain Python with no dependencies
precisely so this works: read the files listed in *Appendix: minimum file set*
below from GitHub, write them into `~/.estate-agent/`, then `chmod +x
~/.estate-agent/bin/estate` and continue.

**Verify before continuing:** `estate version` prints `estate 0.1.0` or later.
If it does not, stop and tell the human which path you tried and what the
error was. Do not continue with a partial install.

---

## Step 1 — look before you touch

```bash
estate doctor .
```

This changes nothing. Read its output carefully; it tells you what already
exists. In particular note:

- whether the repo already has a deed (`.agent/estate.yaml`)
- which stack was detected, and whether the detection looks right to you
- which existing context files were found

**If `doctor` says the stack was not recognised**, say so to the human before
continuing. Estate Agent will still work, but the build and test commands will
need filling in by hand and you should ask for them rather than invent them.

**If a deed already exists**, this repo is already set up. Run `estate check`
instead and report the result. Do not run `init` again unless the human
explicitly asks you to rebuild it.

---

## Step 2 — set the repo up

```bash
estate init .
```

This will:

- write `.agent/estate.yaml` (the deed)
- read any existing `CLAUDE.md` and similar, keep the commands and rules it
  recognises, and preserve the rest verbatim under `notes:`
- save a copy of anything it replaces as `<file>.before-estate-agent`
- install the secret guard at `.agent/hooks/secret_guard.py`
- merge the permission profile into `.claude/settings.json`
- generate the five assistant context files

**Verify:** `.agent/estate.yaml` exists and `estate check .` exits 0.

---

## Step 3 — check the deed against reality, and fix what is wrong

This is the step that matters most, and the one only you can do. Open
`.agent/estate.yaml` and check each field against the actual repo:

| Field | How to check it |
|---|---|
| `repo.summary` | Does it describe what this service actually does? |
| `repo.stack` | Does it match the build files you can see? |
| `commands.build` | **Run it.** Does it work? |
| `commands.test` | **Run it.** Does it work? |
| `commands.lint` | **Run it.** Does it work? |
| `never_do` | Anything in the codebase that would be dangerous to change? |

**Run the build and test commands before trusting them.** If a command fails
because it is wrong, fix it in `.agent/estate.yaml` and run `estate sync`. If
it fails because a tool is not installed on this machine, leave it alone and
say so — that is the machine's problem, not the deed's.

If you cannot determine a command, leave it empty and tell the human exactly
which one you could not work out and what you tried.

---

## Step 4 — set the tier deliberately

The tier decides how much rope the next agent gets. `init` guesses from the
stack; the guess is conservative but it is still a guess, and this is a
decision with real consequences.

| Tier | Agent may | Use when |
|---|---|---|
| **1** Restricted | read and propose only, write nothing | regulated, customer-data-bearing, or effectively untestable. **AS400 and similar legacy systems belong here.** |
| **2** Reviewed | edit and open pull requests, never merge | the normal setting |
| **3** Autonomous | edit, open PRs, merge on green CI | internal tools, docs, scripts |

**Ask the human to confirm the tier.** Do not raise a tier on your own
initiative, ever. Lowering one is fine.

---

## Step 5 — map the estate (only if there are sibling repos)

If the repo sits in a directory alongside other repos:

```bash
estate scan <the directory containing all the repos>
```

This writes `ESTATE.md` and `estate/graph.json`, and adds a `related_repos`
list to each deed so a future agent knows the neighbours.

**Do not run this against a home directory or `/`.** Point it at the specific
workspace directory. If you are not sure which directory that is, ask.

Then read the *Needs confirming* section of `ESTATE.md`. Those are connections
Estate Agent could not pin to one service. **Do not guess at them.** Present
them to the human and let them answer; each answer is permanent.

---

## Step 6 — report back

Tell the human, briefly:

1. What stack was detected and whether you agree with it.
2. Which commands you ran and whether they worked.
3. What tier was set, and that they should confirm it.
4. Anything in the deed you could not fill in.
5. If you ran a scan: how many repos and connections, and how many questions
   are waiting in `ESTATE.md`.

Then stop. Do not start making code changes in the same turn as setting the
repo up.

---

## Ongoing: the correction protocol

Once a repo is set up, this applies to you in every future session there.

The generated context files can go stale, and stale instructions are worse
than none because you will act on them confidently and be wrong. So whenever
reality contradicts what the notes say — a documented command fails, a service
named in `related_repos` no longer exists, an endpoint has been renamed:

1. Fix `.agent/estate.yaml`, **not** the generated file. Edits to `CLAUDE.md`
   and its siblings are overwritten.
2. Run `estate sync`.
3. Mention the correction in your pull request description, one line, so a
   human can sanity-check it.

Do not silently work around a wrong instruction. Correcting it is part of the
task. This is the mechanism by which the notes get better over time instead of
worse.

---

## Things that will go wrong, and what to do

| Symptom | What it means | What to do |
|---|---|---|
| `estate: needs Python 3.9 or newer` | old or missing Python | tell the human; do not try to install Python |
| `estate check` exits 1 with "out of date" | the deed changed | run `estate sync` |
| `estate sync` says a file was "edited by hand" | someone customised it | **do not use `--force`.** Show the human the lines and ask where they should live in the deed |
| `no repos found` from `scan` | pointed at the wrong directory | ask which directory holds the repos |
| The secret guard blocks something | it thinks there is a credential | read the reason. If it is a genuine false positive, tell the human the finding ID and let *them* decide whether to allowlist it. Never allowlist on your own initiative |
| A stack was detected wrongly | detection is heuristic | set `repo.stack` by hand in the deed and run `estate sync` |

---

## Appendix: minimum file set for Path C

If you have to materialise Estate Agent by hand, these are the files that must
exist for `estate doctor`, `init`, `sync`, `check`, `scan`, `impact` and
`upkeep` to work:

```
bin/estate
src/estate_agent/__init__.py
src/estate_agent/__main__.py
src/estate_agent/cli.py
src/estate_agent/ui.py
src/estate_agent/yamlite.py
src/estate_agent/deed.py
src/estate_agent/render.py
src/estate_agent/stacks.py
src/estate_agent/discover.py
src/estate_agent/graph.py
src/estate_agent/scan.py
src/estate_agent/impact.py
src/estate_agent/doctor.py
src/estate_agent/initialise.py
src/estate_agent/upkeep.py
hooks/secret_guard.py
templates/settings/permissions.json
stacks/*.yaml            (at minimum, the profile matching this repo's stack)
```

There are no other dependencies. Do not attempt to `pip install` anything.
