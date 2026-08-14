---
name: The secret guard blocked something safe
about: A false positive in the credential guard
labels: guard, precision
---

A guard that cries wolf gets switched off, and a switched-off guard protects
nothing. This is as valuable as a missed credential.

## The code that tripped it

Redact it if you must — as long as the **shape** survives, since the shape is
what the detector matched.

```

```

## What the guard said

<!-- The whole message, including the finding ID -->

## What it actually is

<!-- e.g. "a variable holding the result of a function call, not a secret" -->

This becomes a case in `MUST_ALLOW` in `tests/test_secret_guard.py`, so the
measured false-positive rate stays honest.
