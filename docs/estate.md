# The estate map

**What this is for:** explaining how Estate Agent works out which service calls
which, across languages that share no package manager — and why you can trust
the answer.

---

## The problem with the obvious approach

The obvious approach is to parse everything. It does not survive contact with a
real estate.

The best available code-graph tool covers Java, Rust, .NET, Node and Kotlin. It
does not cover Swift, BrightScript, or RPG. It does not link separate
repositories, and it does not read OpenAPI, protobuf or GraphQL at all. For a
ten-stack estate that is half your repos and none of your cross-service
connections. And it is not a gap anyone will close: there is no tree-sitter
grammar for BrightScript or RPGLE, and there is unlikely ever to be one.

So Estate Agent does not parse ten languages.

> **It reads the contracts between them instead.**

Every service already declares what it offers and what it needs, in places that
are language-neutral: API spec files, generated client libraries listed as
dependencies, and configured service URLs. Those work identically for Rust and
for RPG, because understanding neither is required.

---

## What it reads

**Contracts, first and most trusted.** `openapi.yaml`, `swagger.json`,
`*.proto`, `*.graphql`, `asyncapi.yaml`.

**Route declarations, where no contract exists.** Spring's `@GetMapping`,
ASP.NET's `[HttpGet]`, Express and Fastify routes, Axum and Actix routers,
FastAPI and Flask decorators, Next.js file-based routes.

**Call sites, per stack.** Feign clients, `RestTemplate`, `HttpClient`, Refit,
`axios`, `fetch`, `reqwest`, Retrofit, `URLSession`, Alamofire, `roUrlTransfer`,
gRPC stubs, Kafka topics, SQS queues.

**Dependencies that name a service.** A repo depending on `payments-client` is
strong evidence it calls `payments-api`.

**Configuration.** Base URLs and the *names* of the variables holding them —
`PAYMENTS_API_URL` identifies a service even when its value is a placeholder.

---

## The resolution ladder

A raw signal ("this line calls something") is not yet a connection. Resolving
it into "calls `payments-api`" happens on a ranked ladder, and every edge on
the map records which rung it came from:

| Rung | Means | Confidence |
|---|---|---|
| `declared` | the source names the service outright — `@FeignClient("payments-api")` | 0.95 |
| `dependency` | a generated client for that service is a dependency | 0.90 |
| `env` | a configured variable names it — `PAYMENTS_API_URL` | 0.75 |
| `host` | a URL's hostname matches the service | 0.70 |
| `path` | the called path matches exactly one service's declared endpoint | 0.60 |

Below that rung, nothing is invented.

---

## Why you can trust it

**Every connection cites its evidence.** File and line. If you doubt an edge,
open the line and look. No edge exists without one.

**Ambiguity becomes a question, not a guess.** If a call could plausibly mean
two services, it resolves to neither and goes to the *Needs confirming* section
of `ESTATE.md`. Answer it once, in the calling repo's deed, and it never asks
again. A map that cries wolf twice stops being read — including the parts that
were right.

**Third-party services are separated from questions.** A call to
`api.stripe.com` is not something a colleague can adjudicate; it is simply
outside the estate. Those are listed under *Outside the estate* instead, where
they answer a different useful question: what do we depend on that we do not
control.

**Nothing is inferred by a model.** This is file reading and a ranking ladder.
The same estate always produces the same map, which means a change in the map
means a change in your code, not a change in the weather.

**Self-calls are dropped.** A repo calling its own `/api/...` route is not a
connection, and in a Next.js estate that is most of the call sites.

**Catch-all routes are ignored.** A route like `/{full_path:path}` matches
everything; indexing it would make one repo appear to own every path in the
estate. This was found by dogfooding on real repos, not by reasoning about it.

---

## Measured accuracy

`tests/fixtures/estate/` is a small polyglot estate whose connections are known
exactly, with each rung of the ladder exercised once plus one genuinely
ambiguous call.

```
$ python3 tests/run_all.py --report

  Repos classified            8
  Real connections found      8/8   (recall 100%)
  Phantom connections         0     (precision 100%)
  Sent for confirmation       1
```

The honest caveats: recall on a real estate will be lower than on a fixture,
and it varies by stack. Retrofit and Feign give near-perfect coverage because
one annotation states the whole answer. BrightScript is the weakest, because
there is no parser and detection rests on `roUrlTransfer` call sites. Estate
Agent notes that in the register rather than letting you assume even coverage.

---

## Using it

```bash
estate scan ~/work                          # build the map
estate impact payments-api /v2/charge       # what breaks if I change this
estate impact payments-api --json           # same, for a script
```

`scan` writes `ESTATE.md` (readable), `estate/graph.json` (queryable), and adds
a `related_repos` list to each deed so a single-repo agent session starts out
knowing its neighbours.

## When the map is wrong

It will sometimes be. Two ways to correct it, both permanent:

**A missing connection** — declare it in the calling repo's deed. Declared
connections outrank everything detected:

```yaml
consumes:
  - service: payments-api
    via: rest
    evidence: src/main/java/Client.java:42
```

**A wrong connection** — tell us. If a pattern produced a phantom edge, that is
a bug in a stack profile and worth fixing for everyone. See
[adding a stack](adding-a-stack.md).
