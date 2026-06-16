# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- **Intent:** Establish project governance so that all future agents and contributors follow consistent hygiene practices from day one.
  **Rationale:** An empty repository with no conventions leads to inconsistent behaviour across agent sessions, missing context, and hard-to-maintain history. Encoding conventions as `alwaysApply` Cursor rules makes them automatic rather than aspirational.
  **Impact (codebase):** Added `.cursor/rules/` with five focused rules (`readme`, `changelog`, `git-hygiene`, `agent-journal`, `automate-verify`), `AGENTS.md` as an agent/human index, `README.md` skeleton, `docs/agent-journal.md` running journal, and `.gitignore`. No production code yet.
  **Impact (user experience):** Future agents will automatically maintain the README, changelog, git discipline, and decision journal without requiring explicit per-session reminders.

---

<!-- When cutting a release, move items from [Unreleased] to a versioned block:

## [0.1.0] - YYYY-MM-DD

### Added
...

[Unreleased]: https://github.com/your-org/local-agent-galileo/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/your-org/local-agent-galileo/releases/tag/v0.1.0
-->
