---
name: New stack profile
about: A language or platform Estate Agent does not cover yet
labels: stack-profile
---

## Which stack

<!-- Language / platform / framework. e.g. "Elixir + Phoenix", "COBOL on z/OS" -->

## Can you attach a scaffold?

If you can run Estate Agent on a repo in this stack:

```
estate contribute stack <repo> --name <stack>
estate contribute check <stack>.yaml <repo>
```

It is redacted — no repo names, no hosts, no paths, and anything in a local
`.publish-denylist` removed. **Read it before pasting.** Then paste it here:

```yaml

```

## If you cannot run it

That is fine — describe the stack and someone can write the profile:

- **Marker files** at the repo root (e.g. `mix.exs`, `go.mod`):
- **Source extensions** (e.g. `.ex`, `.exs`):
- **How routes are declared** (an example line, with names removed):
- **How outbound calls are made** (library, and an example line):
- **Build / test commands**:
- **Anything a competent new joiner should be told**:

## Coverage honesty

Is there anything in this stack a static reader genuinely cannot see — routes
computed at runtime, config assembled at deploy? Worth writing into the
profile's `notes` so nobody assumes even coverage.
