"""Generate compact extraction prompts from the ontology definition."""

from __future__ import annotations

from app.ontology.loader import OntologySchema, load_ontology


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _category_block(ontology: OntologySchema) -> str:
    """One-liner per category: name — description (properties)."""
    lines: list[str] = []
    for cat_name in ontology.categories:
        cat = ontology.get_category(cat_name)
        prop_names = ", ".join(p.name for p in cat.properties)
        line = f"- {cat_name}: {cat.description}"
        if prop_names:
            line += f" [{prop_names}]"
        if cat.extraction_notes:
            line += f"\n  NOTE: {cat.extraction_notes}"
        lines.append(line)
    return "\n".join(lines)


def _category_detail_block(ontology: OntologySchema) -> str:
    """Detailed property definitions per category, for reference."""
    sections: list[str] = []
    for cat_name in ontology.categories:
        cat = ontology.get_category(cat_name)
        if not cat.properties:
            continue
        prop_lines: list[str] = []
        for p in cat.properties:
            desc = p.description or p.name
            if p.enum:
                desc += f" (options: {', '.join(p.enum)})"
            prop_lines.append(f"    {p.name}: {desc}")
        sections.append(f"  {cat_name}:\n" + "\n".join(prop_lines))
    return "\n".join(sections)


def _disambiguation_block(ontology: OntologySchema) -> str:
    lines: list[str] = []
    for rule in ontology.disambiguation_rules:
        cats = " vs ".join(rule.categories)
        lines.append(f"- {cats}: {rule.rule}")
    return "\n".join(lines)


def _relationship_block(ontology: OntologySchema) -> str:
    """One-liner per relationship type."""
    lines: list[str] = []
    for rel_name in ontology.relationship_types:
        rel = ontology.get_relationship(rel_name)
        src = "/".join(rel.typical_source) if rel.typical_source else "any"
        tgt = "/".join(rel.typical_target) if rel.typical_target else "any"
        line = f"- {rel_name}: {rel.description} ({src} → {tgt})"
        lines.append(line)
    return "\n".join(lines)


_NOISE_RULES = """\
- Do NOT extract generic concepts, abstract ideas, or common nouns
- Do NOT extract the document itself as an entity
- Do NOT extract entities mentioned only in passing with no investigative relevance
- Every entity must have a specific name or identifier
- Prefer fewer, high-quality entities over many low-quality ones"""


# ---------------------------------------------------------------------------
# Entity extraction prompt
# ---------------------------------------------------------------------------

def build_entity_extraction_prompt(
    chunk_text: str,
    file_name: str,
    case_context: str,
    ontology: OntologySchema | None = None,
    is_table: bool = False,
    sheet_name: str = "",
) -> str:
    if ontology is None:
        ontology = load_ontology()

    parts: list[str] = [
        "You are an expert investigative analyst extracting structured entities from documents.",
        "",
        f"CASE CONTEXT:\n{case_context or 'General investigation'}",
        "",
        f"DOCUMENT: {file_name}",
    ]

    if is_table:
        sheet_label = f" (Sheet: {sheet_name})" if sheet_name else ""
        parts.append(f"\nThis is structured TABULAR data{sheet_label}. Pay attention to:")
        parts.append("- Each row may represent a separate entity (transaction, person, record)")
        parts.append("- Column headers define property names")
        parts.append("- Preserve structure — extract one entity per meaningful row where appropriate")
        parts.append("")

    parts.append(
        "Extract entities from the text below. Be SELECTIVE — only extract entities "
        "relevant to the investigation."
    )

    parts.append("\nCATEGORIES (assign exactly one per entity):")
    parts.append(_category_block(ontology))

    parts.append("\nPROPERTY REFERENCE:")
    parts.append(_category_detail_block(ontology))

    parts.append("\nDISAMBIGUATION:")
    parts.append(_disambiguation_block(ontology))

    parts.append(
        "\nFor each entity also provide:\n"
        "- specific_type: a more precise label than the category "
        '(e.g., "Suspect", "Burner Phone", "Wire Transfer", "Arrest Warrant")\n'
        "- source_quote: the exact text span that supports this entity\n"
        "- confidence: 0.0 to 1.0"
    )

    parts.append(f"\nNOISE RULES:\n{_NOISE_RULES}")

    parts.append(f"\nTEXT:\n{chunk_text}")

    parts.append("\nRespond with JSON matching the required schema.")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Relationship extraction prompt
# ---------------------------------------------------------------------------

def build_relationship_extraction_prompt(
    chunk_text: str,
    file_name: str,
    case_context: str,
    entities_json: str,
    ontology: OntologySchema | None = None,
) -> str:
    if ontology is None:
        ontology = load_ontology()

    parts: list[str] = [
        "You are an expert investigative analyst extracting relationships between known entities.",
        "",
        f"CASE CONTEXT:\n{case_context or 'General investigation'}",
        "",
        f"DOCUMENT: {file_name}",
        "",
        "The following entities have been identified in this text:",
        entities_json,
        "",
        "Extract relationships BETWEEN these entities based on the text below. "
        "Use the entity IDs provided.",
        "",
        "CORE RELATIONSHIP TYPES (prefer these, but create custom types if none fit):",
        _relationship_block(ontology),
        "",
        "For each relationship provide:",
        "- source_entity_id and target_entity_id (from the entity list above)",
        "- type: one of the core types above, or a custom UPPER_SNAKE_CASE type",
        "- detail: brief description of the specific nature of this relationship",
        "- properties: any additional structured data (dates, amounts, etc.)",
        "- source_quote: exact text span supporting this relationship",
        "- confidence: 0.0 to 1.0",
        "",
        "RULES:",
        "- Only extract relationships clearly supported by the text",
        "- Do NOT infer relationships not stated or strongly implied",
        "- Both entities in a relationship must be from the provided list",
        "- Prefer specific relationship types over ASSOCIATED_WITH when possible",
        "",
        f"TEXT:\n{chunk_text}",
        "",
        "Respond with JSON matching the required schema.",
    ]

    return "\n".join(parts)
