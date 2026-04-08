"""Generate compact extraction prompts from the ontology definition."""

from __future__ import annotations

from app.ontology.loader import OntologySchema, load_ontology
from app.pipeline.mandatory_rules import format_mandatory_rules_section


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


def _focus_entity_block(special_entity_types: list[dict] | None) -> str:
    lines: list[str] = []
    for item in special_entity_types or []:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        description = str(item.get("description", "")).strip()
        line = f"- {name}"
        if description:
            line += f": {description}"
        lines.append(line)
    return "\n".join(lines)


def _geo_field_guidance(ontology: OntologySchema) -> str:
    categories = ", ".join(ontology.geocodable_categories)
    return (
        "GEO FIELD RULES:\n"
        f"- The following categories may include geo properties when directly supported by the source text: {categories}\n"
        "- Geo properties are: location_raw, address, city, region, country\n"
        "- Only populate geo properties when the document explicitly supports them\n"
        "- Prefer structured fields (address/city/region/country) when the text provides them\n"
        "- Otherwise preserve the original place reference in location_raw\n"
        "- Do not invent or infer a place just to make an entity mapable\n"
        "- A city is the minimum specificity for a mappable place"
    )


def _financial_provenance_guidance() -> str:
    return (
        "FINANCIAL PROVENANCE RULES:\n"
        "- If an entity involves a monetary amount, total, balance, payment, invoice, transfer, valuation, or alleged proceeds, populate financial_provenance\n"
        "- financial_provenance must be null for non-financial entities\n"
        "- financial_record_kind must be one of: transaction, invoice, payment_instruction, balance, asset_value, fraud_total, allegation, summary_metric, other\n"
        "- financial_view_mode must be transaction only for real documentary transaction events; otherwise use intelligence\n"
        "- is_evidence_backed_transaction must be true only when the document provides documentary proof of a transaction, such as a bank statement row, receipt, wire confirmation, ledger entry, card statement, invoice record, or official report\n"
        "- Narrative claims, allegations, interview statements, email prose, and aggregate totals must never be marked as evidence-backed transactions\n"
        "- evidence_strength must be one of documentary, derived, narrative, unknown\n"
        "- evidence_source_type must be one of bank_statement, invoice, receipt, wire, card_statement, ledger, official_report, email, interview, other\n"
        "- source_page should be the page number shown above when available; otherwise null\n"
        "- source_excerpt should be a short exact snippet supporting the classification"
    )


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
    mandatory_instructions: list[str] | None = None,
    special_entity_types: list[dict] | None = None,
    ontology: OntologySchema | None = None,
    is_table: bool = False,
    sheet_name: str = "",
    page_start: int | None = None,
    page_end: int | None = None,
    file_type: str | None = None,
) -> str:
    if ontology is None:
        ontology = load_ontology()

    parts: list[str] = [
        "You are an expert investigative analyst extracting structured entities from documents.",
        "",
        f"DOCUMENT: {file_name}",
    ]
    if file_type:
        parts.append(f"FILE TYPE: {file_type}")

    instruction_section = format_mandatory_rules_section(
        mandatory_instructions,
        title="MANDATORY EXTRACTION INSTRUCTIONS",
    )
    if instruction_section:
        parts.extend(
            [
                "",
                instruction_section,
                "Before responding, verify that every extracted entity complies with these rules.",
                "Do not leave an entity in the output if it still reflects the default behavior instead of the mandatory rules.",
            ]
        )

    parts.extend(
        [
            "",
            f"BACKGROUND CONTEXT:\n{case_context or 'General investigation'}",
        ]
    )

    if page_start is not None:
        if page_end is not None and page_end != page_start:
            parts.append(f"PAGES: {page_start}-{page_end}")
        else:
            parts.append(f"PAGE: {page_start}")

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

    parts.append("\n" + _geo_field_guidance(ontology))
    parts.append("\n" + _financial_provenance_guidance())

    focus_block = _focus_entity_block(special_entity_types)
    if focus_block:
        parts.append(
            "\nFOCUS ENTITY TYPES:\n"
            "In addition to the ontology categories, pay special attention to these investigation-specific entity types.\n"
            "Use them when they are a more precise fit for the evidence, typically as the specific_type value:\n"
            f"{focus_block}"
        )

    parts.append(
        "\nFor each entity also provide:\n"
        "- specific_type: a more precise label than the category "
        '(e.g., "Suspect", "Burner Phone", "Wire Transfer", "Arrest Warrant")\n'
        "- source_quote: the exact text span that supports this entity\n"
        "- confidence: 0.0 to 1.0\n"
        "- verified_facts: direct facts only, each with text, exact quote, page number, and importance 1-5\n"
        "- ai_insights: optional inferences only, each with text, confidence, and reasoning\n"
        "- financial_provenance: null for non-financial entities, otherwise an object containing the required financial provenance fields"
    )

    parts.append(
        "\nNAME CANONICALIZATION RULES:\n"
        "- Use the FULL canonical name as the entity name "
        '(e.g., "Marcus Chen" not "Dr. Chen" or "M. Chen")\n'
        "- Put titles (Dr., Mr., Prof.), honorifics, and nicknames in the "
        '"aliases" property list, NOT in the name field\n'
        "- For organizations, use the full legal name and put abbreviations "
        "in aliases\n"
        '- Prefer "FirstName LastName" format for persons when both are '
        "available in the text\n"
        "- If only a partial name is given (e.g., just a surname), use it "
        "but set a lower confidence"
    )

    parts.append(f"\nNOISE RULES:\n{_NOISE_RULES}")

    parts.append(
        "\nVERIFIED FACTS VS AI INSIGHTS:\n"
        "- verified_facts must be directly supported by the text in this chunk\n"
        "- Every verified fact must include an exact supporting quote\n"
        "- Use the page number shown above when available; otherwise use null\n"
        "- ai_insights are optional and must contain only analysis or inference, never direct facts\n"
        "- If a statement is not explicitly supported by the document text, it must NOT appear in verified_facts"
    )

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
    mandatory_instructions: list[str] | None = None,
    ontology: OntologySchema | None = None,
) -> str:
    if ontology is None:
        ontology = load_ontology()

    parts: list[str] = [
        "You are an expert investigative analyst extracting relationships between known entities.",
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
    ]

    instruction_section = format_mandatory_rules_section(
        mandatory_instructions,
        title="MANDATORY EXTRACTION INSTRUCTIONS",
    )
    if instruction_section:
        parts.extend(
            [
                "",
                instruction_section,
                "Before responding, verify that every extracted relationship complies with these rules.",
                "Do not emit a relationship that still reflects the default behavior instead of the mandatory rules.",
                "",
            ]
        )

    parts.extend(
        [
            f"BACKGROUND CONTEXT:\n{case_context or 'General investigation'}",
            "",
        ]
    )

    parts.extend(
        [
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
    )

    return "\n".join(parts)
