"""One case search for all of Loupe (lx-casesearch; plan R1-R4 in headless/AGENT-RELEVANCE-PLAN.md).

Every search of case content goes through ``search``: the agent's search tools, chat, the Search page and the
theory test ("test both directions"). The stages, each in its own module:

1. ``understand``: the question's terms, quoted phrases, names expanded to the numbers, contact names and accounts the
   case ties to them (each labelled with where the tie comes from), dates turned into windows in the case's time zone,
   and other phrasings of the question.
2. ``net``: a wide net over every kind of case material: meaning and words together (``services.embed_all.search``),
   documents by their words, graph entities by name, alias and meaning.
3. ``rerank``: a model scores every candidate against the question (0-10) and gives a one-line reason.
4. ``service``: duplicates removed, grades by a stated rule (Strong 7-10, Moderate 4-6, Weak 0-3), weaker results
   counted and pageable, never dropped.
5. ``units``: each hit is a whole unit: the message with its thread window, the document passage, the statement row
   with the other rows of its account and month, the entity with its aliases and links.

The result has one shape (``shape.RESULT_KEYS``): total, shown, next page, what was searched, what was not, and why
a search is empty. Text matching of case content lives here and in the modules this package calls; a lint test
(``tests/test_case_search_lint.py``) fails on new text matching anywhere else.
"""
from services.case_search.service import KINDS, search  # noqa: F401
