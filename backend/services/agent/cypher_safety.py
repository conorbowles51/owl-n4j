"""Read-only agent Cypher with a deliberately bounded case-scope grammar.

Supported: MATCH/OPTIONAL MATCH, every node and relationship scoped by its
case_id property or mandatory WHERE equality, previously scoped bindings,
single-hop joins, and built-in scalar/aggregate RETURN expressions. Scope
must hold in every OR/XOR branch. Each MATCH is checked before the next clause.

Not supported: WITH/UNWIND aliases, UNION, subqueries, variable-length paths,
quoted identifiers, list/map expressions, custom functions, or scope inherited
only from a relationship. Rewrite these as simpler explicitly scoped queries;
this validator does not claim to prove arbitrary Cypher safe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
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


@dataclass(frozen=True)
class _Token:
    value: str
    start: int
    end: int
    kind: str = "symbol"


def _tokens(query: str) -> list[_Token]:
    """Lex only the small supported Cypher subset; literals cannot prove scope."""
    result: list[_Token] = []
    index = 0
    while index < len(query):
        start = index
        char = query[index]
        if char.isspace():
            if char not in " \t\r\n":
                raise UnsafeCypherError("Use ordinary spaces or line breaks in Cypher")
            index += 1
            continue
        if query.startswith("//", index):
            newline = re.search(r"[\r\n]", query[index + 2:])
            end = len(query) if newline is None else index + 2 + newline.start()
            if any(value.isspace() and value not in " \t" for value in query[index + 2:end]):
                raise UnsafeCypherError("Use ordinary line breaks in Cypher comments")
            index = end
            continue
        if query.startswith("/*", index):
            end = query.find("*/", index + 2)
            if end < 0:
                raise UnsafeCypherError("Unterminated Cypher comment")
            if "/*" in query[index + 2:end]:
                raise UnsafeCypherError("Nested Cypher comments are not supported")
            index = end + 2
            continue
        if char in ("'", '"'):
            quote = char
            index += 1
            while index < len(query):
                if query[index] == "\\":
                    index += 2
                elif query[index] == quote:
                    if index + 1 < len(query) and query[index + 1] == quote:
                        index += 2
                    else:
                        index += 1
                        break
                else:
                    index += 1
            else:
                raise UnsafeCypherError("Unterminated Cypher string")
            result.append(_Token("<literal>", start, index, "literal"))
            continue
        match = re.match(r"\$?[A-Za-z_][A-Za-z0-9_]*|[0-9]+", query[index:])
        if match:
            value = match.group()
            kind = "parameter" if value.startswith("$") else "number" if value.isdigit() else "word"
            index += len(value)
            result.append(_Token(value, start, index, kind))
            continue
        if char not in "(){}[]:,.=<>!+-*/%|&^":
            raise UnsafeCypherError("Use simple unquoted Cypher identifiers and explicit case-scoped MATCH clauses")
        index += 1
        result.append(_Token(char, start, index))
    return result


def _enforce_limit(query: str, limit: int) -> str:
    safe_limit = max(1, min(int(limit or 100), 200))
    tokens = _tokens(query)
    matches = [
        index for index, token in enumerate(tokens)
        if token.kind == "word" and token.value.upper() == "LIMIT"
    ]
    if not matches:
        return f"{query}\nLIMIT {safe_limit}"
    index = matches[-1]
    if index + 2 != len(tokens) or tokens[index + 1].kind not in {"number", "parameter"}:
        raise UnsafeCypherError("Use a final numeric LIMIT without an expression")
    value = tokens[index + 1]
    if value.kind == "number" and int(value.value) <= safe_limit:
        return query
    return query[:value.start] + str(safe_limit) + query[value.end:]


def _property_map(tokens: list[_Token], index: int) -> tuple[bool, int]:
    """Only scalar map values are supported; a nested fake case_id is not scope."""
    scoped = False
    keys: set[str] = set()
    if index >= len(tokens) or tokens[index].value != "{":
        return scoped, index
    index += 1
    while index < len(tokens) and tokens[index].value != "}":
        if (
            index + 2 >= len(tokens)
            or tokens[index].kind != "word"
            or tokens[index + 1].value != ":"
        ):
            raise UnsafeCypherError("Use scalar properties in MATCH patterns")
        key, value = tokens[index], tokens[index + 2]
        if key.value in keys:
            raise UnsafeCypherError("Duplicate MATCH property keys are not supported")
        keys.add(key.value)
        if value.kind not in {"parameter", "literal", "number", "word"}:
            raise UnsafeCypherError("Use scalar properties in MATCH patterns")
        scoped |= key.value == "case_id" and value.value == "$case_id"
        index += 3
        if index < len(tokens) and tokens[index].value == ",":
            index += 1
        elif index >= len(tokens) or tokens[index].value != "}":
            raise UnsafeCypherError("Use scalar properties in MATCH patterns")
    if index >= len(tokens):
        raise UnsafeCypherError("Unclosed MATCH property map")
    return scoped, index + 1


def _match_bindings(tokens: list[_Token]) -> list[tuple[str, str | None, bool]]:
    """Accept named/anonymous single-hop paths, without expressions or subqueries."""
    result: list[tuple[str, str | None, bool]] = []
    index = 0
    while index < len(tokens):
        if (
            index + 1 < len(tokens)
            and tokens[index].kind == "word"
            and tokens[index + 1].value == "="
        ):
            index += 2  # A path variable: its nodes still need individual scope.
        while True:
            if index >= len(tokens) or tokens[index].value != "(":
                raise UnsafeCypherError("Use explicit MATCH node patterns; path expressions are not supported")
            index += 1
            name = None
            if index < len(tokens) and tokens[index].kind == "word":
                name = tokens[index].value
                index += 1
            while index < len(tokens) and tokens[index].value == ":":
                index += 1
                if index >= len(tokens) or tokens[index].kind != "word":
                    raise UnsafeCypherError("Use simple node labels")
                index += 1
            scoped, index = _property_map(tokens, index)
            if index >= len(tokens) or tokens[index].value != ")":
                raise UnsafeCypherError("Unsupported node pattern; use an explicit case_id property or WHERE predicate")
            result.append(("node", name, scoped))
            index += 1
            if index == len(tokens) or tokens[index].value == ",":
                break
            if tokens[index].value == "<":
                index += 1
            if index >= len(tokens) or tokens[index].value != "-":
                raise UnsafeCypherError("Use single-hop case-scoped relationships")
            index += 1
            relationship_name, relationship_scoped = None, False
            if index < len(tokens) and tokens[index].value == "[":
                index += 1
                if index < len(tokens) and tokens[index].kind == "word":
                    relationship_name = tokens[index].value
                    index += 1
                if index < len(tokens) and tokens[index].value == ":":
                    index += 1
                    if index >= len(tokens) or tokens[index].kind != "word":
                        raise UnsafeCypherError("Use a simple relationship type")
                    index += 1
                relationship_scoped, index = _property_map(tokens, index)
                if index >= len(tokens) or tokens[index].value != "]":
                    raise UnsafeCypherError("Variable-length paths and relationship expressions are not supported")
                index += 1
            result.append(("relationship", relationship_name, relationship_scoped))
            if index >= len(tokens) or tokens[index].value != "-":
                raise UnsafeCypherError("Use single-hop case-scoped relationships")
            index += 1
            if index < len(tokens) and tokens[index].value == ">":
                index += 1
        if index < len(tokens):
            index += 1  # comma separating independent patterns
            if index == len(tokens):
                raise UnsafeCypherError("Incomplete MATCH pattern")
    if not result:
        raise UnsafeCypherError("MATCH requires a case-scoped node")
    return result


def _mandatory_scope(tokens: list[_Token]) -> set[str]:
    """Prove equality only when it is required in every boolean branch."""
    # AND inside a CASE arm is conditional, not a required outer conjunction.
    # Complex conditional filters remain usable with inline scoped MATCH nodes.
    if any(token.kind == "word" and token.value.upper() == "CASE" for token in tokens):
        return set()
    while len(tokens) >= 2 and tokens[0].value == "(" and tokens[-1].value == ")":
        depth = 0
        for index, token in enumerate(tokens):
            depth += (token.value == "(") - (token.value == ")")
            if depth == 0:
                break
        if index != len(tokens) - 1:
            break
        tokens = tokens[1:-1]
    for operators in ({"OR", "XOR"}, {"AND"}):
        depth, begin, parts = 0, 0, []
        for index, token in enumerate(tokens):
            depth += (token.value == "(") - (token.value == ")")
            if depth == 0 and token.kind == "word" and token.value.upper() in operators:
                parts.append(tokens[begin:index])
                begin = index + 1
        if parts:
            parts.append(tokens[begin:])
            scopes = [_mandatory_scope(part) for part in parts]
            return set.union(*scopes) if operators == {"AND"} else set.intersection(*scopes)
    values = [token.value for token in tokens]
    if (
        len(values) == 5 and tokens[0].kind == "word"
        and values[1:] == [".", "case_id", "=", "$case_id"]
    ):
        return {values[0]}
    if (
        len(values) == 5 and values[:2] == ["$case_id", "="]
        and tokens[2].kind == "word" and values[3:] == [".", "case_id"]
    ):
        return {values[2]}
    return set()


def _assert_scalar_expression(tokens: list[_Token]) -> None:
    # A function/projection must not hide a second graph query or an unproved
    # relationship pattern. Third-party functions are not a case boundary.
    functions = {
        "ABS", "AVG", "CEIL", "COALESCE", "COLLECT", "COUNT", "DATE", "DATETIME",
        "DURATION", "ELEMENTID", "ENDNODE", "FLOOR", "HEAD", "ID", "KEYS", "LABELS",
        "LAST", "LEFT", "LENGTH", "LOCALDATETIME", "LOCALTIME", "LTRIM", "MAX", "MIN",
        "NODES", "PROPERTIES", "RELATIONSHIPS", "REPLACE", "REVERSE", "RIGHT", "ROUND",
        "RTRIM", "SIGN", "SIZE", "SPLIT", "STARTNODE", "STDEV", "STDEVP", "SUBSTRING",
        "SUM", "TIME", "TIMESTAMP", "TOBOOLEAN", "TOFLOAT", "TOINTEGER", "TOLOWER",
        "TOSTRING", "TOUPPER", "TRIM", "TYPE",
    }
    for index, token in enumerate(tokens):
        if token.value in {"[", "{"} or (
            token.value == "-" and index + 1 < len(tokens)
            and tokens[index + 1].value in {"-", ">", "["}
        ):
            raise UnsafeCypherError("Nested graph patterns, list expressions and map projections are not supported")
        if token.kind == "word" and index + 1 < len(tokens) and tokens[index + 1].value == "(":
            if token.value.upper() in {"AND", "OR", "XOR", "NOT", "WHEN", "THEN", "ELSE"}:
                continue
            if (index and tokens[index - 1].value == ".") or token.value.upper() not in functions:
                raise UnsafeCypherError("Use supported built-in scalar or aggregate functions; custom query functions are not allowed")


def _assert_case_scope(tokens: list[_Token]) -> None:
    # This is deliberately a small, fail-closed grammar, not a regex claim that
    # arbitrary Cypher has been proved safe. WITH aliases/subqueries can shadow
    # proven variables, and variable paths can traverse foreign intermediate nodes.
    unsupported = {"WITH", "UNWIND", "UNION", "EXISTS", "SHORTESTPATH", "ALLSHORTESTPATHS"}
    if any(token.kind == "word" and token.value.upper() in unsupported for token in tokens):
        raise UnsafeCypherError("Use MATCH/OPTIONAL MATCH with every node and relationship case-scoped; WITH, UNWIND, UNION, subqueries and variable-length paths are not supported")
    proven: set[tuple[str, str]] = set()
    index = 0
    while index < len(tokens):
        if tokens[index].value.upper() == "RETURN":
            tail = tokens[index + 1:]
            if not tail or any(
                token.value in {"[", "{"} or (
                    token.kind == "word"
                    and token.value.upper() in {"MATCH", "OPTIONAL", "WHERE", "RETURN"}
                ) for token in tail
            ):
                raise UnsafeCypherError("Return scalar expressions or existing bindings; nested graph patterns are not supported")
            _assert_scalar_expression(tail)
            return
        if tokens[index].value.upper() == "OPTIONAL":
            index += 1
        if index >= len(tokens) or tokens[index].value.upper() != "MATCH":
            raise UnsafeCypherError("Use MATCH or OPTIONAL MATCH before RETURN")
        begin = index = index + 1
        depth = 0
        while index < len(tokens):
            value = tokens[index].value
            if depth == 0 and tokens[index].kind == "word" and value.upper() in {"WHERE", "MATCH", "OPTIONAL", "RETURN"}:
                break
            depth += (value in {"(", "[", "{"}) - (value in {")", "]", "}"})
            index += 1
        bindings = _match_bindings(tokens[begin:index])
        inline = {(kind, name) for kind, name, scoped in bindings if name and scoped}
        local: set[str] = set()
        if index < len(tokens) and tokens[index].value.upper() == "WHERE":
            begin = index = index + 1
            depth = 0
            while index < len(tokens):
                value = tokens[index].value
                if depth == 0 and tokens[index].kind == "word" and value.upper() in {"MATCH", "OPTIONAL", "RETURN"}:
                    break
                depth += (value == "(") - (value == ")")
                index += 1
            _assert_scalar_expression(tokens[begin:index])
            local |= _mandatory_scope(tokens[begin:index])
        for kind, name, scoped in bindings:
            if not scoped and (name is None or ((kind, name) not in proven | inline and name not in local)):
                raise UnsafeCypherError(
                    "Every MATCH node and relationship must be case-scoped; "
                    f"add {{case_id: $case_id}} or a mandatory WHERE equality for "
                    f"{name or 'the anonymous ' + kind}"
                )
        proven.update((kind, name) for kind, name, _ in bindings if name)
    raise UnsafeCypherError("Cypher must return data")


def repair_common_cypher(query: str) -> str:
    """Repair small Neo4j syntax slips the agent commonly makes."""
    query = _single_statement(query)
    tokens = _tokens(query)
    edits: list[tuple[int, int]] = []
    for index, token in enumerate(tokens[:-1]):
        following = tokens[index + 1]
        if token.kind != "word":
            continue
        if token.value.upper() == "NULLS" and following.value.upper() in {"FIRST", "LAST"}:
            edits.append((token.start, following.end))
        elif token.value.upper() == "LIMIT" and following.kind == "parameter":
            edits.append((token.start, following.end))
    repaired = query
    for start, end in reversed(edits):
        repaired = repaired[:start] + repaired[end:]
    return repaired.strip()


def validate_readonly_cypher(query: str, *, limit: int = 100) -> str:
    normalized_query = _single_statement(query)
    tokens = _tokens(normalized_query)
    squashed = " ".join(token.value for token in tokens)
    upper = squashed.upper()

    if not upper.startswith(("MATCH ", "OPTIONAL MATCH ", "WITH ", "UNWIND ")):
        raise UnsafeCypherError("Cypher must begin with MATCH, OPTIONAL MATCH, WITH, or UNWIND")
    if " RETURN " not in f" {upper} ":
        raise UnsafeCypherError("Cypher must return data")
    if "$CASE_ID" not in upper:
        raise UnsafeCypherError("Cypher must include the $case_id parameter")
    if re.search(r"\bNULLS\s+(FIRST|LAST)\b", upper):
        raise UnsafeCypherError("Neo4j in this app does not support ORDER BY NULLS FIRST/LAST")

    found = sorted(keyword for keyword in DENIED_KEYWORDS if re.search(rf"\b{keyword}\b", upper))
    if found:
        raise UnsafeCypherError(f"Cypher contains disallowed keyword(s): {', '.join(found)}")

    _assert_case_scope(tokens)
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
