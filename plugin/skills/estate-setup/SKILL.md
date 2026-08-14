---
name: estate-setup
description: Set this repository up for AI agents using Estate Agent - detect the stack, write the deed, install the guardrails, and generate the context files for every assistant. Use when a repo has no .agent/estate.yaml, when the user asks to "set up this repo for agents", or when existing CLAUDE.md files need consolidating.
---

# Set this repo up with Estate Agent

Follow `AGENT.md` in the Estate Agent repository, which is written for you to
execute step by step. The short version:

1. `estate doctor .` — changes nothing. Read what already exists.
2. `estate init .` — writes `.agent/estate.yaml`, folds in any hand-written
   `CLAUDE.md`, installs the secret guard and permission profile, generates the
   five assistant files.
3. Open `.agent/estate.yaml` and check it against reality. **Run the build and
   test commands.** If one is wrong, fix the deed and run `estate sync`.
4. Confirm the tier with the human. Never raise a tier on your own initiative.

## Rules

- **Never overwrite a hand-written context file.** `init` folds it in and keeps
  a `.before-estate-agent` copy. Do not tidy it up or delete it yourself.
- **Never guess a build or test command.** Leave it blank and say which one you
  could not determine and what you tried. A wrong test command is worse than a
  missing one, because the next agent will trust it.
- If `estate sync` reports a file was edited by hand, **do not use `--force`**.
  Show the human the lines and ask where they belong in the deed.
