"""
System Logs Router - endpoints for viewing system logs.
"""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel

from services.system_log_service import system_log_service, LogType, LogOrigin
from routers.auth import get_current_user

router = APIRouter(prefix="/api/system-logs", tags=["system-logs"])


class LogEntry(BaseModel):
    """Log entry model."""
    timestamp: str
    type: str
    origin: str
    action: str
    user: Optional[str] = None
    success: bool
    error: Optional[str] = None
    details: dict


class LogsResponse(BaseModel):
    """Response model for logs endpoint."""
    logs: List[LogEntry]
    total: int
    limit: int
    offset: int


class LogStatisticsResponse(BaseModel):
    """Response model for log statistics."""
    total_logs: int
    by_type: dict
    by_origin: dict
    success_rate: float
    successful: int
    failed: int


@router.get("", response_model=LogsResponse)
async def get_logs(
    log_type: Optional[str] = Query(None, description="Filter by log type (comma-separated for multiple)"),
    origin: Optional[str] = Query(None, description="Filter by origin (comma-separated for multiple)"),
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of logs"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    user: Optional[str] = Query(None, description="Filter by user"),
    success_only: Optional[bool] = Query(None, description="Filter by success status"),
    current_user: dict = Depends(get_current_user),
):
    """
    Get system logs with filtering.
    
    Args:
        log_type: Filter by log type (ai_assistant, graph_operation, case_management, etc.)
        origin: Filter by origin (frontend, backend, ingestion, system)
        start_time: Filter logs after this time (ISO format)
        end_time: Filter logs before this time (ISO format)
        limit: Maximum number of logs to return
        offset: Offset for pagination
        user: Filter by username
        success_only: Filter by success status
        current_user: Current authenticated user
    """
    try:
        # Parse log types (support comma-separated list)
        parsed_log_types = None
        if log_type:
            log_type_list = [t.strip() for t in log_type.split(',') if t.strip()]
            if log_type_list:
                try:
                    parsed_log_types = [LogType(t) for t in log_type_list]
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=f"Invalid log type: {str(e)}")
        
        # Parse origins (support comma-separated list)
        parsed_origins = None
        if origin:
            origin_list = [o.strip() for o in origin.split(',') if o.strip()]
            if origin_list:
                try:
                    parsed_origins = [LogOrigin(o) for o in origin_list]
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=f"Invalid origin: {str(e)}")
        
        # Parse times
        parsed_start_time = None
        if start_time:
            try:
                parsed_start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid start_time format: {start_time}")
        
        parsed_end_time = None
        if end_time:
            try:
                parsed_end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid end_time format: {end_time}")
        
        result = system_log_service.get_logs(
            log_type=parsed_log_types[0] if parsed_log_types and len(parsed_log_types) == 1 else None,
            log_types=parsed_log_types if parsed_log_types and len(parsed_log_types) > 1 else None,
            origin=parsed_origins[0] if parsed_origins and len(parsed_origins) == 1 else None,
            origins=parsed_origins if parsed_origins and len(parsed_origins) > 1 else None,
            start_time=parsed_start_time,
            end_time=parsed_end_time,
            limit=limit,
            offset=offset,
            user=user,
            success_only=success_only,
        )
        
        return LogsResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics", response_model=LogStatisticsResponse)
async def get_log_statistics(current_user: dict = Depends(get_current_user)):
    """
    Get log statistics.
    
    Args:
        current_user: Current authenticated user
    """
    try:
        stats = system_log_service.get_log_statistics()
        return LogStatisticsResponse(**stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("")
async def clear_logs(current_user: dict = Depends(get_current_user)):
    """
    Clear all system logs.
    
    Args:
        current_user: Current authenticated user
    """
    try:
        system_log_service.clear_logs()
        return {"message": "Logs cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

