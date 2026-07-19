# asksql

[![CI](https://github.com/adabarbulescu/asksql/actions/workflows/tests.yml/badge.svg)](https://github.com/adabarbulescu/asksql/actions/workflows/tests.yml)

Ask your database questions from the terminal.

Local models by default. API models when you want them. SQL shown before it runs.

```bash
asksql ask sqlite://app.db "Which customers spent the most last month?"
```

`asksql` starts narrow: SQLite, Ollama, OpenAI-compatible APIs, and read-only SQL.

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
- Runs only read-only statements.
- Uses Ollama first: `ollama:qwen2.5-coder:7b`.
- Uses `OPENAI_BASE_URL` when set, otherwise `https://api.openai.com/v1`.
- Does not send data rows to the model, only schema.

## Safety Model

- Generated SQL is displayed before execution.
- Generated SQL requires confirmation unless `--yes` is set.
- Only read-only SQL is allowed.
- Queries are limited to 200 rows by default.
- SQLite execution times out after 30 seconds by default.
- `Ctrl+C` cancels a running TUI query.
- Model calls receive schema only, not data rows.

## Anti-scope

- No hosted service.
- No dashboard builder.
- No migration tool.
- No agentic multi-step database automation.
- No giant database adapter matrix.
