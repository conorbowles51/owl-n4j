"""
LLM Model Configuration - defines available models with metadata.
"""

from typing import Dict, List, Optional
from enum import Enum


class LLMProvider(str, Enum):
    """LLM Provider types."""
    OPENAI = "openai"
    OLLAMA = "ollama"


class LLMModel:
    """Model configuration with metadata."""
    
    def __init__(
        self,
        id: str,
        name: str,
        provider: LLMProvider,
        description: str,
        pros: List[str],
        cons: List[str],
        context_window: Optional[int] = None,
        parameters: Optional[str] = None,
    ):
        self.id = id
        self.name = name
        self.provider = provider
        self.description = description
        self.pros = pros
        self.cons = cons
        self.context_window = context_window
        self.parameters = parameters  # e.g., "7B", "32B", "70B"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider.value,
            "description": self.description,
            "pros": self.pros,
            "cons": self.cons,
            "context_window": self.context_window,
            "parameters": self.parameters,
        }


# Available models
AVAILABLE_MODELS = [
    # Ollama Models
    LLMModel(
        id="qwen2.5:32b-instruct",
        name="Qwen2.5 32B Instruct",
        provider=LLMProvider.OLLAMA,
        description="Large instruction-tuned model with strong reasoning capabilities and multilingual support.",
        pros=[
            "Excellent reasoning and analysis capabilities",
            "Strong multilingual support (English, Chinese, and more)",
            "Good instruction following",
            "Large context window",
            "Runs locally via Ollama (privacy-preserving)",
        ],
        cons=[
            "Requires significant RAM (32GB+ recommended)",
            "Slower than smaller models",
            "Higher memory usage",
        ],
        context_window=32768,
        parameters="32B",
    ),
    LLMModel(
        id="qwen2.5:14b-instruct",
        name="Qwen2.5 14B Instruct",
        provider=LLMProvider.OLLAMA,
        description="Mid-sized instruction-tuned model balancing performance and resource usage.",
        pros=[
            "Good balance of performance and speed",
            "Strong reasoning capabilities",
            "Multilingual support",
            "More efficient than 32B version",
            "Runs locally via Ollama",
        ],
        cons=[
            "Less capable than 32B for complex tasks",
            "Still requires substantial RAM (16GB+ recommended)",
        ],
        context_window=32768,
        parameters="14B",
    ),
    LLMModel(
        id="qwen2.5:7b-instruct",
        name="Qwen2.5 7B Instruct",
        provider=LLMProvider.OLLAMA,
        description="Smaller, faster model suitable for less resource-intensive environments.",
        pros=[
            "Fast inference speed",
            "Lower memory requirements (8GB+ recommended)",
            "Good for quick responses",
            "Runs locally via Ollama",
        ],
        cons=[
            "Less capable for complex reasoning",
            "May struggle with nuanced analysis",
        ],
        context_window=32768,
        parameters="7B",
    ),
    LLMModel(
        id="llama3:70b",
        name="Llama 3 70B",
        provider=LLMProvider.OLLAMA,
        description="Very large model with excellent general capabilities.",
        pros=[
            "Excellent general knowledge",
            "Strong reasoning abilities",
            "Large context window",
            "Runs locally via Ollama",
        ],
        cons=[
            "Very high memory requirements (64GB+ recommended)",
            "Slow inference speed",
            "May be overkill for many tasks",
        ],
        context_window=8192,
        parameters="70B",
    ),
    LLMModel(
        id="llama3:8b",
        name="Llama 3 8B",
        provider=LLMProvider.OLLAMA,
        description="Efficient model with good performance for most tasks.",
        pros=[
            "Good balance of capability and speed",
            "Lower memory requirements",
            "Fast inference",
            "Runs locally via Ollama",
        ],
        cons=[
            "Less capable than larger models",
            "May need more guidance for complex tasks",
        ],
        context_window=8192,
        parameters="8B",
    ),
    LLMModel(
        id="mannix/dolphin-2.9-llama3-8b",
        name="Dolphin 2.9 Llama 3 8B",
        provider=LLMProvider.OLLAMA,
        description="Fine-tuned version of Llama 3 8B optimized for instruction following and conversation.",
        pros=[
            "Excellent instruction following",
            "Optimized for conversational tasks",
            "Good balance of capability and speed",
            "Lower memory requirements (8GB+ recommended)",
            "Fast inference",
            "Runs locally via Ollama",
        ],
        cons=[
            "Less capable than larger models for complex reasoning",
            "Based on 8B model, so limitations of base model apply",
        ],
        context_window=8192,
        parameters="8B",
    ),
    
    # OpenAI Models
    LLMModel(
        id="gpt-5",
        name="GPT-5",
        provider=LLMProvider.OPENAI,
        description="Next-generation OpenAI model with enhanced reasoning, multimodal capabilities, and massive context window.",
        pros=[
            "State-of-the-art reasoning and generation",
            "Multimodal input/output (text, image, audio)",
            "Massive context window (256K tokens)",
            "Improved speed and efficiency",
            "Best-in-class instruction following",
        ],
        cons=[
            "Requires OpenAI API key",
            "Higher API costs",
            "Requires internet connection",
            "Data sent to external service",
        ],
        context_window=256000,
        parameters="N/A",
    ),
    LLMModel(
        id="gpt-4o",
        name="GPT-4o",
        provider=LLMProvider.OPENAI,
        description="OpenAI's most advanced model with multimodal capabilities and excellent reasoning.",
        pros=[
            "State-of-the-art reasoning and analysis",
            "Excellent instruction following",
            "Very large context window (128K tokens)",
            "Fast inference",
            "Multimodal capabilities",
        ],
        cons=[
            "Requires internet connection",
            "API costs per request",
            "Data sent to external service",
            "Requires OpenAI API key",
        ],
        context_window=128000,
        parameters="N/A",
    ),
    LLMModel(
        id="gpt-4-turbo",
        name="GPT-4 Turbo",
        provider=LLMProvider.OPENAI,
        description="High-performance model with large context window and strong capabilities.",
        pros=[
            "Excellent reasoning capabilities",
            "Large context window (128K tokens)",
            "Fast inference",
            "Strong instruction following",
        ],
        cons=[
            "Requires internet connection",
            "API costs per request",
            "Data sent to external service",
            "Requires OpenAI API key",
        ],
        context_window=128000,
        parameters="N/A",
    ),
    LLMModel(
        id="gpt-3.5-turbo",
        name="GPT-3.5 Turbo",
        provider=LLMProvider.OPENAI,
        description="Cost-effective model with good performance for most tasks.",
        pros=[
            "Lower API costs",
            "Fast inference",
            "Good for straightforward tasks",
            "Large context window (16K tokens)",
        ],
        cons=[
            "Less capable than GPT-4",
            "May struggle with complex reasoning",
            "Requires internet connection",
            "Data sent to external service",
        ],
        context_window=16384,
        parameters="N/A",
    ),
]


def get_models_by_provider(provider: LLMProvider) -> List[LLMModel]:
    """Get all models for a specific provider."""
    return [model for model in AVAILABLE_MODELS if model.provider == provider]


def get_model_by_id(model_id: str) -> Optional[LLMModel]:
    """Get a model by its ID."""
    for model in AVAILABLE_MODELS:
        if model.id == model_id:
            return model
    return None


def get_default_model(provider: LLMProvider) -> LLMModel:
    """Get the default model for a provider."""
    if provider == LLMProvider.OLLAMA:
        return get_model_by_id("qwen2.5:32b-instruct") or AVAILABLE_MODELS[0]
    else:
        return get_model_by_id("gpt-4o") or AVAILABLE_MODELS[-1]

