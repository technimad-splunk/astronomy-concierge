# Agent Journal

A running record of meaningful actions taken by agents in this project: what was done, why, and what decisions or trade-offs were made.

**Format for new entries:**

```
## YYYY-MM-DD — <Short title>

**What:** <1-2 sentences describing what was done>

**Why:** <rationale — why this approach over alternatives>

**Decisions / trade-offs:**
- <decision 1>
- <decision 2>

**Effect on codebase / UX:** <what changed and for whom>
```

Entries are append-only. Never delete or rewrite past entries.

---

## 2026-06-16 — Project governance bootstrap

**What:** Initialized the project with a full governance layer: five `alwaysApply` Cursor rules, `AGENTS.md`, `README.md` skeleton, `CHANGELOG.md`, this journal, `.gitignore`, and a git repository with an initial commit.

**Why:** Starting with explicit, machine-enforced conventions prevents drift across agent sessions. Encoding rules in `.cursor/rules/` makes them automatically active without requiring agents to be reminded each session. Scaffolding the artifacts (README, changelog, journal) upfront ensures they exist and have a defined structure before any real code is written.

**Decisions / trade-offs:**
- Chose `alwaysApply: true` for all five rules so they fire regardless of which files are open. A file-glob approach would be less intrusive but risks the rules being silently skipped.
- Split hygiene concerns into five separate rule files (one concern per file) rather than one monolithic rule, keeping each under ~50 lines and easy to update independently.
- Kept `automate-verify.mdc` as a principle only (no scripts or CI yet) since the project's language and toolchain are not yet defined. The rule explicitly asks agents to grow automation incrementally.
- Added an agent journal (this file) in addition to the changelog. The changelog is user-facing and captures intent/impact; the journal is agent/developer-facing and captures decisions and trade-offs.

**Effect on codebase / UX:** No production code yet. All files are governance scaffolding. Future agents will automatically maintain the README, changelog, and this journal.
