"""
LLM Configuration Router - endpoints for managing LLM provider and model selection.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

import sys
from pathlib import Path

# Add backend directory to path for imports
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from models.llm_models import (
    AVAILABLE_MODELS,
    LLMProvider,
    get_models_by_provider,
    get_model_by_id,
    get_default_model,
)
from routers.auth import get_current_user
from routers.users import get_current_db_user, require_admin
from postgres.models.user import User
from postgres.session import get_db
from services.ai_model_policy import (
    WORKLOADS,
    get_policy,
    provider_is_configured,
    save_policy,
)
from services.llm_service import llm_service

router = APIRouter(prefix="/api/llm-config", tags=["llm-config"])


class LLMConfigResponse(BaseModel):
    """Response model for LLM configuration."""
    provider: str
    model_id: str
    model_name: str
    server: str


class ModelInfoResponse(BaseModel):
    """Response model for model information."""
    id: str
    name: str
    provider: str
    description: str
    pros: list[str]
    cons: list[str]
    context_window: Optional[int] = None
    parameters: Optional[str] = None
    supports_agent: bool = True
    supports_structured_output: bool = True
    provider_configured: bool = False


class ModelsListResponse(BaseModel):
    """Response model for available models."""
    models: list[ModelInfoResponse]
    providers: list[str]


class SetLLMConfigRequest(BaseModel):
    """Request model for setting LLM configuration."""
    provider: str
    model_id: str


class WorkloadModelConfig(BaseModel):
    provider: str
    model_id: str


class AIModelPolicyResponse(BaseModel):
    revision: int
    configuration: dict[str, WorkloadModelConfig]
    workloads: dict[str, dict[str, str]]
    providers: dict[str, bool]


class UpdateAIModelPolicyRequest(BaseModel):
    revision: int | None = None
    configuration: dict[str, WorkloadModelConfig]


@router.get("/models", response_model=ModelsListResponse)
async def get_available_models(
    provider: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """
    Get all available LLM models, optionally filtered by provider.
    
    Args:
        provider: Optional cloud provider filter
        user: Current authenticated user
    """
    try:
        if provider:
            try:
                provider_enum = LLMProvider(provider.lower())
                models = get_models_by_provider(provider_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid provider: {provider}")
        else:
            models = AVAILABLE_MODELS
        
        return ModelsListResponse(
            models=[
                ModelInfoResponse(
                    **model.to_dict(),
                    provider_configured=provider_is_configured(model.provider.value),
                )
                for model in models
            ],
            providers=[p.value for p in LLMProvider],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/policy", response_model=AIModelPolicyResponse)
def get_ai_model_policy(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_db_user),
):
    configuration, revision = get_policy(db)
    return AIModelPolicyResponse(
        revision=revision,
        configuration=configuration,
        workloads=WORKLOADS,
        providers={provider.value: provider_is_configured(provider.value, db) for provider in LLMProvider},
    )


@router.put("/policy", response_model=AIModelPolicyResponse)
def update_ai_model_policy(
    request: UpdateAIModelPolicyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        record = save_policy(
            db,
            configuration={key: value.model_dump() for key, value in request.configuration.items()},
            expected_revision=request.revision,
            updated_by=current_user.email,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AIModelPolicyResponse(
        revision=record.revision,
        configuration=record.configuration,
        workloads=WORKLOADS,
        providers={provider.value: provider_is_configured(provider.value, db) for provider in LLMProvider},
    )


@router.get("/current", response_model=LLMConfigResponse)
async def get_current_config(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_db_user),
):
    """
    Get the current LLM configuration.
    
    Args:
        user: Current authenticated user
    """
    try:
        configuration, _ = get_policy(db)
        current_provider = configuration["chat"]["provider"]
        current_model_id = configuration["chat"]["model_id"]
        model = get_model_by_id(current_model_id)
        
        if not model:
            # Fallback to default
            provider_enum = LLMProvider(current_provider)
            model = get_default_model(provider_enum)
        
        server = f"{current_provider.title()} (remote)"
        
        return LLMConfigResponse(
            provider=current_provider,
            model_id=current_model_id or model.id,
            model_name=model.name,
            server=server,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/set", response_model=LLMConfigResponse)
async def set_llm_config(
    request: SetLLMConfigRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Set the LLM provider and model.
    
    Args:
        request: Configuration request with provider and model_id
        user: Current authenticated user
    """
    try:
        # Validate provider
        try:
            provider_enum = LLMProvider(request.provider.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid provider: {request.provider}")
        
        # Validate model
        model = get_model_by_id(request.model_id)
        if not model:
            raise HTTPException(status_code=400, detail=f"Invalid model ID: {request.model_id}")
        
        # Verify model matches provider
        if model.provider != provider_enum:
            raise HTTPException(
                status_code=400,
                detail=f"Model {request.model_id} does not belong to provider {request.provider}"
            )
        
        configuration, revision = get_policy(db)
        configuration["chat"] = {
            "provider": request.provider.lower(),
            "model_id": request.model_id,
        }
        save_policy(
            db,
            configuration=configuration,
            expected_revision=revision,
            updated_by=current_user.email,
        )
        # Keep request-independent legacy callers aligned in this process.
        llm_service.set_config(request.provider.lower(), request.model_id)
        
        server = f"{request.provider.title()} (remote)"
        
        return LLMConfigResponse(
            provider=request.provider.lower(),
            model_id=request.model_id,
            model_name=model.name,
            server=server,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ConfidenceThresholdResponse(BaseModel):
    """Response model for confidence threshold."""
    threshold: float


class SetConfidenceThresholdRequest(BaseModel):
    """Request model for setting confidence threshold."""
    threshold: float


@router.get("/confidence-threshold", response_model=ConfidenceThresholdResponse)
async def get_confidence_threshold(
    user: dict = Depends(get_current_user),
):
    """
    Get the current confidence threshold for vector search.
    
    Args:
        user: Current authenticated user
    """
    try:
        from config import VECTOR_SEARCH_CONFIDENCE_THRESHOLD
        return ConfidenceThresholdResponse(threshold=VECTOR_SEARCH_CONFIDENCE_THRESHOLD)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/confidence-threshold", response_model=ConfidenceThresholdResponse)
async def set_confidence_threshold(
    request: SetConfidenceThresholdRequest,
    user: dict = Depends(get_current_user),
):
    """
    Set the confidence threshold for vector search.
    
    Args:
        request: Request with threshold value (0.0-1.0)
        user: Current authenticated user
    """
    try:
        if not (0.0 <= request.threshold <= 5.0):
            raise HTTPException(status_code=400, detail="Confidence threshold must be between 0.0 and 5.0")
        
        # Update the environment variable for future requests
        import os
        os.environ["VECTOR_SEARCH_CONFIDENCE_THRESHOLD"] = str(request.threshold)
        
        # Update the config module directly for immediate effect
        import config
        config.VECTOR_SEARCH_CONFIDENCE_THRESHOLD = request.threshold
        
        return ConfidenceThresholdResponse(threshold=request.threshold)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

