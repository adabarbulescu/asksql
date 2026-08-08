from __future__ import annotations

import sqlite3
import tempfile
from datetime import date
from pathlib import Path


def _month_start(offset: int) -> str:
    today = date.today()
    month_index = today.year * 12 + today.month - 1 + offset
    return date(month_index // 12, month_index % 12 + 1, 1).isoformat()


def create_demo_db(path: Path | None = None) -> str:
    if path is None:
        with tempfile.NamedTemporaryFile(prefix="asksql-demo-", suffix=".db", delete=False) as file:
            path = Path(file.name)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
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
                customer_id integer not null references customers(id),
                total real not null,
                status text not null,
                channel text not null,
                created_at text not null
            );
            """
        )
        conn.executemany(
            "insert into customers values (?, ?, ?, ?)",
            [
                (1, "Ada", "ada@example.com", _month_start(-1)),
                (2, "Max", "max@example.com", _month_start(-1)),
                (3, "Lin", "lin@example.com", _month_start(0)),
            ],
        )
        conn.executemany(
            "insert into orders values (?, ?, ?, ?, ?, ?)",
            [
                (1, 1, 120.50, "completed", "web", _month_start(-2)),
                (2, 1, 40.00, "completed", "store", _month_start(-2)),
                (3, 2, 75.25, "completed", "partner", _month_start(-2)),
                (4, 3, 55.00, "refunded", "web", _month_start(-2)),
                (5, 1, 170.00, "completed", "web", _month_start(-1)),
                (6, 2, 95.50, "completed", "store", _month_start(-1)),
                (7, 3, 82.25, "completed", "partner", _month_start(-1)),
                (8, 2, 30.00, "refunded", "web", _month_start(-1)),
                (9, 1, 220.00, "completed", "web", _month_start(0)),
                (10, 2, 125.00, "completed", "store", _month_start(0)),
                (11, 3, 110.75, "completed", "partner", _month_start(0)),
                (12, 3, 45.00, "completed", "web", _month_start(0)),
            ],
        )
    path.chmod(0o600)
    return f"sqlite://{path}"
