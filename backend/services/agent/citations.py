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
