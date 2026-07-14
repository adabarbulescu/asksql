from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path


def create_demo_db() -> str:
    path = Path(tempfile.gettempdir()) / "asksql-demo.db"
    path.unlink(missing_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            drop table if exists customers;
            drop table if exists orders;

            create table customers(
                id integer primary key,
                name text not null,
                email text not null,
                created_at text not null
            );

            create table orders(
                id integer primary key,
                customer_id integer not null,
                total real not null,
                created_at text not null
            );
            """
        )
        conn.executemany(
            "insert into customers values (?, ?, ?, ?)",
            [
                (1, "Ada", "ada@example.com", "2026-07-01"),
                (2, "Max", "max@example.com", "2026-07-02"),
                (3, "Lin", "lin@example.com", "2026-07-03"),
            ],
        )
        conn.executemany(
            "insert into orders values (?, ?, ?, ?)",
            [
                (1, 1, 120.50, "2026-07-10"),
                (2, 1, 40.00, "2026-07-11"),
                (3, 2, 75.25, "2026-07-12"),
            ],
        )
    return f"sqlite://{path}"
