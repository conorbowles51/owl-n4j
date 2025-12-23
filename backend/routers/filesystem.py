"""
File System Router

API endpoints for browsing the file system starting from the data folder.
"""

from typing import List, Optional
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from config import BASE_DIR
from routers.auth import get_current_user

router = APIRouter(prefix="/api/filesystem", tags=["filesystem"])

# Root directory for file browsing - start from ingestion/data
# For case-specific browsing, we'll use ingestion/data/{case_id}
FILESYSTEM_ROOT = BASE_DIR / "ingestion" / "data"


class FileSystemItem(BaseModel):
    """Represents a file or directory in the file system."""
    name: str
    path: str  # Relative path from root
    type: str  # "file" or "directory"
    size: Optional[int] = None  # File size in bytes (None for directories)
    modified: Optional[str] = None  # Last modified timestamp


class FileSystemListResponse(BaseModel):
    """Response containing file system items."""
    items: List[FileSystemItem]
    current_path: str
    root_path: str


@router.get("/list", response_model=FileSystemListResponse)
async def list_directory(
    case_id: Optional[str] = None,
    path: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """
    List files and directories in a given path for a specific case.
    
    Args:
        case_id: Case ID to filter by (required for case-specific browsing)
        path: Relative path from case root (e.g., "subfolder" or "subfolder/nested")
              If None, lists the case root directory.
    
    Returns:
        List of files and directories in the specified path
    """
    try:
        if not case_id:
            raise HTTPException(status_code=400, detail="case_id is required")
        
        # Case-specific root: ingestion/data/{case_id}
        case_root = FILESYSTEM_ROOT / case_id
        
        # Normalize path
        path_normalized = path.strip().strip('/') if path and path.strip() else ''
        
        # Build target path
        if path_normalized:
            target_path = (case_root / path_normalized).resolve()
            
            # Security check: ensure path is within case_root
            try:
                target_path.relative_to(case_root.resolve())
            except ValueError:
                raise HTTPException(status_code=403, detail="Path outside case directory")
        else:
            target_path = case_root.resolve()
        
        # Create case root directory if it doesn't exist (but not subdirectories)
        if not case_root.exists() and not path_normalized:
            try:
                case_root.mkdir(parents=True, exist_ok=True)
            except OSError:
                # If we can't create it, return empty list instead of error
                return FileSystemListResponse(
                    items=[],
                    current_path='',
                    root_path=str(case_root),
                )
        
        if not target_path.exists():
            # If it's a subdirectory that doesn't exist, return 404
            # If it's the case root that doesn't exist, return empty list
            if path_normalized:
                raise HTTPException(status_code=404, detail="Path not found")
            else:
                return FileSystemListResponse(
                    items=[],
                    current_path='',
                    root_path=str(case_root),
                )
        
        if not target_path.is_dir():
            raise HTTPException(status_code=400, detail="Path is not a directory")
        
        items = []
        
        # List directory contents
        for item_path in sorted(target_path.iterdir()):
            # Skip hidden files/directories
            if item_path.name.startswith('.'):
                continue
            
            try:
                if item_path.is_dir():
                    item_type = "directory"
                    size = None
                else:
                    item_type = "file"
                    size = item_path.stat().st_size
                
                # Get relative path from case root (not FILESYSTEM_ROOT)
                relative_path = item_path.relative_to(case_root)
                
                # Get modification time
                modified = datetime.fromtimestamp(item_path.stat().st_mtime).isoformat()
                
                items.append(FileSystemItem(
                    name=item_path.name,
                    path=str(relative_path).replace('\\', '/'),
                    type=item_type,
                    size=size,
                    modified=modified,
                ))
            except (OSError, PermissionError):
                # Skip items we can't access
                continue
        
        # Get current relative path from case root
        current_relative = target_path.relative_to(case_root)
        current_path_str = str(current_relative).replace('\\', '/') if str(current_relative) != '.' else ''
        
        return FileSystemListResponse(
            items=items,
            current_path=current_path_str,
            root_path=str(case_root),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/read")
async def read_file(
    case_id: str,
    path: str,
    user: dict = Depends(get_current_user),
):
    """
    Read a file's contents (for text files only).
    
    Args:
        case_id: Case ID
        path: Relative path from case root (e.g., "file.txt" or "subfolder/file.txt")
    
    Returns:
        File contents as text
    """
    try:
        if not case_id:
            raise HTTPException(status_code=400, detail="case_id is required")
        
        # Case-specific root: ingestion/data/{case_id}
        case_root = FILESYSTEM_ROOT / case_id
        
        # Build target path
        path = path.strip().strip('/')
        target_path = (case_root / path).resolve()
        
        # Security check: ensure path is within case_root
        try:
            target_path.relative_to(case_root.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Path outside case directory")
        
        if not target_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        if target_path.is_dir():
            raise HTTPException(status_code=400, detail="Path is a directory, not a file")
        
        # Only allow reading text files (safety measure)
        text_extensions = {'.txt', '.md', '.json', '.csv', '.log', '.py', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.xml', '.yaml', '.yml', '.rtf', '.sri'}
        if target_path.suffix.lower() not in text_extensions:
            raise HTTPException(status_code=400, detail="File type not allowed for reading")
        
        # Read file contents
        try:
            content = target_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            # Try with error handling
            content = target_path.read_text(encoding='utf-8', errors='replace')
        
        return {
            "path": path,
            "content": content,
            "size": target_path.stat().st_size,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

