# .claude/agents — subagent definitions

This directory hosts project-local subagents for Claude Code. The contents
will be authored in **Phase 16** of `claude_project.md`. Until then this
README is a placeholder so the directory exists in git.

Planned agents:

- `code-reviewer.md` — reviews diffs on `claude_optimization` against the
  project rules (no bare `except`, no `eval` of user data, no `print` in
  library code, Nodz folder off-limits).
- `test-author.md` — drafts pytest cases for a changed module; positive +
  negative path coverage; mocks via `tests/fakes/`.
- `node-doctor.md` — validates a new autonomous-microscopy node has a
  well-formed `__function_metadata__`, declared kwargs, and is loadable
  through the registry.

When a `.md` is added here it becomes selectable as
`subagent_type=<name>` in the Agent tool.
