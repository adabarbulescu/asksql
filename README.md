# asksql

[![CI](https://github.com/adabarbulescu/asksql/actions/workflows/tests.yml/badge.svg)](https://github.com/adabarbulescu/asksql/actions/workflows/tests.yml)

Ask your database questions from a local AI workspace, the terminal, or the TUI.

Local models by default. API models when you want them. SQL shown before it runs.

```bash
asksql ask sqlite://app.db "Which customers spent the most last month?"
```

`asksql` supports SQLite and PostgreSQL, Ollama and OpenAI-compatible APIs, and read-only SQL by default.

## Install

With pipx:

```bash
pipx install asksql
```

For local development:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cd web && npm ci
```

Check first-run setup:

```bash
asksql setup
asksql setup --check-model
```

`asksql setup` is fast and does not contact model providers unless `--check-model` is passed.

Run local checks:

```bash
python scripts/check_versions.py
python -m unittest discover -q
cd web && npm test && npm run build && npm run audit
```

`pyproject.toml` is the canonical release version. The version check also covers the Python package, web manifests,
and both Tauri manifests; release tags must use the matching `vX.Y.Z` form.

For browser e2e tests, install the Playwright browser dependencies once:

```bash
cd web && npm run test:e2e:install
npm run test:e2e
```

## Use

Launch AskSQL Studio, the local-first browser workspace:

```bash
asksql ui
```

Studio opens on `127.0.0.1` and uses your saved connections. Its persistent multi-query workspace restores open
tabs after restart and preserves each query's connection, schema context, question, generated and edited SQL,
execution lifecycle, metadata, and result reference. Studio also includes searchable query history, natural-language
SQL generation, cancellable execution, safe write confirmation, exports, query plans, and a virtualized results grid.
The Saved Queries Library captures deliberate reusable snapshots independently from session drafts and execution
history, with folders, tags, favorites, search, duplication, Save as, and opening into a fresh tab. The
library supports typed `:name` parameters and generates per-tab input forms. Values are passed separately through
native SQLite or PostgreSQL driver binding; parameters marked sensitive are never written to `workspace.db`. The
Business Model editor defines schema-validated entities, metrics, dimensions, default filters, time grains, and
relationships. Questions that name these objects are resolved into an explicit semantic plan and compiled
deterministically for SQLite or PostgreSQL; Studio displays the definitions and joins used to produce the SQL.
Studio can propose a Business Model from schema metadata without reading table rows. The proposal remains an
unpersisted draft until you review it, and readiness checks identify invalid physical references, disconnected
entities, and workflow requirements, then execute bounded read-only checks for nulls, uniqueness, freshness, and
relationship cardinality before adoption. The demo connection provisions a reviewed model so the complete governed
workflow is available immediately.
Studio opens on the Analysis Engine: choose a compatible metric and monthly time dimension, define two comparable
periods, and run a bounded Metric Change Investigation instead of writing a prompt or query. The resulting report
explains the measured change through trend, an optional component metric, and selected dimension contributions.
Revenue Investigation remains available as the revenue-specific compatibility workflow, and findings can launch
scoped follow-up analyses.
Every conclusion links back to an inspectable semantic plan, safely bound SQL, result evidence, timing, and quality
flags. Analysis definitions, immutable run snapshots, progress, reports, and recent runs persist across restarts, and
completed reports export to HTML or PDF. The SQL Workbench remains available from the Analysis toolbar.
Unmatched questions retain free-form generation while receiving the model's business vocabulary as context. The
database stays on your machine; model providers receive schema and the question, never result rows.

No terminal setup is required after launch. Studio can register, validate, rename, and remove SQLite or PostgreSQL
connections, or create a disposable demo profile. Removing a profile never removes its database. The model
selector supports Ollama and OpenAI-compatible providers and checks availability without generating a completion.

Save a real SQLite database once, then use its name everywhere:

```bash
asksql connections add local --url sqlite://app.db
asksql ask local "which customers spent the most?"
asksql --yes run local "select count(*) from customers"
```

Launch `asksql` without arguments to pick a saved connection and open the TUI:

```bash
asksql
```

Manage saved connections:

```bash
asksql connections list
asksql connections show local
asksql connections remove local
```

Connection profiles are stored in `$XDG_CONFIG_HOME/asksql/connections.json` (or
`~/.config/asksql/connections.json`) with private file permissions. Query metadata is kept in a private local
`workspace.db`. Ordinary SQL result rows are not persisted; completed Analysis runs retain their bounded evidence rows,
semantic plans, and compiled SQL locally so reports remain auditable after restart. Set `ASKSQL_CONFIG_DIR` to override
the directory.
Workspace upgrades keep a private backup before adopting an older unversioned database or refusing a future
unsupported workspace version.

PostgreSQL support uses the optional driver:

```bash
pipx install 'asksql[postgres]'
asksql connections add warehouse --url postgresql://user:password@localhost/warehouse
asksql --yes run warehouse "select current_database()"
```

Try the built-in demo:

```bash
asksql --yes ask demo "which customers spent the most?"
```

List local Ollama models:

```bash
asksql models
```

Check the selected model:

```bash
asksql setup --check-model
```

Inspect a database schema:

```bash
asksql schema demo
```

Run read-only SQL directly:

```bash
asksql --yes run demo "select name from customers order by id"
```

Write to an existing database with explicit opt-in:

```bash
asksql run --write sqlite://app.db "update users set active = 0 where last_seen < '2025-01-01'"
```

Write mode accepts one `INSERT`, `UPDATE`, `DELETE`, or DDL statement, shows it before execution, and asks before committing. Add `--yes` before `run` only for deliberate non-interactive use.

Export query results:

```bash
asksql --yes --format csv --output customers.csv run demo "select * from customers"
asksql --yes --format json ask demo "show all customers"
asksql --yes --format markdown ask demo "orders by customer"
```

Limit returned rows:

```bash
asksql --limit 500 ask demo "show customers"
asksql --limit 1000 --format csv run demo "select * from customers"
asksql --limit 1000 tui demo
```

Set a SQLite execution timeout:

```bash
asksql --timeout 10 ask demo "show customers"
asksql --timeout 5 run demo "select * from customers"
```

Open the terminal UI:

```bash
asksql tui demo
```

The TUI keeps schema and AI/manual SQL controls on top, with full-width results below. Use `Tab` / `Shift+Tab` to move between panes, `Enter` to generate SQL or preview a selected table, `Ctrl+Enter` to run reviewed SQL, and `Ctrl+C` to cancel a running query.

Run with local Ollama:

```bash
asksql ask sqlite://app.db "show the newest 10 users"
```

Use a specific Ollama model:

```bash
asksql --model ollama:qwen2.5-coder:7b ask sqlite://app.db "top customers by revenue"
```

Use an OpenAI-compatible API:

```bash
OPENAI_API_KEY=... asksql --model openai:gpt-4.1-mini ask sqlite://app.db "weekly signups"
```

For local models, start Ollama and install the model named by `--model`. For API models, set `OPENAI_API_KEY`
or save the key in Studio's model dialog. `OPENAI_BASE_URL` can point at any OpenAI-compatible endpoint.

Preview SQL without running it:

```bash
asksql --dry-run ask sqlite://app.db "users created yesterday"
```

The older shorthand still works for now:

```bash
asksql demo "which customers spent the most?"
```

## Defaults

- Shows generated SQL before running it.
- Asks before executing generated SQL. Use `--yes` to skip the prompt.
- Shows when results are limited to 200 rows.
- Returns at most 200 rows by default. Use `--limit` to choose 1-10000 returned rows.
- Stops SQLite execution after 30 seconds by default. Use `--timeout` to change that deadline.
- Runs read-only statements by default; manual `run --write` execution requires explicit opt-in.
- Uses Ollama first: `ollama:qwen2.5-coder:7b`.
- Uses `OPENAI_BASE_URL` when set, otherwise `https://api.openai.com/v1`.
- Does not send data rows to the model, only schema.

## Safety Model

- Generated SQL is displayed before execution.
- Generated SQL requires confirmation unless `--yes` is set.
- AI-generated SQL remains read-only; manual writes require `run --write`.
- Queries are limited to 200 rows by default.
- Database execution times out after 30 seconds by default.
- `Ctrl+C` cancels a running TUI query.
- Model calls receive schema only, not data rows.

## Troubleshooting

- `asksql setup` shows config paths, saved connection count, selected model, and the next missing setup step.
- `PostgreSQL support requires...`: install the optional driver with `pipx inject asksql psycopg[binary]` or
  install AskSQL with `asksql[postgres]`.
- `Ollama is reachable, but ... is not installed`: run `ollama pull MODEL` or choose an installed model.
- `OPENAI_API_KEY is not configured`: set the environment variable or save the key in Studio.
- `SQLite database does not exist`: pass an existing file path; AskSQL does not create application databases.
- Config, saved connections, workspace history, and backups live under `$ASKSQL_CONFIG_DIR` when set, otherwise
  `$XDG_CONFIG_HOME/asksql` or `~/.config/asksql`.

## Anti-scope

- No hosted service; Studio is served only on localhost.
- No dashboard builder.
- No migration tool.
- No agentic multi-step database automation.
- No giant database adapter matrix; v0.3 deliberately supports SQLite and PostgreSQL.
