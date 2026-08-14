# Glossary

**What this is for:** defining every term Estate Agent uses, including the ones
the rest of the industry uses carelessly. No prior knowledge assumed.

---

**Agent** — an AI assistant that can act, not just answer: read files, run
commands, edit code, open pull requests. Claude Code, Cursor, Copilot's agent
mode and Gemini CLI are all agents. The distinction from a chatbot matters,
because an agent can do damage.

**AEO** — answer engine optimisation. Being the source an AI cites when
somebody asks it a question, in the way SEO is about being the link a search
engine returns.

**Blast radius** — everything that breaks if you change one thing. `estate
impact` computes it. See also *expand and contract*.

**Catch-all route** — a route like `/{full_path:path}` that matches every
request. Estate Agent ignores these when identifying services, because a repo
with one would otherwise appear to own every path in the estate.

**Client app** — an app your users install: iOS, tvOS, Android, Roku, or a web
front end. Treated specially throughout, because it cannot be rolled forward —
see *ship cost*.

**Confirm list** — the "Needs confirming" section of `ESTATE.md`: connections
that could plausibly point at two services. Estate Agent asks rather than
guesses. Answering one is permanent.

**Context file** — a file an AI assistant reads automatically to learn how to
work in a repo. Each assistant wants its own: `CLAUDE.md`, `AGENTS.md`,
`.cursor/rules/`, `.github/copilot-instructions.md`, `GEMINI.md`. Estate Agent
generates all five from the deed so you never hand-maintain them.

**Deed** — `.agent/estate.yaml`, the one file per repo that everything else is
generated from. Named after the legal document because it is short,
authoritative, and someone signs it.

**Drift** — when a generated file no longer matches the deed it came from.
`estate check` fails on it. Distinguished carefully from a *hand edit*.

**Estate** — all your repos, taken together. The thing no single agent session
can see, and the reason this project exists.

**Evidence** — the exact file and line proving a connection is real, recorded
on every edge of the map. If there is no evidence, there is no edge.

**Expand and contract** — the safe way to change a shared API: add the new
shape, migrate every caller, and only then remove the old shape. Estate Agent's
landing order is this pattern applied to your actual dependency graph.

**Hand edit** — a change someone made directly to a generated file. Estate
Agent detects it and refuses to overwrite it, offering to move it into the deed
instead. See [self-healing](self-healing.md).

**Hook** — a script an assistant runs automatically at a defined moment.
Estate Agent's secret guard is a hook that runs *before* every tool call and
can block it.

**Infrastructure** — a shared cluster, cache, database or queue. Two services
join the same node only when they name the same host or declared resource; a
container image in one repo's compose file is local development, not a shared
production cluster.

**Level** — how far *you* have adopted, from 0 (nothing) to 4 (it stays true on
its own). Not to be confused with a *tier*: a level describes your adoption, a
tier describes what one repo lets an agent do. See
[the five levels](levels.md).

**MCP** — Model Context Protocol, a standard way to give an assistant access to
an external tool or data source. Estate Agent does not require any MCP server;
some optional level-3 tools use one.

**Monorepo** — one repository containing many packages or services. Estate
Agent handles nested deeds; see [monorepos](monorepo.md).

**Permission profile** — the deny/ask/allow rules in `.claude/settings.json`
that stop an agent running irreversible commands. Estate Agent ships a reviewed
baseline.

**Provider / consumer** — a service that exposes an endpoint, and a service
that calls it. The map is built by matching one to the other.

**Register** — `ESTATE.md`, the human-readable listing of the whole estate.

**Resolution ladder** — how a connection was identified, ranked by trust:
`declared` > `dependency` > `env` > `host` > `path`. Shown on every edge so you
can weigh it.

**Secret guard** — the hook that blocks an agent from reading or writing
credentials. Measured at 32/32 real credentials caught with 0 false positives
on ordinary code.

**Ship cost** — how many release cycles you are committed to supporting an old
API shape. Zero for a service you can redeploy; roughly two for a mobile or TV
app that goes through store review and lingers on old versions. This is what
drives the ordering in `estate impact`.

**Stack** — a language-plus-ecosystem: `java`, `rust`, `react-web`,
`roku-brightscript`. Each is one YAML file in `stacks/`; adding a language
means adding one file and no code.

**Stack profile** — that file. It holds detection rules, build and test
commands, conventions, and the patterns for finding endpoints and call sites.

**Tier** — how much autonomy an agent gets in a repo: 1 restricted, 2
reviewed, 3 autonomous. Distinct from a *level*, which is how far you have
adopted overall. See [tiers](tiers.md).

**Upkeep** — `estate upkeep`, the self-healing command.

**Vault** — the estate written as linked markdown: `estate vault`. Generated
notes under `Generated/`, human-authored ones (investigations, decisions,
runbooks, concepts) in sibling trees that link into them. Readable in Obsidian,
GitHub, `rg`, or by an agent.

**Workspace** — the directory holding your repos, the thing you point `estate
scan` at.
