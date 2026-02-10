"""
Cost Tracking Service - tracks OpenAI API usage and costs.
"""

from typing import Optional, Dict, Any
from datetime import datetime
import uuid

from sqlalchemy.orm import Session
from postgres.session import get_db
from postgres.models.cost_record import CostRecord, CostJobType


# OpenAI pricing per 1M tokens (as of 2024)
# Format: {model_id: (prompt_price_per_1M, completion_price_per_1M)}
OPENAI_PRICING = {
    "gpt-4o": (2.50, 10.00),  # $2.50/$10.00 per 1M tokens
    "gpt-4o-mini": (0.15, 0.60),  # $0.15/$0.60 per 1M tokens
    "gpt-4": (30.00, 60.00),  # $30.00/$60.00 per 1M tokens
    "gpt-4-turbo": (10.00, 30.00),  # $10.00/$30.00 per 1M tokens
    "gpt-3.5-turbo": (0.50, 1.50),  # $0.50/$1.50 per 1M tokens
    "o1-preview": (15.00, 60.00),  # $15.00/$60.00 per 1M tokens
    "o1-mini": (3.00, 12.00),  # $3.00/$12.00 per 1M tokens
    "o3": (15.00, 60.00),  # Estimated, same as o1
    "gpt-5": (30.00, 120.00),  # Estimated pricing
    "gpt-5-mini": (3.00, 12.00),  # Estimated pricing
    "gpt-5.1": (15.00, 60.00),  # Estimated pricing
    "gpt-5.2": (30.00, 120.00),  # Estimated pricing
    "gpt-4.1": (5.00, 15.00),  # Estimated pricing
}

# Default pricing for unknown models (use gpt-4o-mini as fallback)
DEFAULT_PRICING = (0.15, 0.60)


def get_model_pricing(model_id: str) -> tuple[float, float]:
    """
    Get pricing for a model.
    
    Args:
        model_id: OpenAI model ID
        
    Returns:
        Tuple of (prompt_price_per_1M, completion_price_per_1M)
    """
    # Check exact match first
    if model_id in OPENAI_PRICING:
        return OPENAI_PRICING[model_id]
    
    # Check for model variants (e.g., "gpt-4o-2024-08-06" -> "gpt-4o")
    for base_model, pricing in OPENAI_PRICING.items():
        if model_id.startswith(base_model):
            return pricing
    
    # Default fallback
    return DEFAULT_PRICING


def calculate_cost(
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """
    Calculate cost in USD for OpenAI API usage.
    
    Args:
        model_id: OpenAI model ID
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        
    Returns:
        Cost in USD
    """
    if prompt_tokens is None or completion_tokens is None:
        return 0.0
    
    prompt_price, completion_price = get_model_pricing(model_id)
    
    prompt_cost = (prompt_tokens / 1_000_000) * prompt_price
    completion_cost = (completion_tokens / 1_000_000) * completion_price
    
    return prompt_cost + completion_cost


def record_cost(
    job_type: CostJobType,
    provider: str,
    model_id: str,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
    case_id: Optional[uuid.UUID] = None,
    user_id: Optional[uuid.UUID] = None,
    description: Optional[str] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
    db: Optional[Session] = None,
) -> CostRecord:
    """
    Record a cost entry in the database.
    
    Args:
        job_type: Type of job (INGESTION or AI_ASSISTANT)
        provider: Provider name ("openai" or "ollama")
        model_id: Model ID
        prompt_tokens: Number of prompt tokens (OpenAI only)
        completion_tokens: Number of completion tokens (OpenAI only)
        total_tokens: Total tokens (OpenAI only)
        case_id: Optional case ID
        user_id: Optional user ID
        description: Optional description
        extra_metadata: Optional extra metadata dictionary
        db: Optional database session (if None, creates a new one)
        
    Returns:
        Created CostRecord
    """
    # Only track costs for OpenAI
    if provider != "openai":
        # For Ollama, create a record with 0 cost
        cost_usd = 0.0
    else:
        # Calculate cost for OpenAI
        cost_usd = calculate_cost(model_id, prompt_tokens or 0, completion_tokens or 0)
    
    # Use provided session or create a new one
    if db is None:
        db_gen = get_db()
        db = next(db_gen)
        should_close = True
    else:
        should_close = False
    
    try:
        cost_record = CostRecord(
            job_type=job_type.value,
            provider=provider,
            model_id=model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            case_id=case_id,
            user_id=user_id,
            description=description,
            extra_metadata=extra_metadata,
        )
        
        db.add(cost_record)
        db.commit()
        db.refresh(cost_record)
        
        return cost_record
    finally:
        if should_close:
            db.close()


# Singleton instance
cost_tracking_service = {
    "record_cost": record_cost,
    "calculate_cost": calculate_cost,
    "get_model_pricing": get_model_pricing,
}
