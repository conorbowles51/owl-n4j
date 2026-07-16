from __future__ import annotations

import re
from typing import Any

from neo4j import READ_ACCESS

from services.agent.json_utils import to_jsonable
from services.neo4j.driver import driver


class UnsafeCypherError(ValueError):
    """Raised when an agent-proposed Cypher query violates read-only rules."""


ALLOWED_KEYWORDS = {
    "ALL",
    "AND",
    "AS",
    "ASC",
    "ASCENDING",
    "BY",
    "CASE",
    "CONTAINS",
    "DESC",
    "DESCENDING",
    "DISTINCT",
    "ELSE",
    "END",
    "ENDS",
    "FALSE",
    "IN",
    "IS",
    "LIMIT",
    "MATCH",
    "NOT",
    "NULL",
    "OPTIONAL",
    "OR",
    "ORDER",
    "RETURN",
    "SKIP",
    "STARTS",
    "THEN",
    "TRUE",
    "UNWIND",
    "WHEN",
    "WHERE",
    "WITH",
    "XOR",
}

DISALLOWED_KEYWORDS = {
    "ALTER",
    "CALL",
    "CREATE",
    "DELETE",
    "DENY",
    "DETACH",
    "DROP",
    "EXECUTE",
    "EXPLAIN",
    "FOREACH",
    "GRANT",
    "INDEX",
    "LOAD",
    "MERGE",
    "PROFILE",
    "REMOVE",
    "REVOKE",
    "SHOW",
    "SET",
    "START",
    "STOP",
    "TERMINATE",
    "UNION",
    "USE",
}

ALLOWED_FUNCTIONS = {
    "ABS",
    "AVG",
    "CEIL",
    "COALESCE",
    "COLLECT",
    "COUNT",
    "DATE",
    "DATETIME",
    "DURATION",
    "ELEMENTID",
    "ENDNODE",
    "EXISTS",
    "FLOOR",
    "HEAD",
    "ID",
    "KEYS",
    "LABELS",
    "LAST",
    "LEFT",
    "LENGTH",
    "LOCALDATETIME",
    "LOCALTIME",
    "LOWER",
    "LTRIM",
    "MAX",
    "MIN",
    "NODES",
    "POINT",
    "PROPERTIES",
    "RANGE",
    "RELATIONSHIPS",
    "REPLACE",
    "RIGHT",
    "ROUND",
    "RTRIM",
    "SIZE",
    "SPLIT",
    "STARTNODE",
    "SUBSTRING",
    "SUM",
    "TAIL",
    "TIME",
    "TOBOOLEAN",
    "TOFLOAT",
    "TOINTEGER",
    "TOSTRING",
    "TRIM",
    "TYPE",
    "UPPER",
}

Token = tuple[str, str]


def _tokenize(query: str) -> list[Token]:
    tokens: list[Token] = []
    quote: str | None = None
    token_start = 0
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
            if char == "\\" and quote in ("'", '"'):
                index += 2
                continue
            if char == quote:
                if next_char == quote:
                    index += 2
                    continue
                token_type = "QUOTED_IDENT" if quote == "`" else "STRING"
                tokens.append((token_type, query[token_start : index + 1]))
                quote = None
            index += 1
            continue

        if char in ("'", '"', "`"):
            quote = char
            token_start = index
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

        if char.isspace():
            index += 1
            continue

        if char == "$":
            end = index + 1
            if end >= len(query) or not (query[end].isalpha() or query[end] == "_"):
                raise UnsafeCypherError("Cypher contains an invalid parameter token")
            end += 1
            while end < len(query) and (query[end].isalnum() or query[end] == "_"):
                end += 1
            tokens.append(("PARAM", query[index:end]))
            index = end
            continue

        if char.isalpha() or char == "_":
            end = index + 1
            while end < len(query) and (query[end].isalnum() or query[end] == "_"):
                end += 1
            tokens.append(("WORD", query[index:end]))
            index = end
            continue

        if char.isdigit():
            end = index + 1
            while end < len(query) and (query[end].isdigit() or query[end] == "."):
                end += 1
            tokens.append(("NUMBER", query[index:end]))
            index = end
            continue

        two_char = char + next_char
        if two_char in {"<=", ">=", "<>", "!=", "=~", "->", "<-", ".."}:
            tokens.append(("OP", two_char))
            index += 2
            continue

        if char in "=<>+-*/%|":
            tokens.append(("OP", char))
            index += 1
            continue

        if char in "()[]{}.,:;":
            tokens.append(("PUNCT", char))
            index += 1
            continue

        raise UnsafeCypherError(f"Cypher contains unsupported character: {char}")

    if quote:
        raise UnsafeCypherError("Cypher contains an unterminated string or identifier")
    if in_block_comment:
        raise UnsafeCypherError("Cypher contains an unterminated block comment")

    return tokens


def _strip_comments(query: str) -> str:
    parts: list[str] = []
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
                parts.append(char)
            else:
                parts.append(" ")
            index += 1
            continue

        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                parts.append("  ")
                index += 2
            else:
                parts.append(" ")
                index += 1
            continue

        if quote:
            parts.append(char)
            if char == "\\" and quote in ("'", '"'):
                if next_char:
                    parts.append(next_char)
                index += 2
                continue
            if char == quote:
                if next_char == quote:
                    parts.append(next_char)
                    index += 2
                    continue
                quote = None
            index += 1
            continue

        if char in ("'", '"', "`"):
            quote = char
            parts.append(char)
            index += 1
            continue

        if char == "/" and next_char == "/":
            in_line_comment = True
            parts.append("  ")
            index += 2
            continue

        if char == "/" and next_char == "*":
            in_block_comment = True
            parts.append("  ")
            index += 2
            continue

        parts.append(char)
        index += 1

    return "".join(parts)


def _has_statement_separator(query: str) -> bool:
    return any(token_type == "PUNCT" and value == ";" for token_type, value in _tokenize(query))


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


def _upper(token: Token) -> str:
    return token[1].upper()


def _is_word(token: Token, value: str | None = None) -> bool:
    if token[0] != "WORD":
        return False
    return value is None or token[1].upper() == value


def _is_identifier(token: Token) -> bool:
    return token[0] in {"WORD", "QUOTED_IDENT"}


def _identifier_name(token: Token) -> str:
    if token[0] == "QUOTED_IDENT":
        return token[1][1:-1].replace("``", "`")
    return token[1]


def _next_non_literal(tokens: list[Token], index: int) -> Token | None:
    cursor = index + 1
    while cursor < len(tokens):
        if tokens[cursor][0] not in {"STRING", "NUMBER"}:
            return tokens[cursor]
        cursor += 1
    return None


def _validate_allowed_tokens(tokens: list[Token]) -> None:
    for index, token in enumerate(tokens):
        token_type, value = token
        if token_type != "WORD":
            continue

        upper = value.upper()
        previous_token = tokens[index - 1] if index else None
        next_token = _next_non_literal(tokens, index)

        if upper in DISALLOWED_KEYWORDS:
            raise UnsafeCypherError(f"Cypher contains disallowed keyword: {upper}")

        if upper in ALLOWED_KEYWORDS:
            continue

        if (
            index + 2 < len(tokens)
            and tokens[index + 1] == ("PUNCT", ".")
            and tokens[index + 2][0] == "WORD"
            and _next_non_literal(tokens, index + 2) == ("PUNCT", "(")
        ):
            raise UnsafeCypherError("Dotted functions and procedures are not allowed")

        is_function_call = (
            next_token == ("PUNCT", "(")
            and previous_token != ("PUNCT", ":")
        )
        if is_function_call and upper not in ALLOWED_FUNCTIONS:
            raise UnsafeCypherError(f"Cypher function is not allowlisted: {value}")


def _find_matching(tokens: list[Token], start: int, close_value: str) -> int | None:
    depth = 0
    open_value = tokens[start][1]
    for index in range(start, len(tokens)):
        token = tokens[index]
        if token == ("PUNCT", open_value):
            depth += 1
        elif token == ("PUNCT", close_value):
            depth -= 1
            if depth == 0:
                return index
    return None


def _range_has_case_param(tokens: list[Token], start: int, end: int) -> bool:
    for index in range(start, max(start, end - 1)):
        if (
            _is_identifier(tokens[index])
            and _identifier_name(tokens[index]).lower() == "case_id"
            and tokens[index + 1] == ("PUNCT", ":")
            and tokens[index + 2] == ("PARAM", "$case_id")
        ):
            return True
    return False


def _pattern_variables_and_scopes(tokens: list[Token]) -> tuple[set[str], set[str], bool]:
    pattern_vars: set[str] = set()
    scoped_vars: set[str] = set()
    has_scope = False

    for index, token in enumerate(tokens):
        if (
            _is_identifier(token)
            and index + 4 < len(tokens)
            and tokens[index + 1] == ("PUNCT", ".")
            and _is_identifier(tokens[index + 2])
            and _identifier_name(tokens[index + 2]).lower() == "case_id"
            and tokens[index + 3] == ("OP", "=")
            and tokens[index + 4] == ("PARAM", "$case_id")
        ):
            scoped_vars.add(_identifier_name(token))
            has_scope = True

        if token not in {("PUNCT", "("), ("PUNCT", "[")}:
            continue

        previous = tokens[index - 1] if index else None
        if (
            token == ("PUNCT", "(")
            and previous
            and previous[0] == "WORD"
            and previous[1].upper() not in ALLOWED_KEYWORDS
        ):
            continue

        close = ")" if token == ("PUNCT", "(") else "]"
        end = _find_matching(tokens, index, close)
        if end is None:
            raise UnsafeCypherError("Cypher contains an unterminated graph pattern")

        if _range_has_case_param(tokens, index + 1, end):
            has_scope = True

        if index + 1 >= end or not _is_identifier(tokens[index + 1]):
            continue

        variable = _identifier_name(tokens[index + 1])
        after_variable = tokens[index + 2] if index + 2 <= end else None
        if after_variable not in {("PUNCT", ")"), ("PUNCT", "]"), ("PUNCT", ":"), ("PUNCT", "{")}:
            continue

        pattern_vars.add(variable)
        if _range_has_case_param(tokens, index + 2, end):
            scoped_vars.add(variable)

    return pattern_vars, scoped_vars, has_scope


def _validate_case_scope(tokens: list[Token]) -> None:
    pattern_vars, scoped_vars, has_scope = _pattern_variables_and_scopes(tokens)
    if not has_scope:
        raise UnsafeCypherError("Cypher must scope a node or relationship with $case_id")

    unscoped = sorted(variable for variable in pattern_vars if variable not in scoped_vars)
    if unscoped:
        raise UnsafeCypherError(
            "Cypher graph pattern variable(s) must be scoped with $case_id: "
            + ", ".join(unscoped)
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
    squashed = " ".join(commentless.split())
    tokens = _tokenize(normalized_query)

    if not tokens:
        raise UnsafeCypherError("Cypher query is required")
    if not (
        _is_word(tokens[0], "MATCH")
        or (
            _is_word(tokens[0], "OPTIONAL")
            and len(tokens) > 1
            and _is_word(tokens[1], "MATCH")
        )
        or _is_word(tokens[0], "WITH")
        or _is_word(tokens[0], "UNWIND")
    ):
        raise UnsafeCypherError("Cypher must begin with MATCH, OPTIONAL MATCH, WITH, or UNWIND")
    if not any(_is_word(token, "RETURN") for token in tokens):
        raise UnsafeCypherError("Cypher must return data")
    if ("PARAM", "$case_id") not in tokens:
        raise UnsafeCypherError("Cypher must include the $case_id parameter")
    for index, token in enumerate(tokens[:-1]):
        if (
            _is_word(token, "NULLS")
            and _is_word(tokens[index + 1])
            and _upper(tokens[index + 1]) in {"FIRST", "LAST"}
        ):
            raise UnsafeCypherError("Neo4j in this app does not support ORDER BY NULLS FIRST/LAST")
    _validate_allowed_tokens(tokens)
    _validate_case_scope(tokens)

    if " NULLS FIRST" in squashed.upper() or " NULLS LAST" in squashed.upper():
        raise UnsafeCypherError("Neo4j in this app does not support ORDER BY NULLS FIRST/LAST")

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
