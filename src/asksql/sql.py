from __future__ import annotations

import re


def clean_sql(text: str) -> str:
    sql = text.strip()
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", sql, re.I | re.S)
    if fenced:
        sql = fenced.group(1).strip()
    return pretty_sql(sql)


def pretty_sql(sql: str) -> str:
    if "\n" in sql:
        return sql
    return re.sub(r"\s+(from|join|where|group by|order by|limit)\b", r"\n\1", sql, flags=re.I)
