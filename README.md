# asksql

Ask your database questions from the terminal.

Local models by default. API models when you want them. SQL shown before it runs.

```bash
asksql sqlite://app.db "Which customers spent the most last month?"
```

`asksql` starts narrow: SQLite, Ollama, OpenAI-compatible APIs, and read-only SQL.

## Install

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

## Use

Try the built-in demo:

```bash
asksql --yes demo "which customers spent the most?"
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

Open the terminal UI:

```bash
asksql tui demo
```

The TUI keeps schema and AI/manual SQL controls on top, with full-width results below. Use `Tab` / `Shift+Tab` to move between panes, `Enter` to generate SQL or preview a selected table, and `Ctrl+Enter` to run reviewed SQL.

Run with local Ollama:

```bash
asksql sqlite://app.db "show the newest 10 users"
```

Use a specific Ollama model:

```bash
asksql --model ollama:qwen2.5-coder:7b sqlite://app.db "top customers by revenue"
```

Use an OpenAI-compatible API:

```bash
OPENAI_API_KEY=... asksql --model openai:gpt-4.1-mini sqlite://app.db "weekly signups"
```

Preview SQL without running it:

```bash
asksql --dry-run sqlite://app.db "users created yesterday"
```

## Defaults

- Shows generated SQL before running it.
- Asks before executing generated SQL. Use `--yes` to skip the prompt.
- Shows when results are limited to 200 rows.
- Runs only read-only statements.
- Uses Ollama first: `ollama:qwen2.5-coder:7b`.
- Uses `OPENAI_BASE_URL` when set, otherwise `https://api.openai.com/v1`.
- Does not send data rows to the model, only schema.

## Anti-scope

- No hosted service.
- No dashboard builder.
- No migration tool.
- No agentic multi-step database automation.
- No giant database adapter matrix.
