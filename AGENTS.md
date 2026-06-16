# Agent Governance

This file is the entry point for any agent (or human) wanting to understand how this project is run. Five hygiene principles apply to all work done here. Each is enforced by an `alwaysApply` Cursor rule.

---

## Principles and rules

| # | Principle | Rule file | Artifact |
|---|---|---|---|
| 1 | Keep an updated README for humans | [`.cursor/rules/readme.mdc`](.cursor/rules/readme.mdc) | [`README.md`](README.md) |
| 2 | Maintain a changelog (intent, rationale, impact) | [`.cursor/rules/changelog.mdc`](.cursor/rules/changelog.mdc) | [`CHANGELOG.md`](CHANGELOG.md) |
| 3 | Git hygiene: disciplined commits, branches, merges | [`.cursor/rules/git-hygiene.mdc`](.cursor/rules/git-hygiene.mdc) | git history |
| 4 | Capture agent actions and decisions | [`.cursor/rules/agent-journal.mdc`](.cursor/rules/agent-journal.mdc) | [`docs/agent-journal.md`](docs/agent-journal.md) |
| 5 | Automate and verify before declaring work done | [`.cursor/rules/automate-verify.mdc`](.cursor/rules/automate-verify.mdc) | `scripts/` (as it grows) |

---

## Quick summary for agents

- **Before starting**: read the relevant rule file(s) for the work you are about to do.
- **While working**: follow the branching and commit conventions in `git-hygiene.mdc`.
- **After finishing**: update `README.md` if user-facing behaviour changed, add a `CHANGELOG.md` entry, and append an entry to `docs/agent-journal.md`.
- **Never**: skip verification, force-push to `main`, hardcode secrets, or leave the project in a broken state.
