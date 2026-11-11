"""Extraction prompts open with what every chunk shares, so DeepSeek reads it from its cache: per-chunk parts (page,
table note, text, entity list, a transcript's speakers) come after the fixed instructions. Measured on CHAT JARZ
EMPRESA.pdf (11 Nov 2026): with the page line near the top, 9 % of entity prompt tokens were cache hits; with it
at the end, 95 % once the cache was built."""
from app.ontology.prompt_builder import build_entity_extraction_prompt, build_relationship_extraction_prompt


def _common_prefix(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _entity(page, text, is_table, context="Case X"):
    return build_entity_extraction_prompt(chunk_text=text, file_name="chat.pdf", case_context=context,
                                          mandatory_instructions=["Name every bank account by its number."],
                                          special_entity_types=[{"name": "Courier", "description": "Carries cash"}],
                                          is_table=is_table, page_start=page, page_end=page, file_type="pdf")


def test_entity_prompt_shares_every_fixed_block_across_chunks() -> None:
    a = _entity(1, "Azucena: hola", True)
    b = _entity(57, "Pedro: ya", False, context="Case X\n\nSpeakers: S1")
    shared = a[:_common_prefix(a, b)]
    for block in ("CATEGORIES", "PROPERTY REFERENCE:", "DISAMBIGUATION:", "NAME CANONICALIZATION RULES:",
                  "NOISE RULES:", "VERIFIED FACTS VS AI INSIGHTS:", "MANDATORY EXTRACTION INSTRUCTIONS",
                  "FOCUS ENTITY TYPES:"):
        assert block in shared, block
    # Per-chunk parts are still given, next to the text.
    tail = a[_common_prefix(a, b):]
    assert "PAGE: 1" in a and "PAGE: 57" in b and "TABULAR" in a and "TABULAR" not in b
    assert tail.index("Azucena: hola") > 0


def test_relationship_prompt_shares_fixed_rules_across_chunks() -> None:
    def rel(entities, text):
        return build_relationship_extraction_prompt(chunk_text=text, file_name="chat.pdf", case_context="Case X",
                                                    entities_json=entities,
                                                    mandatory_instructions=["Name every bank account by its number."])
    a = rel('[{"id": "e1", "name": "Azucena"}]', "Azucena: hola")
    b = rel('[{"id": "e1", "name": "Pedro"}]', "Pedro: ya")
    shared = a[:_common_prefix(a, b)]
    for block in ("CORE RELATIONSHIP TYPES", "For each relationship provide:", "RULES:",
                  "MANDATORY EXTRACTION INSTRUCTIONS", "BACKGROUND CONTEXT:"):
        assert block in shared, block
    assert '"Azucena"' in a and a.index('"Azucena"') < a.index("\nTEXT:\n")
