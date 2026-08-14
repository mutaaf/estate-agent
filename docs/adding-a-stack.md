# Adding a language

**What this is for:** teaching Estate Agent a stack it does not know. It is one
YAML file and no code, which is deliberate — it is the main way this project
can cover estates nobody anticipated.

---

## The whole extension model

Drop a file in `stacks/`. That is it. Nothing to register, no code to change.

```yaml
stack: elixir
display: Elixir
kind: backend          # backend | client | legacy

detect:
  files: [mix.exs]
  extensions: ['.ex', '.exs']

commands:
  build: mix compile
  test: mix test
  lint: mix credo

conventions:
  - Let it crash; supervise rather than defensively rescue
  - Keep processes small and message-driven

tier_default: 2

provides:
  contracts: [openapi.yaml, priv/*.proto]
  routes:
    - name: phoenix-route
      regex: '\b(get|post|put|delete|patch)\s+"([^"]+)"'
      method_group: 1
      path_group: 2

consumes:
  patterns:
    - name: httpoison-call
      regex: '\bHTTPoison\.(get|post|put|delete)!?\s*\(\s*([^,)]+)'
      url_group: 2
      via: rest
```

Then check it loaded:

```bash
python3 -c "import sys; sys.path.insert(0,'src'); \
  from estate_agent import stacks; print(stacks.LOAD_ERRORS or 'clean')"
```

`LOAD_ERRORS` is empty when everything parsed and every regex compiled. A
pattern that fails to compile is *reported*, never silently dropped — a
silently dropped pattern means silently missing connections, which is the worst
possible failure for a map.

---

## The fields

**`detect`** — how to recognise the stack.

| Key | Meaning |
|---|---|
| `files` | marker files; globs allowed (`*.csproj`) |
| `not_files` | presence of these argues *against* this stack |
| `extensions` | source file extensions |
| `min_source_files` | how many before it counts |
| `any_dirs` | a directory that suggests this stack |
| `content_markers` | strings to look for inside root build files |
| `requires_marker` | when true, one of `any_dirs`/`content_markers` is **mandatory** |

`requires_marker` exists because some stacks are indistinguishable by marker
file alone. tvOS and iOS both have an `.xcodeproj` and `.swift` sources, so
without it every iOS repo would be classified as tvOS. If your stack is a
sibling of an existing one, you almost certainly need it.

**`commands`** — build, test, lint, and `alternatives` for when the same
language has several build systems:

```yaml
commands:
  build: ./gradlew build
  alternatives:
    - when: pom.xml
      build: mvn -q package
```

**`provides.routes`** — regexes that find endpoint declarations. Name the
capture groups with `path_group`, `method_group`.

**`consumes.patterns`** — regexes that find outbound calls. Name the useful
group with exactly one of:

| Group | Use when the pattern captures | Resolves via |
|---|---|---|
| `service_group` | a service name outright | `declared` — strongest |
| `url_group` | a URL or an expression containing one | `host` or `path` |
| `path_group` | a path fragment | `path` |
| `env_group` | an environment variable name | `env` |
| `topic_group` | a queue or topic name | `topic` |

Add `confidence: declared` when the pattern is unambiguous — Retrofit's
`@GET("/v2/charge")` and Feign's `@FeignClient("payments")` both are.

**`kind`** matters more than it looks. `client` puts a repo at the end of every
landing order and marks it as unable to roll forward. `legacy` defaults to tier
1 and to being described rather than parsed.

---

## Two rules for writing patterns

**Prefer precision over coverage, always.** A pattern that occasionally invents
a connection is worse than one that occasionally misses one. Missed connections
get added by hand and stay added; phantom ones destroy trust in the whole map,
including the parts that were right.

**Quote regexes with single quotes.** Estate Agent's YAML reader treats
single-quoted strings as verbatim, so `\d+` survives. Use `''` for a literal
apostrophe inside one.

---

## Testing it

Add a small repo to `tests/fixtures/estate/` with a connection you know exists,
add the expected edge to `GROUND_TRUTH` in `tests/test_estate_map.py`, and run:

```bash
python3 tests/run_all.py --report
```

Precision must stay at 100%. If your new pattern adds a phantom edge somewhere
else in the fixture, the suite will say so — which is the point.

---

## Stacks that would be genuinely useful

Go, Ruby on Rails, PHP/Laravel, Scala, Elixir, Flutter, React Native, Unity,
COBOL on z/OS, Salesforce Apex, SAP ABAP, and anything embedded.

The mainframe and enterprise-platform ones are the most valuable and the least
likely to be covered by anything else. Follow the `as400` profile's approach
for those: describe the interface rather than trying to parse the language, and
default the tier to restricted.
