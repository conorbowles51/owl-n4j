"""
LLM Service - handles all AI API interactions for the investigation console.
"""

from typing import Dict, Any, Optional
import requests
import json

from config import OLLAMA_BASE_URL, OLLAMA_MODEL, OPENAI_MODEL, LLM_PROVIDER, LLM_MODEL, OPENAI_API_KEY
from profile_loader import get_chat_config

import sys
from pathlib import Path
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from models.llm_models import LLMProvider, get_default_model, get_model_by_id

from openai import OpenAI

client = None
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)

config = get_chat_config()
system_context = config.get("system_context", "You are an AI assistant.")
analysis_guidance = config.get("analysis_guidance", "Provide clear and helpful answers.")

class LLMService:
    """Service for LLM interactions via llm."""

    def __init__(self):
        # Initialize with config defaults
        self.provider = LLM_PROVIDER or "ollama"
        self.model_id = LLM_MODEL
        
        # Set default model if not specified
        if not self.model_id:
            provider_enum = LLMProvider(self.provider)
            default_model = get_default_model(provider_enum)
            self.model_id = default_model.id
        
        # Ensure model exists
        model = get_model_by_id(self.model_id)
        if not model:
            # Fallback to default
            provider_enum = LLMProvider(self.provider)
            default_model = get_default_model(provider_enum)
            self.model_id = default_model.id
            self.provider = default_model.provider.value
    
    def get_current_config(self) -> tuple[str, str]:
        """Get current provider and model ID."""
        return (self.provider, self.model_id)
    
    def set_config(self, provider: str, model_id: str):
        """Set the provider and model."""
        self.provider = provider.lower()
        self.model_id = model_id

    def call(
        self,
        prompt: str,
        temperature: float = 0.3,
        json_mode: bool = False,
        timeout: int = 600,  # 10 minutes default for large models
    ) -> str:
        """
        Call the LLM (Ollama or OpenAI).

        Args:
            prompt: The prompt to send
            temperature: Sampling temperature
            json_mode: Request JSON output
            timeout: Request timeout

        Returns:
            Model response text
        """
        if self.provider == "ollama":
            return self._call_ollama(prompt, temperature, json_mode, timeout)
        elif self.provider == "openai":
            return self._call_openai(prompt, temperature, json_mode, timeout)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    def _call_ollama(
        self,
        prompt: str,
        temperature: float = 0.3,
        json_mode: bool = False,
        timeout: int = 600,  # 10 minutes default for large models
    ) -> str:
        """Call Ollama LLM."""
        try:
            url = f"{OLLAMA_BASE_URL}/api/chat"

            payload: Dict = {
                "model": self.model_id,
                "messages": [
                    {"role": "system", "content": system_context},
                    {"role": "user", "content": prompt}
                ],
                "stream": False,
                "options": {
                    "temperature": temperature,
                },
            }

            if json_mode:
                payload["format"] = "json"

            # Use tuple timeout: (connect_timeout, read_timeout)
            # Connect timeout: 10 seconds, Read timeout: as specified (for large models)
            resp = requests.post(url, json=payload, timeout=(10, timeout))
            resp.raise_for_status()

            data = resp.json()
            content = (data.get("message") or {}).get("content", "") or ""
            if not content.strip():
                raise ValueError("LLM returned empty response")
            return content
        except Exception as e:
            print(f"[LLM] ERROR calling Ollama: {e}")
            raise
    
    def _call_openai(
        self,
        prompt: str,
        temperature: float = 0.3,
        json_mode: bool = False,
        timeout: int = 600,  # 10 minutes default for large models
    ) -> str:
        """Call OpenAI LLM."""
        if not client:
            raise ValueError("OpenAI client not initialized. OPENAI_API_KEY not set.")
        
        try:
            kwargs = {
                "model": self.model_id,
                "messages": [
                    {"role": "system", "content": system_context},
                    {"role": "user", "content": prompt}
                ],
                "temperature": temperature,
                "timeout": timeout,
            }

            # Force JSON response if requested
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            print(f"[LLM] Calling OpenAI model {self.model_id} with prompt length {len(prompt)}")
            response = client.chat.completions.create(**kwargs)

            # Extract content
            content = response.choices[0].message.content
            if not content:
                print("[LLM] WARNING: Empty response from LLM")
                raise ValueError("LLM returned empty response")
            
            print(f"[LLM] Response length: {len(content)}")
            return content
        except Exception as e:
            print(f"[LLM] ERROR calling OpenAI: {e}")
            raise
            # --- OpenAI API --- #
            # kwargs = {
            #     "model": OPENAI_MODEL,
            #     "messages": [
            #         {"role": "user", "content": prompt}
            #     ],
            #     "temperature": temperature,
            #     "timeout": timeout,
            # }

            # # Force JSON response if requested
            # if json_mode:
            #     kwargs["response_format"] = {"type": "json_object"}

            # print(f"[LLM] Calling model {OPENAI_MODEL} with prompt length {len(prompt)}")
            # response = client.chat.completions.create(**kwargs)

            # # Extract content
            # content = response.choices[0].message.content
            # if not content:
            #     print("[LLM] WARNING: Empty response from LLM")
            #     raise ValueError("LLM returned empty response")
            
            # print(f"[LLM] Response length: {len(content)}")
            # return content
        except Exception as e:
            print(f"[LLM] ERROR calling LLM: {e}")
            print(f"[LLM] Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            raise

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

        prompt = f"""{system_context}. You are also a Neo4j Cypher expert.        
Given the following graph schema and AVAILABLE ENTITIES:
{schema_info}

Generate a Cypher query to answer this question:
"{question}"

CRITICAL RULES:
1.⁠ ⁠You MUST use the EXACT 'key' values from the AVAILABLE ENTITIES list above
2.⁠ ⁠DO NOT guess or invent keys - only use keys that appear in the list
3.⁠ ⁠Keys are lowercase with hyphens (e.g., 'john-smith'), NOT the display name
4.⁠ ⁠If you cannot find the exact entity key in the list, return can_query: false
5.⁠ ⁠Use only the entity types and relationship types from the schema
6.⁠ ⁠Return relevant properties (name, key, type, summary)
7.⁠ ⁠Keep queries simple and readable

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
        answer, _ = self.answer_question_with_prompt(question, context, query_results)
        return answer

    def answer_question_with_prompt(
        self,
        question: str,
        context: str,
        query_results: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        Answer a question based on graph context and return the prompt used.

        Args:
            question: User's question
            context: Graph context (entities, relationships)
            query_results: Optional results from a Cypher query

        Returns:
            Tuple of (answer text, prompt used)
        """
        try:
            query_section = ""
            if query_results:
                query_section = f"""
Query Results:
{query_results}
"""

            prompt = f"""{system_context}

You have access to the following information from the investigation graph:

{context}
{query_section}

Based on this information, please answer the investigator's question:
"{question}"

Guidelines:
- {analysis_guidance}
- Format your response using markdown (use **bold** for emphasis, bullet points with -)
- Do NOT use tables - use bullet points or numbered lists instead for structured data
- Be specific and cite entity names when relevant
- If you identify suspicious patterns, explain them
- Use ALL available information from the context above - extract and synthesize details from summaries, notes, and relationships
- If specific details (like exact dates, amounts, or names) are mentioned in the context, include them in your answer
- Only say "insufficient information" if the context truly contains NO relevant information about the question
- If the context has related information (even if incomplete), provide what you can find and note what additional details would be helpful
- Keep your response focused and professional
- Highlight any connections or patterns you notice

Answer:"""

            answer = self.call(prompt, temperature=0.3)
            if not answer or not answer.strip():
                print("[LLM] WARNING: answer_question returned empty answer")
                raise ValueError("LLM returned empty answer")
            return answer, prompt
        except Exception as e:
            print(f"[LLM] ERROR in answer_question: {e}")
            import traceback
            traceback.print_exc()
            raise


# Singleton instance
llm_service = LLMService()