"""Platform-owned OpenAI embedding generation service."""

from typing import List

# Try to import OpenAI (optional)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from config import EMBEDDING_PROVIDER, EMBEDDING_MODEL, OPENAI_API_KEY
from services.ai_costs_service import CostOperationKind, get_current_ai_cost_context
from services.cost_tracking_service import record_cost


class EmbeddingService:
    """Service for generating text embeddings."""
    
    def __init__(self):
        """Initialize the one supported embedding implementation."""
        self.provider = EMBEDDING_PROVIDER
        self.model = EMBEDDING_MODEL
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI package not installed. Install with: pip install openai")
        self.client = None
        self._client_key = None
        self._validate_openai_model()
    
    def _validate_openai_model(self) -> None:
        """Validate that the OpenAI model is available."""
        # OpenAI models are validated on first use, so we'll just log
        print(f"[Embedding] Using OpenAI model: {self.model}")

    def _get_openai_client(self):
        api_key = None
        try:
            from postgres.session import get_background_session
            from services.ai_provider_credentials import get_provider_api_key

            with get_background_session() as db:
                api_key = get_provider_api_key(db, "openai")
        except Exception:
            api_key = OPENAI_API_KEY
        if not api_key:
            raise ValueError(
                "OpenAI is not connected. Add its API key in Settings → AI settings."
            )
        if self.client is None or self._client_key != api_key:
            self.client = OpenAI(api_key=api_key)
            self._client_key = api_key
        return self.client
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats (embedding vector)
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")
        
        try:
            response = self._get_openai_client().embeddings.create(
                model=self.model,
                input=text
            )
            context = get_current_ai_cost_context()
            if context:
                usage = getattr(response, "usage", None)
                prompt_tokens = None
                total_tokens = None
                if usage is not None:
                    prompt_tokens = getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", None)
                    total_tokens = getattr(usage, "total_tokens", None)
                try:
                    from postgres.session import get_background_session

                    with get_background_session() as db:
                        record_cost(
                            db=db,
                            job_type=context.job_type,
                            provider="openai",
                            model_id=self.model,
                            operation_kind=CostOperationKind.EMBEDDING,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=0,
                            total_tokens=total_tokens or prompt_tokens,
                            case_id=context.case_id,
                            user_id=context.user_id,
                            engine_job_id=context.engine_job_id,
                            evidence_file_id=context.evidence_file_id,
                            description=context.description or "Embedding generation",
                            extra_metadata=context.extra_metadata,
                        )
                except Exception as tracking_error:
                    print(f"[Embedding] Warning: failed to record cost: {tracking_error}")
            return response.data[0].embedding
        
        except Exception as e:
            print(f"[Embedding] Error generating embedding: {e}")
            raise
    
    def generate_embeddings_batch(
        self,
        texts: List[str],
        batch_size: int = 100
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches.
        
        Args:
            texts: List of texts to embed
            batch_size: Number of texts per batch (OpenAI supports up to 2048)
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        embeddings = []
        
        # Filter out empty texts
        valid_texts = [t for t in texts if t and t.strip()]
        if len(valid_texts) < len(texts):
            print(f"[Embedding] Warning: {len(texts) - len(valid_texts)} empty texts filtered out")
        
        for i in range(0, len(valid_texts), batch_size):
            batch = valid_texts[i:i + batch_size]
            
            try:
                response = self._get_openai_client().embeddings.create(
                    model=self.model,
                    input=batch
                )
                context = get_current_ai_cost_context()
                if context:
                    usage = getattr(response, "usage", None)
                    prompt_tokens = None
                    total_tokens = None
                    if usage is not None:
                        prompt_tokens = getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", None)
                        total_tokens = getattr(usage, "total_tokens", None)
                    try:
                        from postgres.session import get_background_session

                        with get_background_session() as db:
                            record_cost(
                                db=db,
                                job_type=context.job_type,
                                provider="openai",
                                model_id=self.model,
                                operation_kind=CostOperationKind.EMBEDDING,
                                prompt_tokens=prompt_tokens,
                                completion_tokens=0,
                                total_tokens=total_tokens or prompt_tokens,
                                case_id=context.case_id,
                                user_id=context.user_id,
                                engine_job_id=context.engine_job_id,
                                evidence_file_id=context.evidence_file_id,
                                description=context.description or "Embedding generation",
                                extra_metadata={
                                    **(context.extra_metadata or {}),
                                    "batch_size": len(batch),
                                },
                            )
                    except Exception as tracking_error:
                        print(f"[Embedding] Warning: failed to record batch cost: {tracking_error}")
                batch_embeddings = [item.embedding for item in response.data]
                
                embeddings.extend(batch_embeddings)
            
            except Exception as e:
                print(f"[Embedding] Error in batch {i//batch_size + 1}: {e}")
                # Continue with remaining batches
                continue
        
        return embeddings
    
    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of embeddings produced by this service.
        
        Returns:
            Dimension size (e.g., 1536 for text-embedding-3-small)
        """
        return 1536


# Singleton instance (will be created on first import).
try:
    embedding_service = EmbeddingService()
except Exception as e:
    print(f"[Embedding] Warning: Could not initialize embedding service: {e}")
    print("[Embedding] Vector search will be disabled until configuration is fixed")
    embedding_service = None

