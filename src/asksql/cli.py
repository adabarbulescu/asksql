from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ask your database questions from the terminal.")
    parser.add_argument("--model", default="ollama:qwen2.5-coder", help="ollama:name or openai:name")
    parser.add_argument("db_url", nargs="?", help="database URL, starting with sqlite://...")
    parser.add_argument("question", nargs="?", help="natural-language question")
    args = parser.parse_args(argv)

    if not args.db_url or not args.question:
        parser.print_help()
        return 0

    print(f"model: {args.model}")
    print(f"db: {args.db_url}")
    print(f"question: {args.question}")
    print("\nTODO: introspect schema, ask model, show SQL, then run read-only query.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
