# Security policy

## Supported versions

Glados-PycroManager is a research/lab tool, not a production service. The only
supported version is the current `main` branch (and the most recent release
tag). Older revisions do not receive security backports.

## Reporting a vulnerability

If you discover a vulnerability that should not be discussed in public
(credential leak, RCE in node-graph execution, plugin-loader escape, etc.):

1. **Do not open a public GitHub issue.**
2. Email the maintainer at **kjamartens@proton.me** with:
   - A short description of the issue.
   - Steps to reproduce (a minimal recipe JSON, plugin file, or config
     suffices).
   - Affected version (`git rev-parse HEAD` is fine).
   - Whether you have already shared the finding elsewhere.
3. You should receive an acknowledgement within 7 days. If you do not, open
   a public issue titled "Security report follow-up" without disclosing the
   underlying vulnerability — that signals the report was missed.

For non-sensitive bug reports, use the regular GitHub issue tracker.

## Known historical exposures

| Date       | What                                              | Mitigation                                                                 |
| ---------- | ------------------------------------------------- | -------------------------------------------------------------------------- |
| pre-2026-05 | Slack bot token + signing secret hard-coded in `WebhookConfig` defaults (committed to git). | Token confirmed stale/expired by maintainer; defaults removed from source in commit `3a63bb4` (Phase 2.1 of `claude_project.md`). Runtime values now entered via the **Slack settings…** dialog and persisted to per-user AppData JSON. **The credentials remain in git history**; rewriting history requires coordination — tracked under `HYG-3` in `claude_project.md`. |

## Threat-model notes (informational)

- **Recipe JSON is not a trust boundary.** The autonomous-microscopy engine
  still uses `eval()` on strings derived from recipe content (see Phase 9
  of `claude_project.md`). Treat any recipe JSON as code: only load files
  authored by people you trust on the same level you trust a `.py` file.
- **Plugin discovery (`Analysis_Measurements`, `Real_Time_Analysis`,
  `CustomFunctions`)** auto-imports any `.py` dropped into the user's
  AppData folder. Anything that can write to that folder can execute code
  on next start — this matches the design intent (it is how nodes are
  added) but is worth flagging.
- **Stored credentials.** `glados_state.json` in the per-user AppData
  directory stores the Slack token in plaintext. This matches typical
  desktop-app behavior and relies on OS-level user isolation; it is not
  encrypted at rest.
