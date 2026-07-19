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
```

## Use

Launch AskSQL Studio, the local-first browser workspace:

```bash
asksql ui
```

Studio opens on `127.0.0.1` and uses your saved connections. It includes connection management, persistent query
history, schema search and context selection, natural-language SQL generation, editable SQL review, cancellable
execution, safe write confirmation, exports, query plans, and a virtualized results grid. The
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
`workspace.db`; result rows are not persisted. Set `ASKSQL_CONFIG_DIR` to override the directory.

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

## Anti-scope

- No hosted service; Studio is served only on localhost.
- No dashboard builder.
- No migration tool.
- No agentic multi-step database automation.
- No giant database adapter matrix; v0.3 deliberately supports SQLite and PostgreSQL.
