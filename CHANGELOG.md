# Changelog

All notable changes to this project are documented in this file.

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

- Only read-only SQL is accepted.
- SQLite timeout and cancellation outcomes are classified deterministically.
- Model calls receive database schema, not table data.
- CLI failures use stable exit codes for refusal, timeout, cancellation, and general errors.

[0.2.0]: https://github.com/adabarbulescu/asksql/releases/tag/v0.2.0
