# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

- Added end-to-end Self-Correction / Auto-Fix loop (`--auto-fix` and `--retries 1-5`) for text-to-SQL generation.
- Added multi-turn database error conditioning for both Ollama and OpenAI-compatible models (`repair_sql`).
- Added `AutoFixAttempt` telemetry and attempt tracking to `QueryExecution` and Studio API.
- Integrated auto-fix in AskSQL Studio execution flows with real-time editor SQL updates upon repair.
- Preserved strict read-only safety invariants and clean stdout isolation for piped export formats.

## [0.8.0] - 2026-08-02

- Added a persistent Analysis Engine with reusable declarative workflows, bounded semantic query plans, immutable
  definition and Business Model snapshots, explicit lifecycle states, cancellation, restart recovery, and workspace
  migration v5 to v6.
- Added the production Revenue Investigation workflow with period comparison, monthly trend, metric decomposition,
  dimensional contribution analysis, contextual follow-ups, and a strict 30-query execution budget.
- Added deterministic findings and confidence based on evidence coverage and data completeness. Every claim retains
  its semantic plan, compiled SQL, bound parameters, result rows, timing, and data-quality flags.
- Replaced Studio's default query surface with “What do you want to understand?”, including workflow configuration,
  live progress, reusable reports, SVG charts, evidence inspection, recent analysis recovery, and HTML/PDF export.
- Added SQLite, conditional PostgreSQL, migration, API, lifecycle, report export, store, chart, and Analysis workspace
  tests. The SQL Workbench remains available as a first-class surface.

## [0.7.0] - 2026-08-02

- Added a persistent Semantic Layer with schema-validated entities, business metrics, dimensions, default filters,
  time grains, and cardinality-aware relationships.
- Added deterministic SQLite and PostgreSQL compilers that translate semantic query plans into auditable SQL and
  pass filter values through native driver binding.
- Added semantic question resolution before free-form generation, business vocabulary context for the LLM fallback,
  explicit generation modes, compilation traces, and protection against executing edited semantic SQL with a stale plan.
- Added the Business Model editor in Studio, semantic-model selection per connection, SQL compilation previews,
  persistent per-document plans, and workspace migration v4 to v5.
- Added compiler, resolver, migration, API, store, UI, SQLite execution, and conditional PostgreSQL integration tests.

## [0.6.0] - 2026-08-02

- Added typed parameters for saved queries, with native SQLite/PostgreSQL binding, server and client validation,
  per-tab values, generated Studio forms, and parameter-aware exports.
- Added text, integer, decimal, boolean, date, and datetime contracts; sensitive values are accepted for execution
  but excluded from persistent workspace state.
- Migrated workspace storage from v3 to v4 while preserving parameter definitions through duplication and Save as.

- Added a Saved Queries Library with explicit Save/Save as workflows, folders, normalized tags, favorites, full-text
  search, duplication, and opening reusable queries in new workspace tabs.
- Migrated private workspace storage from v2 to v3 with a pre-migration backup and a dedicated `saved_queries`
  aggregate, kept separate from mutable query documents and execution history.
- Added a persistent multi-query Studio workspace with reopenable, renameable tabs and per-document connection,
  schema context, natural-language question, generated SQL, edited SQL, execution metadata, and result references.
- Added explicit draft, generated, running, completed, failed, and cancelled document lifecycles, including recovery
  of an interrupted running query after Studio restarts.
>>>>>>> origin/main

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
[0.6.0]: https://github.com/adabarbulescu/asksql/releases/tag/v0.6.0
[0.7.0]: https://github.com/adabarbulescu/asksql/releases/tag/v0.7.0
[0.8.0]: https://github.com/adabarbulescu/asksql/releases/tag/v0.8.0
[0.2.0]: https://github.com/adabarbulescu/asksql/releases/tag/v0.2.0
