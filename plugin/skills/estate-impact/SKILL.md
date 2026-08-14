---
name: estate-impact
description: Find out what breaks elsewhere in the estate before changing an API, endpoint, schema, queue message, or shared contract. Use before any change to something other repos consume, and whenever the user asks "what depends on this" or "what will this break".
---

# Check the blast radius first

An agent sees one repo. The consumers of the thing you are about to change are
usually in other repos, in other languages, and some of them are apps that ship
on app-store timelines and cannot be fixed forward.

## Do this before changing a shared contract

```bash
estate impact <repo> <endpoint>      # e.g. estate impact payments-api /v2/charge
estate impact <repo> --json          # machine-readable
```

If there is no map yet: `estate scan <the directory holding the repos>`.

## Reading the result

- **Services** in the list can be updated and deployed with you.
- **Client apps** (iOS, tvOS, Android, Roku, web) cannot. They need their own
  release, and users on old versions keep calling the old shape for months.
- Where any client app appears, the change **must** be expand-and-contract: add
  the new shape, migrate consumers, ship the clients, and only remove the old
  shape much later. Follow the printed landing order.

## Rules

- Report the affected list to the human before making the change, not after.
- If `ESTATE.md` has entries under *Needs confirming*, say so — the list may be
  incomplete. Do not guess at them yourself.
- If you find a consumer the map missed, add it to the calling repo's deed
  under `consumes:` with its evidence. Declared connections outrank detection
  and are never re-derived.
