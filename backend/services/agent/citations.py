"""Document citations in agent text as links the answer renderer can open.

A Markdown link target cannot contain a space, so ``[March statement.pdf, p.4](doc://March statement.pdf/4)``
renders as plain text and the citation cannot be clicked. The chat encodes the filename
(services/rag_service.py); agent answers and report sections get the same encoding here. The page stays as given;
a citation with no page keeps none.
"""
import re
from urllib.parse import quote, unquote

_DOC_LINK = re.compile(r"\]\(\s*<?doc://([^)>]*?)>?\s*\)")


def _encode(target: str) -> str:
    head, slash, tail = target.rpartition("/")
    filename, page = (head, tail) if slash and tail.strip().isdigit() else (target, "")
    encoded = quote(unquote(filename.strip()), safe="")
    return f"](doc://{encoded}/{page.strip()})" if page else f"](doc://{encoded})"


def link_document_citations(text: str) -> str:
    return _DOC_LINK.sub(lambda match: _encode(match.group(1)), text or "")


# A file name the answer quotes as code (`statement.pdf`) where a link was meant: coverage run v-tl-2, 8 Nov 2026,
# named its source as `lxfw-feat002-cost-100k.txt` and the answer carried no citation. Linked only when this run's
# own tool results returned that exact name, so a name the model made up is never turned into a citation.
_TICKED_FILE = re.compile(r"(?<![\[`])`([^`\n/\\]{1,200}\.[A-Za-z0-9]{2,5})`(?![`\]])")


def link_named_files(text: str, returned: str) -> str:
    """Turn a code-quoted file name into its doc:// link when ``returned`` (the run's tool results) holds it."""
    if not text or "`" not in text or not returned:
        return text or ""
    parts = re.split(r"(```.*?(?:```|\Z))", text, flags=re.S)

    def one(match: re.Match) -> str:
        name = match.group(1).strip()
        if not name or name not in returned:
            return match.group(0)
        return f"[{name}](doc://{quote(name, safe='')})"

    return "".join(part if part.startswith("```") else _TICKED_FILE.sub(one, part) for part in parts)


# A tool result's handle (res_<hex>, services/agent/tools.py) written as a citation: demo case Q3, 10 Nov 2026, cited
# all 7 sources as doc://res_<hex>, which open nothing in the case. The handle is swapped for the one source link that
# result returned; a result with none or several gives no single source, so its label stays as plain text.
_RESULT_LINK = re.compile(r"\[([^\]\n]*)\]\(\s*<?(?:[A-Za-z]+://)?(res_[0-9a-f]{6,32})(?:/[^)>\s]*)?>?\s*\)")
_REAL_CITE = re.compile(r"^(?:txn|doc|rec)://(?!res_)\S+$")


def _cites_in(value, found: set, depth: int = 0) -> None:
    if depth > 6 or len(found) > 1:
        return
    if isinstance(value, str):
        if _REAL_CITE.match(value.strip()):
            found.add(value.strip())
    elif isinstance(value, dict):
        for item in value.values():
            _cites_in(item, found, depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _cites_in(item, found, depth + 1)


def replace_result_handles(text: str, results: dict | None) -> str:
    """Rewrite each ``[label](scheme://res_<hex>)`` to the result's own source link, or to ``label`` when it has none."""
    if not text or "res_" not in text:
        return text or ""

    def one(match: re.Match) -> str:
        label, handle = match.group(1), match.group(2)
        found: set = set()
        _cites_in((results or {}).get(handle), found)
        return f"[{label}]({found.pop()})" if len(found) == 1 else label

    return _RESULT_LINK.sub(one, text)
