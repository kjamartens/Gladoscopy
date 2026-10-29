# Security policy

## Supported versions

Glados-PycroManager is a research/lab tool, not a production service. The only
supported version is the current `main` branch; there are no release tags yet.
Older revisions do not receive security fixes.

## Reporting a vulnerability

If you discover a vulnerability that should not be discussed in public
(credential leak, code execution through a recipe or plugin, etc.):

1. **Do not open a public GitHub issue.**
2. Email the maintainer at **koenjamartens@gmail.com** with:
   - A short description of the issue.
   - Steps to reproduce (a minimal recipe JSON, plugin file, or config
     suffices).
   - Affected version (`git rev-parse HEAD` is fine).
   - Whether you have already shared the finding elsewhere.
3. You should receive an acknowledgement within 7 days. If you do not, open
   a public issue titled "Security report follow-up" without disclosing the
   underlying vulnerability; that signals the report was missed.

For non-sensitive bug reports, use the regular GitHub issue tracker.

## Known historical exposures

| Date       | What                                              | Mitigation                                                                 |
| ---------- | ------------------------------------------------- | -------------------------------------------------------------------------- |
| pre-2026-05 | Slack bot token + signing secret hard-coded in `WebhookConfig` defaults (committed to git). | Token confirmed stale/expired by the maintainer; defaults removed from the source in commit `3a63bb4`. Runtime values are now entered in the **Slack settings…** dialog and stored in per-user AppData. **The credentials remain in git history.** |

## Threat-model notes (informational)

- **Recipe JSON is not a trust boundary.** Node functions are dispatched
  through a registry rather than `eval`, but a recipe can still run Python:
  the *Run advanced script* node executes its lines, and Advanced-mode
  parameters are evaluated as Python expressions. Treat any recipe JSON as
  code: only load files from people you would trust with a `.py` file.
- **Plugin discovery (`Analysis_Measurements`, `Real_Time_Analysis`,
  `CustomFunctions`)** imports any `.py` dropped into the user's AppData
  folder. Anything that can write to that folder can execute code on the
  next start. This is the design intent (it is how nodes are added) but is
  worth flagging.
- **Stored credentials.** `glados_state.json` in the per-user AppData
  directory stores the Slack token in plaintext. This matches typical
  desktop-app behaviour and relies on OS-level user isolation; it is not
  encrypted at rest.
