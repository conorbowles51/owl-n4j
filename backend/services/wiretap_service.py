"""
Wiretap Processing Service

Handles wiretap folder detection and processing.
"""

import asyncio
from pathlib import Path
from typing import Callable, Dict, Optional


def check_wiretap_suitable(folder_path: Path) -> Dict:
    """
    Check if a folder is suitable for wiretap processing.
    
    A folder is suitable if it contains:
    - At least one audio file (.wav, .mp3, .m4a, .flac)
    - Optionally .sri metadata files
    - Optionally .rtf files
    
    Args:
        folder_path: Path to the folder to check
    
    Returns:
        Dict with:
            - suitable: bool
            - has_audio: bool
            - has_sri: bool
            - has_rtf: bool
            - audio_files: List[str]
            - sri_files: List[str]
            - rtf_files: List[str]
            - message: str
    """
    if not folder_path.exists() or not folder_path.is_dir():
        return {
            "suitable": False,
            "has_audio": False,
            "has_sri": False,
            "has_rtf": False,
            "audio_files": [],
            "sri_files": [],
            "rtf_files": [],
            "message": "Folder does not exist or is not a directory"
        }
    
    audio_files = []
    sri_files = []
    rtf_files = []
    
    for file_path in folder_path.iterdir():
        if file_path.is_file():
            name_lower = file_path.name.lower()
            
            if name_lower.endswith(('.wav', '.mp3', '.m4a', '.flac')):
                audio_files.append(file_path.name)
            elif name_lower.endswith('.sri'):
                sri_files.append(file_path.name)
            elif name_lower.endswith('.rtf'):
                rtf_files.append(file_path.name)
    
    has_audio = len(audio_files) > 0
    has_sri = len(sri_files) > 0
    has_rtf = len(rtf_files) > 0
    
    suitable = has_audio  # At minimum, need audio files
    
    if suitable:
        message = "Folder is suitable for wiretap processing"
        if not has_sri:
            message += " (missing .sri metadata file)"
        if not has_rtf:
            message += " (missing .rtf interpretation file)"
    else:
        message = "Folder is not suitable: no audio files found"
    
    return {
        "suitable": suitable,
        "has_audio": has_audio,
        "has_sri": has_sri,
        "has_rtf": has_rtf,
        "audio_files": audio_files,
        "sri_files": sri_files,
        "rtf_files": rtf_files,
        "message": message
    }


async def process_wiretap_folder_async(
    folder_path: Path,
    case_id: str,
    whisper_model: str = "base",
    log_callback: Optional[Callable[[str], None]] = None
) -> Dict:
    """
    Legacy wiretap folder processing entrypoint.
    
    This version uses asyncio to avoid blocking the event loop.
    
    Args:
        folder_path: Path to wiretap folder
        case_id: Case ID for tracking
        whisper_model: Retained for request compatibility.
        log_callback: Optional callback function(message: str) for logs
    
    Returns:
        Dict with processing result
    """
    if not folder_path.exists() or not folder_path.is_dir():
        return {
            "success": False,
            "error": f"Folder does not exist: {folder_path}"
        }
    
    # Check if suitable
    check_result = check_wiretap_suitable(folder_path)
    if not check_result["suitable"]:
        return {
            "success": False,
            "error": check_result["message"]
        }
    
    if log_callback:
        log_callback(
            "Legacy wiretap folder processing has been retired. "
            "Upload audio files through evidence-engine processing instead."
        )

    return {
        "success": False,
        "error": (
            "Legacy wiretap folder processing has been retired. "
            "Upload audio files through evidence-engine processing instead."
        ),
    }


def process_wiretap_folder(
    folder_path: Path,
    case_id: str,
    whisper_model: str = "base",
    log_callback: Optional[Callable[[str], None]] = None
) -> Dict:
    """
    Synchronous wrapper for async wiretap processing.
    This is kept for backward compatibility but should use the async version in async contexts.
    """
    # Run the async function in a new event loop
    # This is needed when called from sync code
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already in an async context, we need to run in a thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    process_wiretap_folder_async(folder_path, case_id, whisper_model, log_callback)
                )
                return future.result()
        else:
            return loop.run_until_complete(
                process_wiretap_folder_async(folder_path, case_id, whisper_model, log_callback)
            )
    except RuntimeError:
        # No event loop, create a new one
        return asyncio.run(
            process_wiretap_folder_async(folder_path, case_id, whisper_model, log_callback)
        )

