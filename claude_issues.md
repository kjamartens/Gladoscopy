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

*(none yet)*

---

## Resolved (history)

- [x] **`MIL.create_mda` mutable-default trap** — fixed in Phase 10.8. Mutable defaults replaced with `None`; bare `create_mda(num_time_points=N)` now yields a clean time-only event list. Bad plans (negative frames, zero-step z-stack, empty channel name, exposure/channel mismatch, channels without channel_group) raise `MDAEventError`. The regression test `test_default_call_raises_due_to_mutex_defaults` was renamed and inverted to `test_default_call_now_produces_time_only_events` and now asserts the saner default behaviour.
