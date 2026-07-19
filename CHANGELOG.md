# Changelog

All notable changes to this project are documented in this file.

## [0.3.0] - 2026-07-19

- Added AskSQL Studio query history, pinning, search, restore, and local private workspace storage.
- Added asynchronous execution, cancellation, streaming generation state, CSV/JSON/Markdown export, and virtualized results.
- Added token-bound, expiring, one-time write confirmation with a persistent local audit trail.
- Added schema search and AI context selection, indexes, foreign keys, row estimates, views, triggers, and query plans.
- Added a database adapter boundary and PostgreSQL support for Studio, CLI, and TUI.
- Added OS-keyring storage for provider secrets, Vue component tests, accessibility improvements, and Tauri desktop workflows.

The desktop workflow requires private Tauri signing credentials. Source, Python packages, and unsigned local desktop
builds do not require those credentials.

## [0.2.0] - 2026-07-19

### Added

- Explicit `ask`, `run`, `tui`, `schema`, and `models` CLI commands.
- SQLite query deadlines with fractional `--timeout` values.
- Query cancellation in the TUI with `Ctrl+C`.
- A UI-independent `QueryService` and explicit execution status models.
- CSV, JSON, and Markdown result export.
- Configurable result limits and schema exploration.

### Changed

- Generated SQL is shown for review before execution.
- The TUI prevents concurrent runs and ignores stale worker results.
- The legacy `asksql DATABASE QUESTION` shorthand remains supported.

### Safety

- Only read-only SQL is accepted by default.
- SQLite timeout and cancellation outcomes are classified deterministically.
- Model calls receive database schema, not table data.
- CLI failures use stable exit codes for refusal, timeout, cancellation, and general errors.

[0.3.0]: https://github.com/adabarbulescu/asksql/releases/tag/v0.3.0
[0.2.0]: https://github.com/adabarbulescu/asksql/releases/tag/v0.2.0
