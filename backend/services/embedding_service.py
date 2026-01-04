"""
Embedding generation service.

Supports both OpenAI and local (Ollama) models for generating text embeddings.
"""

from typing import List, Optional
import os

# Try to import OpenAI (optional)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Try to import Ollama (optional)
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

from config import EMBEDDING_PROVIDER, EMBEDDING_MODEL, OPENAI_API_KEY, LLM_PROVIDER


class EmbeddingService:
    """Service for generating text embeddings."""
    
    def __init__(self):
        # Use embedding provider from config, or fall back to LLM provider
        self.provider = (EMBEDDING_PROVIDER or LLM_PROVIDER or "ollama").lower()
        self.model = EMBEDDING_MODEL
        
        # If no explicit embedding model set, use defaults based on provider
        if not self.model:
            if self.provider == "ollama":
                self.model = "nomic-embed-text"  # Common Ollama embedding model
            elif self.provider == "openai":
                self.model = "text-embedding-3-small"
        
        if self.provider == "openai":
            if not OPENAI_AVAILABLE:
                raise ImportError("OpenAI package not installed. Install with: pip install openai")
            if not OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY not set in environment variables")
            self.client = OpenAI(api_key=OPENAI_API_KEY)
            self._validate_openai_model()
        
        elif self.provider == "ollama":
            if not OLLAMA_AVAILABLE:
                raise ImportError("Ollama package not installed. Install with: pip install ollama")
            self.client = ollama
            self._validate_ollama_model()
        
        else:
            raise ValueError(f"Unsupported embedding provider: {self.provider}. Use 'openai' or 'ollama'")
    
    def _validate_openai_model(self) -> None:
        """Validate that the OpenAI model is available."""
        # OpenAI models are validated on first use, so we'll just log
        print(f"[Embedding] Using OpenAI model: {self.model}")
    
    def _validate_ollama_model(self) -> None:
        """Validate that the Ollama model is available."""
        try:
            # Try to pull the model if it doesn't exist
            models = self.client.list()
            model_names = [m["name"] for m in models.get("models", [])]
            
            if self.model not in model_names:
                print(f"[Embedding] Model {self.model} not found. Attempting to pull...")
                self.client.pull(self.model)
                print(f"[Embedding] Model {self.model} pulled successfully")
        except Exception as e:
            print(f"[Embedding] Warning: Could not validate Ollama model {self.model}: {e}")
    
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
            if self.provider == "openai":
                response = self.client.embeddings.create(
                    model=self.model,
                    input=text
                )
                return response.data[0].embedding
            
            elif self.provider == "ollama":
                response = self.client.embeddings(
                    model=self.model,
                    prompt=text
                )
                return response["embedding"]
            
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")
        
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
                if self.provider == "openai":
                    # OpenAI supports batch requests (up to 2048 texts)
                    response = self.client.embeddings.create(
                        model=self.model,
                        input=batch
                    )
                    batch_embeddings = [item.embedding for item in response.data]
                else:
                    # Ollama: process one by one (no batch support)
                    batch_embeddings = [
                        self.generate_embedding(text) for text in batch
                    ]
                
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
        # Common dimensions
        if self.provider == "openai":
            if "text-embedding-3-small" in self.model:
                return 1536
            elif "text-embedding-3-large" in self.model:
                return 3072
            elif "text-embedding-ada-002" in self.model:
                return 1536
            else:
                # Default for unknown OpenAI models
                return 1536
        elif self.provider == "ollama":
            # Ollama embedding dimensions vary by model
            # Common: nomic-embed-text (768), mxbai-embed-large (1024)
            return 768  # Default, may vary
        else:
            return 1536  # Safe default


# Singleton instance (will be created on first import)
# Note: This will raise an error if provider is misconfigured
try:
    embedding_service = EmbeddingService()
except Exception as e:
    print(f"[Embedding] Warning: Could not initialize embedding service: {e}")
    print("[Embedding] Vector search will be disabled until configuration is fixed")
    embedding_service = None

