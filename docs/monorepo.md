# Monorepos and satellites

**What this is for:** setting up a repo that contains many packages, and the
separate repos orbiting it.

---

## The rule that does the work

> **If a fact appears in two context files, it belongs in exactly one of them.**

Everything below is that rule applied. Duplication between a root deed and a
package deed is not redundancy — it is two facts that will disagree in six
months, and the agent has no way to know which one is current.

---

## Layout

A deed per package, plus one at the root:

```
platform/
├── .agent/estate.yaml          root: what is true everywhere
├── CLAUDE.md                   generated
├── services/
│   ├── payments/
│   │   ├── .agent/estate.yaml  payments only
│   │   └── CLAUDE.md           generated
│   └── ledger/
│       ├── .agent/estate.yaml
│       └── CLAUDE.md
└── packages/ui/
    └── .agent/estate.yaml
```

Run `estate init` in each package that has its own build, its own tests, or its
own risk profile. A package that is genuinely just a folder of shared types
does not need one.

## What goes where

**Root deed** — only what is true of every package: the monorepo tool, the
commit convention, the shared lint setup, the org-wide never-dos.

```yaml
repo:
  name: platform
  stack: node
  tier: 2
commands:
  install: pnpm install --frozen-lockfile
  test: pnpm -r test
conventions:
  - Conventional Commits; the release tooling parses them
never_do:
  - Add a dependency to the root package.json; add it to the package
```

**Package deed** — only what is specific. Do not restate the root:

```yaml
repo:
  name: payments
  summary: Card payments and refunds.
  stack: java
  tier: 1
commands:
  test: ./gradlew :services:payments:test
never_do:
  - Modify anything under src/generated
```

Note that `payments` is tier 1 while the root is tier 2. **This is the main
reason to split deeds at all.** A repo containing both a marketing site and a
payments module should not have one tier; giving the whole monorepo the
strictest tier makes agents useless in the safe parts, and giving it the
loosest makes them dangerous in the risky ones.

Commands are the other reason: `pnpm -r test` at the root is correct but slow,
and an agent working on one package should be told the command that tests that
package.

## How assistants combine them

Claude Code reads the `CLAUDE.md` at the repo root and the nearest one to the
files being edited. Cursor applies rules by path. So an agent working in
`services/payments/` sees the root file plus the payments file, and the package
file wins where they overlap — which is exactly why they should not overlap.

## Satellites

Separate repos around the monorepo work identically: `estate init` in each, then
one scan across the parent directory that holds them all.

```
~/work/
├── platform/          the monorepo
├── ios-app/
├── roku-app/
└── payments-bridge/

$ estate scan ~/work
```

The scan maps across the boundary, so `estate impact payments /v2/charge`
includes the satellite clients, and each deed gets a `related_repos` list so a
single-repo session starts out aware of its neighbours.

## Practical notes

**Package deeds are cheap; write them for the packages that matter.** Ten
identical deeds for ten trivial packages is worse than none.

**Check per package, not just at the root.** In CI:

```yaml
- run: |
    for deed in $(find . -name estate.yaml -path '*/.agent/*'); do
      estate check "$(dirname "$(dirname "$deed")")" --quiet || exit 1
    done
```

**A monorepo can be several stacks.** A Java service and a React app in one
repo is normal. Give each its own deed with its own `stack:`; detection handles
the rest.
