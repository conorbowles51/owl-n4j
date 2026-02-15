"""
LLM Service - handles all AI API interactions for the investigation console.
"""

from typing import Dict, Any, Optional
import requests
import json

from config import OLLAMA_BASE_URL, OLLAMA_MODEL, OPENAI_MODEL, LLM_PROVIDER, LLM_MODEL, OPENAI_API_KEY, QUESTION_CLASSIFICATION_ENABLED
from profile_loader import get_chat_config

import sys
from pathlib import Path
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from models.llm_models import LLMProvider, get_default_model, get_model_by_id

from openai import OpenAI

from utils.prompt_trace import log_section

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
        self.provider = LLM_PROVIDER or "openai"
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
        
        # Context for cost tracking (set by caller)
        self._cost_tracking_context = None
    
    def get_current_config(self) -> tuple[str, str]:
        """Get current provider and model ID."""
        return (self.provider, self.model_id)
    
    def set_config(self, provider: str, model_id: str):
        """Set the provider and model."""
        self.provider = provider.lower()
        self.model_id = model_id
    
    def set_cost_tracking_context(self, case_id: Optional[str] = None, user_id: Optional[str] = None, job_type: Optional[str] = None, description: Optional[str] = None, extra_metadata: Optional[Dict] = None):
        """Set context for cost tracking."""
        self._cost_tracking_context = {
            "case_id": case_id,
            "user_id": user_id,
            "job_type": job_type,
            "description": description,
            "extra_metadata": extra_metadata,
        }
    
    def clear_cost_tracking_context(self):
        """Clear cost tracking context."""
        self._cost_tracking_context = None

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

            log_section(
                source_file=__file__,
                source_func="_call_ollama",
                title="HTTP request: Ollama /api/chat payload",
                content={
                    "url": url,
                    "model_id": self.model_id,
                    "provider": self.provider,
                    "json_mode": json_mode,
                    "temperature": temperature,
                    "payload": payload,
                },
                as_json=True,
            )

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
            # Some OpenAI models (like o1, o3, gpt-5) don't support custom temperature
            # They only support the default value of 1.0
            # Check if the model doesn't support custom temperature
            models_without_temperature_support = ["o1", "o3", "gpt-5"]
            supports_custom_temperature = not any(
                self.model_id.startswith(prefix) for prefix in models_without_temperature_support
            )
            
            kwargs = {
                "model": self.model_id,
                "messages": [
                    {"role": "system", "content": system_context},
                    {"role": "user", "content": prompt}
                ],
                "timeout": timeout,
            }
            
            # Only add temperature if the model supports custom temperature values
            # Some models (like o1, o3, gpt-5) only support the default temperature (1.0)
            # and will error if any temperature parameter is provided
            if supports_custom_temperature:
                kwargs["temperature"] = temperature
            # For models that don't support custom temperature, omit the parameter
            # OpenAI will use the default value (1.0) automatically

            # Force JSON response if requested
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            log_section(
                source_file=__file__,
                source_func="_call_openai",
                title="HTTP request: OpenAI chat.completions payload",
                content={
                    "model_id": self.model_id,
                    "provider": self.provider,
                    "json_mode": json_mode,
                    "temperature": temperature,
                    "payload": kwargs,
                },
                as_json=True,
            )

            print(f"[LLM] Calling OpenAI model {self.model_id} with prompt length {len(prompt)}")
            response = client.chat.completions.create(**kwargs)

            # Extract content
            content = response.choices[0].message.content
            if not content:
                print("[LLM] WARNING: Empty response from LLM")
                raise ValueError("LLM returned empty response")
            
            # Track token usage and cost
            try:
                from services.cost_tracking_service import record_cost, CostJobType
                from postgres.session import get_db
                import uuid as uuid_lib
                
                usage = response.usage
                if usage:
                    # Get database session
                    db = next(get_db())
                    try:
                        # Get context from instance variable
                        context = self._cost_tracking_context or {}
                        job_type_str = context.get("job_type", "ai_assistant")
                        job_type = CostJobType.AI_ASSISTANT if job_type_str == "ai_assistant" else CostJobType.INGESTION
                        
                        # Parse case_id and user_id if provided
                        case_id = None
                        if context.get("case_id"):
                            try:
                                case_id = uuid_lib.UUID(context["case_id"])
                            except (ValueError, TypeError):
                                pass
                        
                        user_id = None
                        if context.get("user_id"):
                            try:
                                user_id = uuid_lib.UUID(context["user_id"])
                            except (ValueError, TypeError):
                                pass
                        
                        record_cost(
                            job_type=job_type,
                            provider="openai",
                            model_id=self.model_id,
                            prompt_tokens=usage.prompt_tokens,
                            completion_tokens=usage.completion_tokens,
                            total_tokens=usage.total_tokens,
                            case_id=case_id,
                            user_id=user_id,
                            description=context.get("description"),
                            extra_metadata=context.get("extra_metadata"),
                            db=db,
                        )
                    except Exception as e:
                        print(f"[LLM] WARNING: Failed to record cost: {e}")
                    finally:
                        db.close()
            except ImportError:
                # Cost tracking not available, skip
                pass
            except Exception as e:
                # Don't fail the request if cost tracking fails
                print(f"[LLM] WARNING: Cost tracking error: {e}")
            
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

    def classify_question(self, question: str) -> str:
        """
        Classify a question as semantic, structural, or hybrid.

        - semantic: Questions about content, meaning, descriptions, summaries
          (e.g., "What did John say about the transaction?", "Describe the evidence")
        - structural: Questions about counts, connections, patterns, graph structure
          (e.g., "How many transactions involve X?", "Who is connected to Y?")
        - hybrid: Questions that benefit from both approaches
          (e.g., "What are the suspicious connections between X and Y?")

        Args:
            question: The user's question

        Returns:
            One of "semantic", "structural", or "hybrid"
        """
        if not QUESTION_CLASSIFICATION_ENABLED:
            return "hybrid"

        prompt = f"""Classify this investigation question into exactly one category.

Categories:
- "semantic": Questions about content, meaning, descriptions, what someone said or did, summaries of events or documents
- "structural": Questions about counts, lists of connections, network patterns, who is connected to whom, how many, which entities
- "hybrid": Questions that need both text understanding AND graph/structural information

Question: "{question}"

Return ONLY valid JSON:
{{"classification": "semantic" or "structural" or "hybrid"}}"""

        try:
            response = self.call(prompt, temperature=0.0, json_mode=True)
            result = self.parse_json_response(response)
            classification = result.get("classification", "hybrid").lower().strip()
            if classification in ("semantic", "structural", "hybrid"):
                return classification
            return "hybrid"
        except Exception as e:
            print(f"[LLM] Question classification failed: {e}")
            return "hybrid"

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
    ) -> str:
        """
        Answer a question based on document context.

        Args:
            question: User's question
            context: Document context from vector search

        Returns:
            Answer text
        """
        answer, _ = self.answer_question_with_prompt(question, context)
        return answer

    def answer_question_with_prompt(
        self,
        question: str,
        context: str,
    ) -> tuple[str, str]:
        """
        Answer a question based on document context and return the prompt used.

        Args:
            question: User's question
            context: Document context from vector search

        Returns:
            Tuple of (answer text, prompt used)
        """
        try:
            prompt = f"""{system_context}

You have access to the following investigation context:

{context}

Based on this investigation context, please answer the question:
"{question}"

Guidelines:
- {analysis_guidance}
- Format your response using markdown (use **bold** for emphasis, bullet points with -)
- Do NOT use tables - use bullet points or numbered lists instead for structured data
- CITE SOURCES: When referencing specific facts, cite the document name and page number in [brackets] (e.g., [Financial Report, p.3])
- When verified facts are provided with quotes, reference the original quote to support your answer
- Be specific and cite document names when relevant
- If you identify patterns or important information, explain them
- Use ALL available information from the context above - extract and synthesize details from text passages, entity information, graph connections, and any query results
- If specific details (like exact dates, amounts, or names) are mentioned, include them in your answer
- Only say "insufficient information" if the context truly contains NO relevant information about the question
- If the context has related information (even if incomplete), provide what you can find and note what additional details would be helpful
- Keep your response focused and professional
- Highlight any connections or patterns you notice across different sources of information

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