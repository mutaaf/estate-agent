---
name: The map got something wrong
about: A phantom connection, a missed one, or a wrong classification
labels: precision
---

## What happened

<!-- Pick one:
     - it invented a connection that does not exist  (most serious)
     - it missed a connection that does exist
     - it classified a repo as the wrong stack
     - the confirm list is too long to answer      -->

## The redacted report

```
estate report ~/work --out report.md
```

Every repo becomes `repo-01`, every host `host-a`, every path its basename and
line. Safe to paste. **Read it first.**

```

```

## For a phantom connection

- The edge it produced (`from`, `to`, `resolved_by`):
- The evidence line it cited:
- What the code at that line **actually** does:

That is the most useful bug report this project can receive, and it becomes a
fixture case so the same false positive cannot come back.

## How many did you check?

<!-- "I checked six of the forty, five were real" is a finding.
     "It found forty" is not. -->
