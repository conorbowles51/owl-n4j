"""
Insights Service — Generates investigative insights for entities using LLM.
"""
import json
import logging

logger = logging.getLogger(__name__)


def generate_entity_insights(entity_data: dict, verified_facts: list, related_entities: list, llm_call_fn) -> list:
    """Generate investigative insights for a defense attorney.

    Args:
        entity_data: Entity dict with name, type, summary
        verified_facts: List of verified fact dicts
        related_entities: List of related entity dicts with name, type, relationship
        llm_call_fn: Function that takes (prompt, temperature, json_mode) and returns string

    Returns:
        List of insight dicts
    """
    facts_text = "\n".join(
        f"- {f.get('text', str(f))}" for f in (verified_facts or [])[:20]
    ) or "No verified facts available."

    related_text = "\n".join(
        f"- {r.get('name', 'Unknown')} ({r.get('type', 'Unknown')}) — {r.get('relationship', 'related')}"
        for r in (related_entities or [])[:15]
    ) or "No related entities."

    prompt = f"""You are an expert defense attorney analyst. Generate 3-5 investigative insights for the following entity.

ENTITY: {entity_data.get('name', 'Unknown')} (Type: {entity_data.get('type', 'Unknown')})
SUMMARY: {entity_data.get('summary', 'No summary available.')}

VERIFIED FACTS:
{facts_text}

RELATED ENTITIES:
{related_text}

Generate insights that would be valuable for a DEFENSE attorney, including:
- Inconsistencies or gaps in evidence
- Significant connections to other entities
- Defense opportunities (alibi, alternative explanations)
- Brady/Giglio concerns (evidence favorable to defense)
- Patterns that weaken the prosecution's case

Return ONLY valid JSON with this structure:
{{
  "insights": [
    {{
      "text": "The insight statement",
      "confidence": "high|medium|low",
      "reasoning": "Why this insight is relevant",
      "category": "inconsistency|connection|defense_opportunity|brady_giglio|pattern",
      "status": "pending"
    }}
  ]
}}
"""

    try:
        response = llm_call_fn(prompt, 0.4, True)
        parsed = json.loads(response)
        insights = parsed.get("insights", [])

        valid_insights = []
        for insight in insights[:5]:
            if not isinstance(insight, dict) or not insight.get("text"):
                continue
            valid_insights.append({
                "text": insight["text"],
                "confidence": insight.get("confidence", "medium"),
                "reasoning": insight.get("reasoning", ""),
                "category": insight.get("category", "pattern"),
                "status": "pending",
            })

        return valid_insights
    except json.JSONDecodeError:
        logger.error("Failed to parse LLM response as JSON for insights")
        return []
    except Exception as e:
        logger.error(f"Failed to generate insights: {e}")
        return []
