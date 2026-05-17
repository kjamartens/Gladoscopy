# claude_decisions.md — design and process decisions

Append-only log of decisions made while executing `claude_project.md`. Each
entry is dated (YYYY-MM-DD), tagged by phase, and records the option chosen
plus the alternatives considered and the reason. The point is so a future
session can answer "why was it done this way?" without re-deriving the
context.

Format:

```
## YYYY-MM-DD — <short title>  [Phase X.Y]
**Decision:** what was chosen.
**Alternatives:** what was considered.
**Reason:** why this option won.
**Affects:** files / interfaces touched.
```

---

## 2026-05-17 — Branch base is `Code-cleanup`, not `main`  [Phase 0]
**Decision:** The `claude_optimization` branch is cut from `Code-cleanup`
(current branch at session start), not from `main`.
**Alternatives:** Branch from `main` (CLAUDE.md hint).
**Reason:** `Code-cleanup` is where the user is actively working and already
contains baseline state (the existing tests, the recent unit-test commit).
Branching from `main` would lose that context. PR target at the end of the
plan can still be `main` if desired.
**Affects:** git topology only.

## 2026-05-17 — Plan structure: Phase 0 is Claude architecture, Phase 1 starts code work  [Phase 0]
**Decision:** Phase 0 is dedicated to setting up the Claude-collaboration
files (`CLAUDE.md` updates, `claude_issues.md`, `claude_decisions.md`,
`.claude/` slash commands and agents skeleton, branch already in use).
**Alternatives:** Fold Claude setup into Phase 1 alongside repo guardrails.
**Reason:** User explicitly asked for a Claude-architecture-setup phase. Also
keeps the "continue" protocol functional from the very first resume.
**Affects:** `claude_project.md` numbering — every subsequent phase shifts
by 1 vs. the original draft.

## 2026-05-17 — Slack credentials: rotate-less path  [Phase 2]
**Decision:** The committed Slack token is treated as stale/expired and is
simply deleted from `WebhookConfig` defaults. No out-of-band rotation step
is forced on the user. A small GUI dialog ("Slack settings") is added to
let the user enter token + secret + channel at runtime; values are persisted
via the existing `glados_state.json` mechanism.
**Alternatives:** Keep the credentials in source until the user confirms
rotation; force an environment-variable-only path.
**Reason:** User confirmed the token is stale and no longer functional;
adding a GUI input is more user-friendly than env vars and matches the
project's existing settings-via-dataclass pattern.
**Affects:** `glados_pycromanager/GUI/sharedFunctions.py:WebhookConfig`,
new `glados_pycromanager/ui/dialogs/slack_settings.py` (or equivalent
location after the Phase 7 split).

## 2026-05-17 — Vendored Nodz left alone  [global]
**Decision:** `glados_pycromanager/GUI/nodz/` is treated as third-party code
and is excluded from all refactors, lint auto-fixes, type-hint passes, and
god-file splits.
**Alternatives:** Reformat / type-annotate Nodz alongside the rest of the
codebase.
**Reason:** It is vendored upstream; touching it makes future re-syncing
with upstream impossible. CLAUDE.md already labels it "vendored".
**Affects:** Phase 2 (`ruff`/`mypy` config must exclude `nodz/*`), Phase 7
(not in scope), Phase 14 (typing — not in scope), Phase 9 (error-handling —
not in scope).

## 2026-05-17 — Error handling: tighten **and** add  [Phase 9]
**Decision:** Phase 9 covers two complementary jobs:
(a) tighten the 131 existing bare/broad `except:` blocks, and
(b) **add** new validation/error-checks at boundaries that currently have
none — config load, plugin load, recipe load, MIL backend probe, MDA event
construction, file-write atomicity.
Every new check ships with a dedicated test (positive + negative path).
**Alternatives:** Only tighten the existing excepts; add new checks later.
**Reason:** User asked for "a pass on where to add new checks for errors"
and emphasized "properly done via many tests". Pairing the addition with
tests prevents the regression of swallowing errors silently again.
**Affects:** all top-level modules; new tests under `tests/test_errors_*.py`.

## 2026-05-17 — Conversation log: initial plan revisions  [Phase 0]
**Decision:** Treat the chat that produced these revisions as a
load-bearing artifact and copy it into this file (paraphrased) so future
sessions don't have to dig through old chat history.
**Alternatives:** Rely on commit messages + the decision entries above.
**Reason:** User explicitly asked to record the conversation here.
**Affects:** documentation only.

### Conversation (paraphrased)

**User (initial request, prior turn):** Create `claude_project.md` that
optimizes this software through five steps — understand the code, list what
is missing (traditional + AI POV), list detailed changes, performance ideas,
then a multi-phase Actionables section with steps, expected outcomes, and
proof. Do it on a new `claude_optimization` branch with small commits.
Also: when I say *continue*, first check `claude_issues.md` for issues,
fix those, then implement the actionables. Add that protocol to
`CLAUDE.md`.

**Claude (response):** Wrote first version of `claude_project.md` with 18
phases (0–17) and added a "continue" protocol section to `CLAUDE.md`.

**User (this turn's feedback):**
1. Phase 0 should explicitly set up the Claude architecture and double-check
   the interpretation of the request.
2. Create the branch *now*, switch to it, and use it from this point on.
3. Track decisions in a new `claude_decisions.md` and point to it from
   `CLAUDE.md`.
4. **Slack credentials**: don't bother with rotation — the token is stale.
   Just delete it and add a GUI method to input new values.
5. **Phase 9 (error handling)** should also include *adding new* error
   checks (not just tightening existing `except` blocks), and "properly
   done via many tests."
6. Leave the vendored Nodz subfolder alone.

**Claude (actions taken):**
- Cut and switched to `claude_optimization` from `Code-cleanup` (Bash:
  `git checkout -b claude_optimization`).
- Created `claude_issues.md` (empty inbox template).
- Created `claude_decisions.md` (this file) with format documentation and
  the four initial decisions: branch base, phase numbering, Slack handling,
  vendored Nodz exclusion, error-handling scope.
- Updated `CLAUDE.md` "Optimization plan & continue protocol" section to
  point at all three companion files, enforce branch check, and require
  decision logging.
- Rewrote `claude_project.md`:
  - Added "Interpretation check" section so the user can correct
    misreadings before the next "continue".
  - Replaced old Phase 0 with new Phase 0 "Claude architecture setup"
    (9 steps including this conversation's setup actions).
  - Renumbered all subsequent phases (old N → new N+1) so the plan now has
    19 phases (0–18).
  - Reworked the Slack phase (now Phase 2): remove hardcoded credentials,
    add a `slack_settings_dialog.py` QDialog, persist via existing
    `glados_state.json`, add no-op guard when token is empty, add tests.
  - Reworked the error-handling phase (now Phase 10) to have two halves:
    *(a)* tighten existing bare/broad excepts, *(b)* add new validation
    checks at 10 documented boundaries (Shared_data load/write, plugin
    metadata, recipe schema, MIL.set_core, MDA event builder, headless
    dialog inputs, Slack send, AppData walk, registry dispatch, global
    exception hook). Every addition pairs with positive + negative-path
    tests. Step 10.0 produces an explicit `docs/error-audit.md` listing
    Table A (existing excepts) and Table B (missing checks) before any
    code changes.
  - Added an explicit Nodz exclusion to Phase 3 (ruff/mypy/pre-commit
    configs), Phase 4 (module map + new ADR `0005-vendored-nodz.md`),
    Phase 8 (FlowChart split scope), Phase 10 (sweep scope), Phase 11
    (logging sweep scope), Phase 14 (tooltips attach from outside Nodz),
    Phase 15 (typing scope).
  - Fixed cross-phase references after renumbering.

## 2026-05-17 — Disable napari pytest plugins via addopts  [Phase 1.1]
**Decision:** Add `-p no:napari -p no:npe2 -p no:napari_plugin_engine` to
`addopts` in `[tool.pytest.ini_options]` so the full pytest suite runs from
the repo root without hanging.
**Alternatives:** (a) always invoke pytest with an explicit `tests/` path
(works but easy to forget and breaks `pytest` from any CWD), (b) downgrade
pytest or napari (risky pin churn), (c) actually delete the offending test
(no such test exists — the suite is 31 unit tests, all pure-logic).
**Reason:** `pytest -q` with no args hangs 10+ minutes; `pytest tests/` works
in ~1.2s; `--collect-only` is fast in both cases. Difference: napari's
pytest-plugin entry-point triggers `npe2` plugin discovery during session
teardown when rootdir scanning is broader. The Glados package registers a
napari manifest (`[project.entry-points."napari.manifest"]`), so the discover
step pulls in heavy Glados-side imports. Disabling the three offenders is
the lowest-risk fix and the result is identical to explicit-path mode.
**Affects:** `pyproject.toml` (`[tool.pytest.ini_options].addopts`).

## 2026-05-17 — uv.lock stays tracked  [Phase 1.2]
**Decision:** Leave `uv.lock` un-ignored (tracked when present). The default
`.gitignore` already comments it out with the recommendation to commit it.
**Alternatives:** Ignore it via `.gitignore` (skip lockfile entirely).
**Reason:** This is an application/UI bundle (not a library), so reproducible
installs from a committed lockfile are a clear win — matches the pyproject
hard-pin philosophy. There is no `uv.lock` in the repo yet; this decision
just preserves the default so when one is generated it gets tracked.
**Affects:** `.gitignore` (line 101 comment retained).

## 2026-05-17 — `.venv/` already ignored  [Phase 1.2]
**Decision:** Skip adding `.venv/` as a duplicate entry — line 153 (`.venv`)
in the existing `.gitignore` already covers it.
**Alternatives:** Add a redundant trailing-slash form.
**Reason:** Plan step 1.2 listed `.venv/` but the existing entry handles
both file-and-dir cases. Avoiding duplication keeps `.gitignore` clean.
**Affects:** none — pre-existing entry suffices.

## 2026-05-17 — Fix `webook_config` / `shared_dataconfig` typos in slack-send sites  [Phase 2.5]
**Decision:** While adding the empty-token guard, also fix two pre-existing typos
at the Slack-send call sites in `FlowChart_dockWidgets.py`:
- `self.shared_data.config.webook_config` → `webhook_config` (missing 'h', 4 occurrences in the score-end + report-call paths)
- `self.shared_dataconfig.webook_config` → `self.shared_data.config.webhook_config` (missing dot)
**Alternatives:** Leave typos in place and only add a no-op guard; defer typo fix to Phase 9/10.
**Reason:** The guard step (2.5) is functionally a no-op without the typo
fix — every Slack-send call site currently raises `AttributeError` on a
mistyped attribute before the guard can even evaluate token-empty. The
fix is a one-line-per-site rename, scoped exactly to the same call sites
the guard touches. Leaving it would have required a second pass through
the same lines in Phase 10.
**Affects:** `glados_pycromanager/GUI/FlowChart_dockWidgets.py`
(`scoreEnd`-reporting block ~L4410, `runslackReportCallAction` ~L4636).

## 2026-05-17 — Slack-send guard uses helper, not inline checks  [Phase 2.5]
**Decision:** Introduce `_slack_send_enabled()` on
`GladosNodzFlowChart_dockWidget` that checks `webhook_config` presence,
non-empty token, and an initialised `slack_client`. Both Slack-send call
sites use this helper.
**Alternatives:** Duplicate inline `if cfg.slack_token: …` at each site.
**Reason:** A single helper centralizes the empty-token policy and the
"set via 'Slack settings…'" hint, so future Slack add-ons (image upload
variants, future reporting nodes) pick up the same behavior.
**Affects:** same file as above.

---

*Append future decisions below this line, newest at the bottom.*
