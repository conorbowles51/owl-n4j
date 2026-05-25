from __future__ import annotations

import re
from typing import Any

from neo4j import READ_ACCESS

from services.agent.json_utils import to_jsonable
from services.neo4j.driver import driver


class UnsafeCypherError(ValueError):
    """Raised when an agent-proposed Cypher query violates read-only rules."""


DENIED_KEYWORDS = {
    "ALTER",
    "CALL",
    "CREATE",
    "DELETE",
    "DENY",
    "DETACH",
    "DROP",
    "FOREACH",
    "GRANT",
    "LOAD",
    "MERGE",
    "REMOVE",
    "REVOKE",
    "SET",
    "START",
    "STOP",
    "TERMINATE",
    "USE",
}


def _strip_comments(query: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", " ", query, flags=re.DOTALL)
    return re.sub(r"//.*?$", " ", without_block, flags=re.MULTILINE)


def _has_statement_separator(query: str) -> bool:
    quote: str | None = None
    in_line_comment = False
    in_block_comment = False
    index = 0
    while index < len(query):
        char = query[index]
        next_char = query[index + 1] if index + 1 < len(query) else ""

        if in_line_comment:
            if char in "\r\n":
                in_line_comment = False
            index += 1
            continue

        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                index += 2
            else:
                index += 1
            continue

        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                if next_char == quote:
                    index += 2
                    continue
                quote = None
            index += 1
            continue

        if char in ("'", '"'):
            quote = char
            index += 1
            continue

        if char == "/" and next_char == "/":
            in_line_comment = True
            index += 2
            continue

        if char == "/" and next_char == "*":
            in_block_comment = True
            index += 2
            continue

        if char == ";":
            return True

        index += 1

    return False


def _single_statement(query: str) -> str:
    stripped = query.strip()
    if not stripped:
        raise UnsafeCypherError("Cypher query is required")
    without_trailing = stripped[:-1].strip() if stripped.endswith(";") else stripped
    if _has_statement_separator(without_trailing):
        raise UnsafeCypherError("Only a single read-only Cypher statement is allowed")
    return without_trailing


def _enforce_limit(query: str, limit: int) -> str:
    safe_limit = max(1, min(int(limit or 100), 200))
    limit_pattern = re.compile(r"\bLIMIT\s+(\$[A-Za-z_][A-Za-z0-9_]*|\d+)\b", flags=re.IGNORECASE)
    match = list(limit_pattern.finditer(query))
    if not match:
        return f"{query}\nLIMIT {safe_limit}"

    last = match[-1]
    value = last.group(1)
    if value.isdigit() and int(value) <= safe_limit:
        return query
    return query[: last.start(1)] + str(safe_limit) + query[last.end(1) :]


def _has_real_case_scope(query: str) -> bool:
    return bool(
        re.search(r"\b[A-Za-z_][A-Za-z0-9_]*\.case_id\s*=\s*\$case_id\b", query, flags=re.IGNORECASE)
        or re.search(r"\{\s*[^}]*case_id\s*:\s*\$case_id\b", query, flags=re.IGNORECASE)
    )


def repair_common_cypher(query: str) -> str:
    """Repair small Neo4j syntax slips the agent commonly makes."""
    repaired = re.sub(r"\s+NULLS\s+(FIRST|LAST)\b", "", query, flags=re.IGNORECASE)
    repaired = re.sub(
        r"\bLIMIT\s+\$[A-Za-z_][A-Za-z0-9_]*\b",
        "",
        repaired,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", repaired).strip()


def validate_readonly_cypher(query: str, *, limit: int = 100) -> str:
    normalized_query = _single_statement(query)
    commentless = _strip_comments(normalized_query)
    squashed = re.sub(r"\s+", " ", commentless).strip()
    upper = squashed.upper()

    if not upper.startswith(("MATCH ", "OPTIONAL MATCH ", "WITH ", "UNWIND ")):
        raise UnsafeCypherError("Cypher must begin with MATCH, OPTIONAL MATCH, WITH, or UNWIND")
    if " RETURN " not in f" {upper} ":
        raise UnsafeCypherError("Cypher must return data")
    if "$CASE_ID" not in upper:
        raise UnsafeCypherError("Cypher must include the $case_id parameter")
    if not _has_real_case_scope(squashed):
        raise UnsafeCypherError("Cypher must scope a node or relationship with .case_id = $case_id")
    if re.search(r"\bNULLS\s+(FIRST|LAST)\b", upper):
        raise UnsafeCypherError("Neo4j in this app does not support ORDER BY NULLS FIRST/LAST")

    found = sorted(keyword for keyword in DENIED_KEYWORDS if re.search(rf"\b{keyword}\b", upper))
    if found:
        raise UnsafeCypherError(f"Cypher contains disallowed keyword(s): {', '.join(found)}")

    return _enforce_limit(normalized_query, limit)


def run_readonly_cypher(
    query: str,
    *,
    case_id: str,
    params: dict[str, Any] | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    safe_query = validate_readonly_cypher(query, limit=limit)
    safe_params = dict(params or {})
    safe_params["case_id"] = case_id

    def work(tx):
        result = tx.run(safe_query, safe_params)
        return [to_jsonable(dict(record)) for record in result]

    with driver.session(default_access_mode=READ_ACCESS) as session:
        return session.execute_read(work)
