# Start here

**What this is for:** getting one repo set up in about fifteen minutes.

## 1. Install

```bash
git clone https://github.com/mutaaf/estate-agent ~/.estate-agent
export PATH="$HOME/.estate-agent/bin:$PATH"   # add to your shell profile
estate version
```

Nothing else. No package manager, no dependencies, no account.

## 2. Look before you leap

```bash
cd ~/work/your-repo
estate doctor
```

`doctor` changes nothing. It tells you what stack it thinks this is, what
context files already exist, and what is missing. Read it before going on.

## 3. Set the repo up

```bash
estate init
```

This writes `.agent/estate.yaml` — **the deed**, the one file you maintain —
and generates the five assistant files from it. If you already had a
`CLAUDE.md`, its commands and rules are folded into the deed and the rest is
kept verbatim; a copy of the original is saved next to it.

## 4. Check the deed

Open `.agent/estate.yaml`. Three things are worth thirty seconds each:

- **The commands.** Run them. A wrong test command is worse than none, because
  the agent will trust it.
- **The tier.** 1 = read only, 2 = pull requests with review, 3 = may merge on
  green CI. See [tiers](tiers.md).
- **`never_do`.** What would you tell a competent new joiner not to touch?

Then:

```bash
estate sync    # regenerate after any edit
git add .agent CLAUDE.md AGENTS.md GEMINI.md .cursor .github .claude
git commit -m "Set up Estate Agent"
```

## 5. Map the estate

If your repos live side by side in one directory:

```bash
estate scan ~/work
```

You get `ESTATE.md` — a readable register of every service, what it exposes,
and who calls it — and the ability to ask the question that matters:

```bash
estate impact payments-api /v2/charge
```

## 6. Keep it honest

Add this to CI so the generated files can never drift from the deed:

```yaml
- run: estate check --quiet
```

And once in a while, or when something feels stale:

```bash
estate upkeep
```

---

## The five commands, in one table

| Command | What it does | Changes files? |
|---|---|---|
| `estate doctor` | what is set up here, what is missing | no |
| `estate init` | set this repo up | yes |
| `estate sync` | regenerate the assistant files from the deed | yes |
| `estate check` | fail if anything has drifted — for CI | no |
| `estate upkeep` | find what has gone stale, repair what is safe | yes |
| `estate scan` | map every repo in a workspace | yes |
| `estate impact` | what breaks if you change this | no |
| `estate vault` | write the estate as linked markdown notes | yes |

## 7. Optional: a vault of linked notes

If you want the estate as a browsable knowledge base rather than a report:

```bash
estate vault ~/work
```

You get one note per service, per shared cluster, and per endpoint something
calls — wikilinked, with YAML frontmatter. Open it in Obsidian for the graph
view, read it on GitHub, or point an agent at the folder. It also scaffolds
`Investigations/`, `Decisions/` and `Runbooks/` for the things only a person
can write. Everything under `Generated/` is overwritten on each run; the human
trees never are.

## What next

- Not sure how far you have got? [The five levels](levels.md) has a
  four-question self-check.
- Adding a repo? Repeat steps 2–4. It gets faster.
- Curious how the map works? [The estate map](estate.md)
- Worried about safety? [What data goes where](data-flow.md)
- Need a word defined? [Glossary](glossary.md)
