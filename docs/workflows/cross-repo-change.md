# Worked example: changing an API that five things depend on

**What this is for:** following one realistic change end to end, from "we need
a new field" to "it is safe to delete the old one." This is the workflow Estate
Agent exists to make possible.

The estate below is the one in `tests/fixtures/estate/`, so you can run every
command in this document yourself.

---

## The task

> Add a `merchant_reference` field to the charge API, and make `description`
> optional.

In `payments-api` (Java) that is twenty minutes of work. The twenty minutes is
not the problem.

---

## Step 1 — ask what breaks

```bash
$ estate impact payments-api /v2/charge
```

```
If you change /v2/charge in payments-api
----------------------------------------
      POST /v2/charge
        src/main/java/com/acme/payments/ChargeController.java:5

  Directly affected:
  warn  ios-app     (CLIENT APP - ships on its own release cycle)
        calls payments-api via rest · path 0.60 · Sources/Endpoints.swift:2
  warn  roku-app    (CLIENT APP - ships on its own release cycle)
        calls payments-api via rest · host 0.70 · source/Api.brs:3
  warn  web-react   (CLIENT APP - ships on its own release cycle)
        calls payments-api via rest · env 0.75 · src/api.tsx:2
  FAIL  checkout-node        (node)
        calls payments-api via rest · env 0.75 · src/pay.ts:4
  FAIL  notifications-dotnet (dotnet)
        calls payments-api via rest · declared 0.95 · Startup.cs:3

  5 repos affected, 3 of them client apps
```

Five consumers across five languages. Three of them are apps on people's
phones and televisions.

**This is the moment the whole project pays for itself.** Without it, the
change looks like a twenty-minute job in one repo. The `roku-app` line in
particular is the one nobody remembers, and it is the one that generates a
support incident four weeks later.

---

## Step 2 — read the order, and understand why

```
  Ship in this order:
    1. Add the new shape to `payments-api` alongside the old one.
       Do not remove anything yet.
    2. Update and deploy the services that call it:
       `checkout-node`, `notifications-dotnet`.
    3. Ship the client apps: `ios-app`, `roku-app`, `web-react`.
       Each needs its own release, and users on older versions keep
       calling the old shape.
    4. Only once client adoption is high enough, remove the old shape
       from `payments-api`. This is usually months, not days.
```

The ordering rule is about **what you can take back**. A service can be
redeployed in minutes and rolled back almost as fast. A Roku channel or an iOS
app cannot: it goes through store review, ships to a fraction of users, and old
versions keep calling the old shape for months whatever you do.

So a client app in the blast radius is not a follow-up ticket. It is a
constraint on the server change itself — which is precisely why step 1 says
*add* rather than *change*, and why step 4 is months away.

If the list had contained only services, step 1 would have read "Change
`payments-api`" and there would be no step 4. The shape of the advice follows
the shape of your estate.

---

## Step 3 — make the change, expanding not replacing

In `payments-api`: add `merchant_reference` as optional, keep `description`
accepted, and keep returning it. Nothing breaks yet, because nothing has been
removed.

Add a test that the old request shape still works. That test is the thing
standing between you and step 4 done too early — it is worth more than the
feature.

---

## Step 4 — update the services

Each consumer repo has a deed, so an agent opening `checkout-node` already
knows it calls `payments-api` and what tier it is in. Open it, make the change,
let CI run, get it reviewed.

Both services can go in parallel. Neither can go before step 3 landed.

---

## Step 5 — ship the clients

Three releases, three timelines:

- `web-react` deploys like a service — fast, and effectively fully adopted.
- `ios-app` needs a release and store review. Adoption climbs over weeks.
- `roku-app` needs a channel update. Note the `roku-brightscript` warning in
  `ESTATE.md`: coverage for that stack is weaker than the others because there
  is no parser, so check its call sites by hand rather than trusting the map to
  be complete here. Estate Agent tells you where it is less sure; it is worth
  reading those notes.

---

## Step 6 — contract, much later

Only when telemetry says old-shape traffic has fallen far enough. Then remove
`description` from `payments-api` and run the impact query again to confirm
nothing new has appeared while you waited — because in three months, something
usually has.

---

## What the agent does differently now

Before Estate Agent, an agent asked to "make `description` optional" would edit
`payments-api`, run its tests, see green, and open a pull request. Everything
it did would be correct and the estate would still break, because the
information needed to know better was not available to it.

After, the agent working in `payments-api` reads in its context file:

> **Services this one calls** — changing how you use these affects them, and
> changing your own endpoints affects whoever calls you.
>
> Before changing anything on this list, run `estate impact payments-api
> <endpoint>` to see everything that breaks — including the mobile and TV
> clients, which ship on their own timelines and cannot be fixed after the
> fact.

Which is the entire difference: not a smarter agent, a better-informed one.

---

## If the map missed a consumer

It will happen — recall is not perfect, and it is weakest on stacks with no
parser. When you find one, write it into the calling repo's deed. Declared
connections outrank everything detected and are never re-derived:

```yaml
consumes:
  - service: payments-api
    via: rest
    evidence: src/legacy/PaymentBridge.cls:88
```

Now it is on the map permanently, and the next person to run `estate impact`
sees it. Every gap you close stays closed.
