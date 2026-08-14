---
name: estate-correct
description: Correct a repo's Estate Agent context when reality contradicts it - a documented command fails, a service was renamed, an endpoint moved, or a related repo no longer exists. Use whenever the notes turn out to be wrong rather than working around them.
---

# When the notes turn out to be wrong

Generated context files go stale. Stale instructions are worse than none: you
act on them confidently and are wrong quickly.

So when reality contradicts the notes, correcting them is part of the task.

## The protocol

1. Fix **`.agent/estate.yaml`** — the source. Never edit `CLAUDE.md`,
   `AGENTS.md`, `GEMINI.md`, `.cursor/rules/` or `copilot-instructions.md`;
   those are generated and your edit will be overwritten.
2. Run `estate sync`.
3. Mention the correction in the pull request description, one line, so a human
   can sanity-check it.

## Also useful

```bash
estate upkeep             # find everything stale, repair what is safe
estate upkeep --dry-run   # show what it would do, change nothing
estate doctor             # what is set up here and what is missing
```

## Rules

- **Do not silently work around a wrong instruction.** Fix it.
- `upkeep` reports broken commands rather than rewriting them, because choosing
  the replacement needs judgement. Make that call explicitly, or ask.
- Never relax a safety rule to make something pass. If the secret guard blocks
  you, read the reason and tell the human the finding ID — let them decide
  whether to allowlist it.
