# claude_issues.md — issue inbox

This file is the inbox for bugs, regressions, or follow-ups that must be
fixed **before** further progress on `claude_project.md`.

When the user says **"continue"**, Claude reads this file first and resolves
every unchecked item in **Open issues** in its own commit on the
`claude_optimization` branch, marking the item `- [x]` as it is fixed. Only
when the open list is empty does Claude advance to the next un-committed
step in `claude_project.md`.

Issues that already have a documented home in a future plan phase live
under **Scheduled / deferred** — they are reminders, not blockers. Moving
an item into that section requires either (a) the issue itself naming a
phase, or (b) a fresh decision entry in `claude_decisions.md` explaining
why the deferral is safe.

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

## Scheduled / deferred (will be addressed by a specific plan phase)

- [ ] **`MIL.create_mda` mutable-default trap** *(scheduled for Phase 10.8)* — defaults `xy_positions=[]` *and* `xyz_positions=[]` together which pycromanager rejects, and `position_labels=[]` + `xy_positions=[]` silently yields zero events. Captured by `tests/test_mda_event_builder.py::test_default_call_raises_due_to_mutex_defaults`. After the Phase 10.8 fix, update that test from "expects ValueError" to "raises typed MDAEventError" or "returns saner default events". See `glados_pycromanager/Core/microscopeInterfaceLayer.py:654`.

---

## Resolved (history)

*(populated as items get checked off; keep for traceability)*
