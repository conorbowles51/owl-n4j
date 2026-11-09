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
