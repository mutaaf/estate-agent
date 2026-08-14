# Field-testing it on a real estate

**What this is for:** running Estate Agent against real repositories, finding
what it gets wrong, and reporting that without leaking anything.

Everything in this project that works was found this way. Reasoning about a
scanner tells you almost nothing; running it against a machine with real code
on it tells you everything within about a minute.

---

## Why this page exists

The bugs that matter only appear against real repos, and real repos at work are
confidential. That combination normally means the bug is found and never
reported. `estate report` exists to break that: it produces a diagnostic where
every repo is `repo-01`, every host is `host-a`, and every path is reduced to
its filename and line number — while keeping the shape of the problem intact.

---

## The loop

### 1. Install somewhere permanent

```bash
git clone https://github.com/mutaaf/estate-agent ~/.estate-agent
echo 'export PATH="$HOME/.estate-agent/bin:$PATH"' >> ~/.zshrc
exec zsh
estate version
```

### 2. Scan, and time it

```bash
estate scan ~/work
```

Note how long it takes. A hundred repos should be seconds, not minutes. If it
is slow, that is a bug worth reporting on its own — the first real scan of this
project took 69 seconds for 25 repos, and the cause was recursive globs
descending into `node_modules`.

### 3. Read `ESTATE.md` with a sceptical eye

Three questions, in order of importance:

**Is anything on the map wrong?** Pick three connections and check the cited
`file:line`. A phantom connection is the most serious possible finding.

**Is anything missing that you know exists?** Think of two services you know
talk to each other and see whether the map says so.

**Is the confirm list short enough that you would actually answer it?** If it
runs to dozens, that is a bug, not a chore.

### 4. Check the coverage report

```bash
estate report ~/work
```

The `silent` column is the one to read: repos that matched a stack but yielded
no endpoints and no call sites. A stack with a high silent count has a profile
that needs work, and that is the single most useful thing to report.

### 5. Report it

```bash
estate report ~/work --out ~/estate-report.md
```

Redacted by default. **Read it before sending** — that takes a minute and is
the only way to be sure. Then open an issue at
`github.com/mutaaf/estate-agent/issues` and paste it.

If you want the unredacted version for your own use, `--include-names` does
that and stamps **UNREDACTED** at the top so nobody forwards it by accident.

---

## Extra safety for a work machine

Create a `.publish-denylist` in the directory you run from — it is git-ignored,
so it never reaches the repo:

```
# One term per line. Never committed.
acmecorp
paymentsgateway
internal-hostname-prefix
```

Both `estate report` and the project's own publish check read it. Terms are
replaced with `[redacted]` in reports, and CI fails if any appear in the
repository itself.

This exists because the alternative — writing your employer's service names
into a public repo in order to check for them — is the leak you were trying to
prevent.

---

## What counts as a finding

Ranked by how much they matter:

| Finding | Why it matters |
|---|---|
| **A phantom connection** | The worst outcome. Two false alarms and nobody reads the map again. |
| **A silent stack** | The profile is not matching real code, so those repos are invisible. |
| **A confirm list nobody would answer** | The map stays permanently partial. |
| **A slow scan** | People stop running it, so it goes stale. |
| **A wrongly classified repo** | Wrong commands, wrong conventions, wrong tier default. |
| **A missed connection** | Real, but the least severe: add it to the deed by hand and it stays added. |

A useful report says which connections you checked and how many were real.
"It found 40 connections" is not a finding; "I checked 6, five were real, the
sixth pointed at a repo that merely shares a route name" is.

---

## Things already found this way

Written down because they are the pattern to look for, and because none of
them were visible by reading the code:

- **Recursive globs ignored the ignore list.** `Path.glob("**/*.proto")`
  descended into `node_modules`. 83% of runtime; 69s became 8s.
- **A nested checkout produced mutual phantom edges.** One repo contained a
  full clone of another in a workspace directory, so identical files were
  attributed to both and each appeared to call the other.
- **The self-call check was too narrow.** It only fired when the calling repo
  was the *sole* declarer of a path. A Next.js app calling its own
  `/api/scrape` while an unrelated project also declared `/api/scrape`
  resolved to the unrelated project. Route names like `/api/share` and
  `/api/og` recur across independent codebases constantly.
- **A route path was built wrongly.** `api/scrape.ts` was read as `/scrape`
  rather than `/api/scrape`, which is why the self-call above went unnoticed.
- **A match cap truncated silently.** One app hit exactly 200 endpoints — the
  limit — so its own routes were missing, and its calls to them resolved
  elsewhere. Caps now report themselves.
- **Adding `.ts` to a profile reclassified plain Node repos as React.** Fixed
  by making the React marker mandatory rather than additive.
- **A symlinked repo was skipped without an error**, so it was simply absent.

Every one was a minute's work to find and would never have been found by
reasoning about it.

---

## Two machines

Work on your own machine first. It is faster to iterate, you can fix and
re-run immediately, and the classes of bug are the same. Once it is clean
there, take it to the estate that matters — where the differences are scale,
stacks you do not have at home, and connections that genuinely exist.

Expect the second run to find a different set of problems. That is the point.
