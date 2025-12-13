"""
LLM Service - handles all AI API interactions for the investigation console.
"""

from typing import Dict, Any, Optional
import requests
import json

from config import OPENAI_MODEL

from openai import OpenAI

client = OpenAI()


class LLMService:
    """Service for LLM interactions via llm."""

    def __init__(self):
        self.model = OPENAI_MODEL

    def call(
        self,
        prompt: str,
        temperature: float = 0.3,
        json_mode: bool = False,
        timeout: int = 180,
    ) -> str:
        """
        Call the Ollama LLM.

        Args:
            prompt: The prompt to send
            temperature: Sampling temperature
            json_mode: Request JSON output
            timeout: Request timeout

        Returns:
            Model response text
        """
        kwargs = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "timeout": timeout,
        }

        # Force JSON response if requested
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**kwargs)

        # Extract content
        return response.choices[0].message.content
    
        url = f"{self.base_url.rstrip('/')}/api/generate"

        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        if json_mode:
            payload["format"] = "json"

        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")

    def parse_json_response(self, response_text: str) -> Dict:
        """
        Parse JSON from LLM response.
        """
        start = response_text.find("{")
        end = response_text.rfind("}")

        if start == -1 or end == -1 or end <= start:
            raise ValueError("No JSON object found in response")

        json_str = response_text[start:end + 1]
        return json.loads(json_str)

    def generate_cypher(
        self,
        question: str,
        schema_info: str,
    ) -> Optional[str]:
        """
        Generate a Cypher query from a natural language question.

        Args:
            question: User's question
            schema_info: Description of the graph schema

        Returns:
            Cypher query string or None if generation failed
        """
        prompt = f"""You are a Neo4j Cypher expert helping with fraud investigations.

Given the following graph schema and AVAILABLE ENTITIES:
{schema_info}

Generate a Cypher query to answer this question:
"{question}"

CRITICAL RULES:
1. You MUST use the EXACT 'key' values from the AVAILABLE ENTITIES list above
2. DO NOT guess or invent keys - only use keys that appear in the list
3. Keys are lowercase with hyphens (e.g., 'john-smith'), NOT the display name
4. If you cannot find the exact entity key in the list, return can_query: false
5. Use only the entity types and relationship types from the schema
6. Return relevant properties (name, key, type, summary)
7. Keep queries simple and readable

Return ONLY valid JSON with this structure:
{{
    "can_query": true or false,
    "cypher": "MATCH ... RETURN ..." or null,
    "explanation": "brief explanation of what the query does"
}}
"""

        try:
            response = self.call(prompt, json_mode=True)
            result = self.parse_json_response(response)

            if result.get("can_query") and result.get("cypher"):
                return result["cypher"]
            return None
        except Exception as e:
            print(f"Cypher generation error: {e}")
            return None

    def answer_question(
        self,
        question: str,
        context: str,
        query_results: Optional[str] = None,
    ) -> str:
        """
        Answer a question based on graph context.

        Args:
            question: User's question
            context: Graph context (entities, relationships)
            query_results: Optional results from a Cypher query

        Returns:
            Answer text
        """
        query_section = ""
        if query_results:
            query_section = f"""
Query Results:
{query_results}
"""

        prompt = f"""You are an AI assistant helping fraud investigators analyze a case.

You have access to the following information from the investigation graph:

{context}
{query_section}

Based on this information, please answer the investigator's question:
"{question}"

Guidelines:
- Format your response using markdown (use **bold** for emphasis, bullet points with -)
- Do NOT use tables - use bullet points or numbered lists instead for structured data
- Be specific and cite entity names when relevant
- If you identify suspicious patterns, explain them
- If the information is insufficient, say so clearly
- Keep your response focused and professional
- Highlight any connections or patterns you notice

Answer:"""

        return self.call(prompt, temperature=0.3)


# Singleton instance
llm_service = LLMService()
