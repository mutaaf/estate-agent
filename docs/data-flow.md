# What data goes where

**What this is for:** to answer, precisely and in one page, the question a security reviewer will ask before letting Estate Agent near your code. Forward it unedited.

Short version: **Estate Agent has no network code.** Levels 1 and 2 make no outbound connection of any kind. There is no telemetry, no analytics, no licence check, no update ping, no crash reporting, and no account.

---

## The honest baseline

Estate Agent does not introduce AI into your workflow. It assumes you already use an AI coding assistant, and that assistant already sends code to its provider — that is how it works, and it is pre-existing to anything here.

**Estate Agent's own contribution to that flow is one thing: it changes which context files the assistant reads.** The files it generates live in your repo, are written in plain text, and are reviewed in pull requests like any other file. It sends nothing itself.

The rest of this page is about what Estate Agent does, not about what your assistant already does.

---

## The table

| Level | Component | Reads | Writes | Sends over the network |
|---|---|---|---|---|
| **1** | `estate init` / `sync` / `check` | Build files, existing context files, your deed | `.agent/`, generated context files, `.claude/settings.json` | **Nothing** |
| **1** | Secret guard hook | The tool call the assistant is about to make | `.agent/.local/friction.jsonl` (counters) | **Nothing** |
| **1** | Permission profile | — | — | **Nothing** |
| **1** | `estate upkeep` | The same files as above | The same files as above | **Nothing** |
| **2** | `estate scan` / `impact` | Source files in the workspace you point it at | `estate/estate.yaml`, `estate/graph.json`, `ESTATE.md` | **Nothing** |
| **3** | Graphify *(optional, not installed by default)* | Your source | `graphify-out/` | Nothing for code (local AST). Non-code files such as PDFs are sent to your assistant's model — see their docs |
| **3** | MemPalace *(optional, not installed by default)* | **Your assistant's conversation transcripts** | `~/.mempalace/` | Nothing by default (local embedding model) |
| **3** | Obsidian *(optional)* | Your vault | Your vault | Nothing unless you enable their paid sync |

---

## How to verify the "nothing" claims yourself

Do not take the table on trust. Estate Agent is a few thousand lines of standard-library Python with no dependencies, so this is checkable in about a minute:

```bash
# 1. No networking libraries are imported anywhere.
grep -rnE '\b(socket|urllib|http\.client|requests|httpx|ssl|smtplib|ftplib)\b' \
  src/ hooks/ bin/

# 2. No dependencies to audit.
cat requirements.txt 2>/dev/null || echo "no requirements file - stdlib only"

# 3. Watch it run with no network access at all.
#    On macOS/Linux, this should complete normally:
estate scan ~/work
```

The project's own CI runs check 1 on every commit and fails the build if a networking import appears.

---

## Level 3 needs a conversation, and here is why

Levels 1 and 2 are files on disk and read-only scans. Level 3 is different in kind, and we would rather say so plainly than bury it:

**MemPalace reads your assistant's conversation transcripts.** Those transcripts contain whatever you and the assistant discussed — which in a real working session can include customer data, internal system names, incident details, and occasionally credentials pasted in haste. It stores them locally and embeds them locally, so nothing leaves the machine by default. But "on disk in a searchable index" is a different risk profile from "scrolled past in a terminal," and it is a decision for whoever owns data governance where you work, not one to make by installing a tool.

**Graphify sends non-code files to a model.** Source code is parsed locally with tree-sitter and stays put. Documents, PDFs, and images go through your assistant's model API for semantic extraction. If your repos contain design documents or specifications with sensitive content, that matters.

Neither is installed by Estate Agent, neither is required, and Levels 1 and 2 are fully functional without them. Adopt Level 3 deliberately or not at all.

---

## What Estate Agent writes into your repo

Everything is plain text and reviewable:

| Path | What it is | Committed? |
|---|---|---|
| `.agent/estate.yaml` | The deed — your repo's source of truth | Yes |
| `.agent/secret-guard-allow.txt` | Reviewed exceptions to the secret guard | Yes |
| `.agent/.local/` | Friction counters, scan cache | **No** — git-ignored |
| `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` | Generated context files | Yes |
| `.cursor/rules/00-estate.mdc` | Generated context file | Yes |
| `.github/copilot-instructions.md` | Generated context file | Yes |
| `.claude/settings.json` | Permission profile and hook wiring | Yes |
| `estate/` | The estate map, at the workspace root | Your choice |

`.agent/.local/` is the only thing not intended for version control, and it contains counters — how often a rule fired — not content.

---

## Questions reviewers actually ask

**Does it phone home?** No. There is no network code in the project.

**Is there telemetry, even anonymous?** No. The friction counters in `.agent/.local/friction.jsonl` are read by `estate doctor` on your machine and go nowhere else.

**Does it need an account, licence, or API key?** No.

**What are its dependencies?** None. Standard-library Python 3.9+ and shell.

**Can it modify our source code?** `estate` commands only write the files in the table above. The self-healing routine is explicitly restricted to Estate Agent's own files and will not touch source.

**Can it weaken our security settings on its own?** No. Self-healing may *suggest* relaxing a rule that is generating friction; only a human can apply it. Automated changes only ever tighten or report.

**What happens if we stop using it?** Delete `.agent/`, the generated files, and `estate/`. Nothing else is touched, and nothing outside the repo holds state.

**Is it open source?** MIT licensed, source at `github.com/mutaaf/estate-agent`.
