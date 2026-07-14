from __future__ import annotations

import re


WRITE_RE = re.compile(r"\b(insert|update|delete|drop|alter|create|truncate|replace|merge|grant|revoke|vacuum|attach)\b", re.I)


def is_read_only(sql: str) -> bool:
    sql = sql.strip().rstrip(";").strip()
    if not sql or ";" in sql:
        return False
    if WRITE_RE.search(sql):
        return False
    return bool(re.match(r"^(select|with|pragma|explain)\b", sql, re.I))
