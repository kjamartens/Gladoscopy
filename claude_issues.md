# claude_issues.md — issue inbox

This file is the inbox for bugs, regressions, or follow-ups that must be
fixed **before** further progress on `claude_project.md`.

When the user says **"continue"**, Claude reads this file first and resolves
every unchecked item in its own commit on the `claude_optimization` branch,
marking the item `- [x]` as it is fixed. Only when the list is empty (or
all items are checked) does Claude advance to the next un-committed step in
`claude_project.md`.

## How to add an issue

Append a checklist item under `## Open issues`:

```
- [ ] short description (file:line if relevant) — reproduction / context
```

Add longer context underneath as a nested bullet if needed.

---

## Open issues

*(none yet)*

---

## Resolved (history)

*(populated as items get checked off; keep for traceability)*
