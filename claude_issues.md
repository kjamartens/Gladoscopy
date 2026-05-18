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

- [ ] **`liveMode` flips back to False ~1 s after being set programmatically** — When `shared_data.liveMode = True` is set from the Phase 13.1 `--profile-runtime` orchestration, the log shows `LIVE mode changed!` immediately followed (within ~250 ms) by `Live mode stopped` (the False branch of `acqModeChanged`, `napariGlados.py:821`). User confirmed the demo cam + PyMMCorePlus is stable for hours when live is toggled via the LiveModeButton, so the issue is in the programmatic path, not the backend. The pymmcore-plus warning `Expected 999, got N` after the stop is intended behaviour (`stop_sequence_acquisition()` cancels the in-flight MDA at frame N). What we still need to find: who sets `liveMode=False`. Candidates to investigate:
  - The outer `while self.acqstate:` loop in `run_MILCoreAcquisition_worker` (`napariGlados.py:528`) exits — its only exit path is `acqstate` flipping False, which is set in `acqModeChanged` when `liveMode=False`. Circular ⇒ someone else writes to `shared_data.liveMode` externally.
  - Reproduce: `make profile-runtime PROFILE_SECS=8` against `--auto-demo`.
  - Investigation idea: temporarily put a `traceback.print_stack()` inside the `liveMode` setter when `new_value is False` and re-run.
  - Note: profile data is still being captured before the abort (watchdog dumps on `liveMode-auto-stop`), so this does not block Phase 13.1 — but it does block fully unattended longer profiling and should be resolved before 13.5/13.6 measurements.

---

## Scheduled / deferred (will be addressed by a specific plan phase)

*(none yet)*

---

## Resolved (history)

- [x] **`make run-dev` / `make run-prod`** — added `run-dev` (editable dev install then launch) and `run-prod` (non-editable production install then launch) combined targets to `Makefile`. Updated `.PHONY` list and top-of-file quick-start comment. Committed in `build: add run-dev and run-prod combined targets`.
- [x] **`MIL.create_mda` mutable-default trap** — fixed in Phase 10.8. Mutable defaults replaced with `None`; bare `create_mda(num_time_points=N)` now yields a clean time-only event list. Bad plans (negative frames, zero-step z-stack, empty channel name, exposure/channel mismatch, channels without channel_group) raise `MDAEventError`. The regression test `test_default_call_raises_due_to_mutex_defaults` was renamed and inverted to `test_default_call_now_produces_time_only_events` and now asserts the saner default behaviour.
