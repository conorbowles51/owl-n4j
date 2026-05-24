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


def _single_statement(query: str) -> str:
    stripped = query.strip()
    if not stripped:
        raise UnsafeCypherError("Cypher query is required")
    without_trailing = stripped[:-1].strip() if stripped.endswith(";") else stripped
    if ";" in without_trailing:
        raise UnsafeCypherError("Only a single read-only Cypher statement is allowed")
    return without_trailing


def _enforce_limit(query: str, limit: int) -> str:
    safe_limit = max(1, min(int(limit or 100), 200))
    limit_pattern = re.compile(r"\bLIMIT\s+(\d+)\b", flags=re.IGNORECASE)
    match = list(limit_pattern.finditer(query))
    if not match:
        return f"{query}\nLIMIT {safe_limit}"

    last = match[-1]
    current = int(last.group(1))
    if current <= safe_limit:
        return query
    return query[: last.start(1)] + str(safe_limit) + query[last.end(1) :]


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
