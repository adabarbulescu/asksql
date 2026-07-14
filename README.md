# asksql

Ask your database questions from the terminal.

Local models by default. API models when you want them. SQL shown before it runs.

```bash
asksql sqlite://app.db "Which customers spent the most last month?"
```

`asksql` starts narrow: SQLite, Ollama, OpenAI-compatible APIs, and read-only SQL.

## Install

```bash
pip install -e .
```

## Use

Try the built-in demo:

```bash
asksql demo "which customers spent the most?"
```

Run with local Ollama:

```bash
asksql sqlite://app.db "show the newest 10 users"
```

Use a specific Ollama model:

```bash
asksql --model ollama:qwen2.5-coder sqlite://app.db "top customers by revenue"
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
- Runs only read-only statements.
- Uses Ollama first: `ollama:qwen2.5-coder`.
- Uses `OPENAI_BASE_URL` when set, otherwise `https://api.openai.com/v1`.
- Does not send data rows to the model, only schema.

## Anti-scope

- No hosted service.
- No dashboard builder.
- No migration tool.
- No agentic multi-step database automation.
- No giant database adapter matrix.
