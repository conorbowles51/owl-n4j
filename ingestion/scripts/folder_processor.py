"""
Folder Processor module - profile-based folder processing.

Processes folders according to user-defined profiles, handling file relationships,
transcription, translation, and metadata extraction before ingestion.
"""

import fnmatch
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
import os

from profile_loader import load_profile, get_folder_processing_config
from audio_processor import (
    parse_sri_file,
    parse_rtf_file,
)
from logging_utils import log_progress, log_error, log_warning

# Try to import OpenAI client
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None

# Import config for OpenAI API key
from config import OPENAI_API_KEY


def match_file_pattern(filename: str, pattern: str) -> bool:
    """
    Check if a filename matches a pattern (supports comma-separated glob patterns).
    
    Args:
        filename: Filename to check
        pattern: Comma-separated glob patterns (e.g., "*.wav,*.mp3")
    
    Returns:
        True if filename matches any pattern
    """
    patterns = [p.strip() for p in pattern.split(",")]
    for p in patterns:
        if fnmatch.fnmatch(filename.lower(), p.lower()):
            return True
    return False


def find_files_by_role(folder_path: Path, file_rules: List[Dict]) -> Dict[str, List[Path]]:
    """
    Find files in folder matching each rule's pattern.
    
    Args:
        folder_path: Path to folder
        file_rules: List of file rule dicts with 'pattern' and 'role' keys
    
    Returns:
        Dict mapping role -> list of matching file paths
    """
    role_files = {}
    
    for rule in file_rules:
        role = rule.get("role", "unknown")
        pattern = rule.get("pattern", "")
        
        if role not in role_files:
            role_files[role] = []
        
        if not folder_path.exists() or not folder_path.is_dir():
            continue
        
        for file_path in folder_path.iterdir():
            if file_path.is_file() and match_file_pattern(file_path.name, pattern):
                role_files[role].append(file_path)
    
    return role_files


def transcribe_audio_openai(
    audio_path: Path,
    language: Optional[str] = None,
    task: str = "transcribe"
) -> str:
    """
    Transcribe or translate audio file using OpenAI Whisper API.
    
    Args:
        audio_path: Path to audio file
        language: Language code (e.g., 'es' for Spanish, 'en' for English)
                  If None, OpenAI will auto-detect
        task: "transcribe" (transcribe in source language) or "translate" (translate to English)
    
    Returns:
        Transcribed/translated text
    """
    if not OPENAI_AVAILABLE:
        raise ImportError("OpenAI client is not available. Install with: pip install openai")
    
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not set in environment variables")
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    with open(audio_path, 'rb') as audio_file:
        if task == "translate":
            # Translate to English
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )
        else:
            # Transcribe in source language
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=language,
                response_format="text"
            )
    
    return transcript.strip() if isinstance(transcript, str) else str(transcript).strip()


def process_audio_files(
    audio_files: List[Path],
    file_rule: Dict,
    whisper_model=None,  # Kept for backward compatibility but not used
    log_callback: Optional[Callable[[str], None]] = None
) -> Dict[str, str]:
    """
    Process audio files according to rule configuration using OpenAI Whisper API.
    
    Args:
        audio_files: List of audio file paths
        file_rule: File rule dict with transcription/translation config
        whisper_model: Deprecated - kept for backward compatibility
        log_callback: Optional logging callback
    
    Returns:
        Dict with transcription results (keys like 'spanish_transcription', 'english_transcription')
    """
    results = {}
    
    if not audio_files:
        return results
    
    audio_file = audio_files[0]  # Use first audio file
    
    log_progress(f"  Processing audio file: {audio_file.name} (using OpenAI Whisper API)", log_callback)
    
    # Handle transcription
    actions = file_rule.get("actions", [])
    transcribe_languages = file_rule.get("transcribe_languages", [])
    translate_languages = file_rule.get("translate_languages", [])
    
    if "transcribe" in actions:
        for lang in transcribe_languages:
            try:
                log_progress(f"  Transcribing in {lang} using OpenAI Whisper...", log_callback)
                transcript = transcribe_audio_openai(
                    audio_file,
                    language=lang,
                    task="transcribe"
                )
                key = f"{lang}_transcription" if lang != "en" else "english_transcription"
                results[key] = transcript
                log_progress(f"  {lang.capitalize()} transcription completed ({len(transcript)} chars)", log_callback)
            except Exception as e:
                log_error(f"  Failed to transcribe in {lang}: {e}", log_callback)
    
    if "translate" in actions:
        # Translate to target languages using OpenAI Whisper
        for target_lang in translate_languages:
            try:
                log_progress(f"  Translating to {target_lang} using OpenAI Whisper...", log_callback)
                # OpenAI Whisper always translates to English
                translation = transcribe_audio_openai(
                    audio_file,
                    task="translate"
                )
                key = f"{target_lang}_translation" if target_lang != "en" else "english_transcription"
                results[key] = translation
                log_progress(f"  {target_lang.capitalize()} translation completed ({len(translation)} chars)", log_callback)
            except Exception as e:
                log_error(f"  Failed to translate to {target_lang}: {e}", log_callback)
    
    return results


def process_metadata_files(
    metadata_files: List[Path],
    file_rule: Dict,
    log_callback: Optional[Callable[[str], None]] = None
) -> Dict[str, Any]:
    """
    Process metadata files according to rule configuration.
    
    Args:
        metadata_files: List of metadata file paths
        file_rule: File rule dict with parser config
        log_callback: Optional logging callback
    
    Returns:
        Dict with extracted metadata
    """
    results = {}
    
    if not metadata_files:
        return results
    
    metadata_file = metadata_files[0]  # Use first metadata file
    parser = file_rule.get("parser", "")
    
    log_progress(f"  Processing metadata file: {metadata_file.name} (parser: {parser})", log_callback)
    
    if parser == "sri":
        try:
            metadata = parse_sri_file(metadata_file)
            results.update(metadata)
            log_progress(f"  Extracted {len(metadata)} metadata fields", log_callback)
        except Exception as e:
            log_error(f"  Failed to parse SRI file: {e}", log_callback)
    else:
        log_warning(f"  Unknown metadata parser: {parser}", log_callback)
    
    return results


def process_interpretation_files(
    interpretation_files: List[Path],
    file_rule: Dict,
    log_callback: Optional[Callable[[str], None]] = None
) -> Dict[str, Any]:
    """
    Process interpretation files (e.g., RTF) according to rule configuration.
    
    Args:
        interpretation_files: List of interpretation file paths
        file_rule: File rule dict with extraction config
        log_callback: Optional logging callback
    
    Returns:
        Dict with 'interpretation' and optionally 'participants'
    """
    results = {}
    
    if not interpretation_files:
        return results
    
    # Prefer files with 'syn' in name for RTF files
    syn_files = [f for f in interpretation_files if 'syn' in f.name.lower()]
    interpretation_file = syn_files[0] if syn_files else interpretation_files[0]
    
    parser = file_rule.get("parser", "")
    
    log_progress(f"  Processing interpretation file: {interpretation_file.name} (parser: {parser})", log_callback)
    
    if parser == "rtf":
        try:
            rtf_data = parse_rtf_file(interpretation_file)
            
            if file_rule.get("extract_interpretation", False):
                results["interpretation"] = rtf_data.get("interpretation", "")
            
            if file_rule.get("extract_participants", False):
                results["participants"] = rtf_data.get("participants", [])
            
            log_progress(f"  Extracted interpretation ({len(results.get('interpretation', ''))} chars), "
                        f"{len(results.get('participants', []))} participants", log_callback)
        except Exception as e:
            log_error(f"  Failed to parse RTF file: {e}", log_callback)
    else:
        log_warning(f"  Unknown interpretation parser: {parser}", log_callback)
    
    return results


def prepare_structured_text(
    folder_name: str,
    file_results: Dict[str, Any],
    output_format: str = "wiretap_structured"
) -> str:
    """
    Combine processed file results into structured text for ingestion.
    
    Args:
        folder_name: Name of the folder being processed
        file_results: Dict with processed file data (metadata, transcriptions, etc.)
        output_format: Format type (e.g., 'wiretap_structured')
    
    Returns:
        Structured text ready for ingestion
    """
    parts = []
    
    if output_format == "wiretap_structured":
        # Header with metadata
        parts.append("=== WIRETAP RECORDING ===")
        parts.append(f"Folder: {folder_name}")
        
        metadata = file_results.get("metadata", {})
        if metadata.get("time_of_call"):
            time_obj = metadata["time_of_call"]
            if isinstance(time_obj, datetime):
                parts.append(f"Date/Time: {time_obj.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                parts.append(f"Date/Time: {time_obj}")
        if metadata.get("input_line_id"):
            parts.append(f"Input Line ID: {metadata['input_line_id']}")
        if metadata.get("contact_id"):
            parts.append(f"Contact ID: {metadata['contact_id']}")
        if metadata.get("session_length"):
            parts.append(f"Session Length: {metadata['session_length']} seconds")
        
        parts.append("")
        
        # Participants
        participants = file_results.get("participants", [])
        if participants:
            parts.append("=== PARTICIPANTS ===")
            for participant in participants:
                parts.append(f"- {participant}")
            parts.append("")
        
        # Spanish transcription
        spanish_text = file_results.get("spanish_transcription") or file_results.get("es_transcription", "")
        if spanish_text:
            parts.append("=== SPANISH TRANSCRIPTION ===")
            parts.append(spanish_text)
            parts.append("")
        
        # English translation
        english_text = file_results.get("english_transcription") or file_results.get("en_translation", "")
        if english_text:
            parts.append("=== ENGLISH TRANSLATION ===")
            parts.append(english_text)
            parts.append("")
        
        # Prosecutor interpretation
        interpretation = file_results.get("interpretation", "")
        if interpretation:
            parts.append("=== PROSECUTOR INTERPRETATION ===")
            parts.append(interpretation)
            parts.append("")
    
    elif output_format == "combined":
        # Simple combination of all text content
        if file_results.get("spanish_transcription"):
            parts.append(file_results["spanish_transcription"])
        if file_results.get("english_transcription"):
            parts.append(file_results["english_transcription"])
        if file_results.get("interpretation"):
            parts.append(file_results["interpretation"])
    
    else:
        # Default: combine all available text
        for key in ["spanish_transcription", "english_transcription", "interpretation"]:
            if file_results.get(key):
                parts.append(file_results[key])
    
    return "\n".join(parts)


def process_folder_with_profile(
    folder_path: Path,
    profile_name: str,
    case_id: str,
    log_callback: Optional[Callable[[str], None]] = None
) -> Dict[str, Any]:
    """
    Process a folder using a profile configuration.
    
    This function:
    1. Loads the profile's folder_processing config
    2. Identifies files by their roles (audio, metadata, interpretation)
    3. Processes files according to rules (transcription, metadata extraction)
    4. Combines results into structured text
    5. Returns the text and metadata ready for ingestion
    
    Args:
        folder_path: Path to the folder to process
        profile_name: Name of the profile to use
        case_id: Case ID for tracking
        log_callback: Optional logging callback
    
    Returns:
        Dict with:
            - text: Structured text ready for ingestion
            - metadata: Metadata dict for document node
            - folder_name: Name of the folder
            - processing_info: Dict with processing details
    """
    def log(message: str):
        if log_callback:
            log_callback(message)
        print(message, flush=True)
    
    folder_name = folder_path.name
    log(f"Processing folder with profile '{profile_name}': {folder_name}")
    
    # Load profile and get folder_processing config
    profile = load_profile(profile_name)
    folder_config = get_folder_processing_config(profile_name)
    
    if not folder_config:
        raise ValueError(f"Profile '{profile_name}' does not have folder_processing configuration")
    
    file_rules = folder_config.get("file_rules", [])
    output_format = folder_config.get("output_format", "combined")
    processing_rules = folder_config.get("processing_rules", "")
    
    log(f"  Profile type: {folder_config.get('type', 'standard')}")
    log(f"  Output format: {output_format}")
    log(f"  {len(file_rules)} file rules defined")
    
    # Find files by role
    role_files = find_files_by_role(folder_path, file_rules)
    
    log(f"  Found files:")
    for role, files in role_files.items():
        log(f"    {role}: {len(files)} file(s)")
        for f in files:
            log(f"      - {f.name}")
    
    # Process files according to rules
    file_results = {
        "metadata": {},
        "participants": [],
    }
    
    for rule in file_rules:
        role = rule.get("role", "")
        files = role_files.get(role, [])
        
        if not files:
            continue
        
        if role == "audio":
            # Use OpenAI Whisper API (default, no model loading needed)
            audio_results = process_audio_files(files, rule, None, log_callback)
            file_results.update(audio_results)
        
        elif role == "metadata":
            metadata_results = process_metadata_files(files, rule, log_callback)
            file_results["metadata"].update(metadata_results)
        
        elif role == "interpretation":
            interpretation_results = process_interpretation_files(files, rule, log_callback)
            file_results.update(interpretation_results)
            if "participants" in interpretation_results:
                file_results["participants"] = interpretation_results["participants"]
    
    # Prepare structured text for ingestion
    structured_text = prepare_structured_text(folder_name, file_results, output_format)
    
    # Prepare metadata for document node
    doc_metadata = {
        "source_type": "folder_processed",
        "profile_name": profile_name,
        "folder_name": folder_name,
        "full_path": str(folder_path.resolve()),
        "processing_rules": processing_rules,
        "output_format": output_format,
    }
    
    # Add file paths to metadata
    all_files = []
    for role, files in role_files.items():
        for f in files:
            all_files.append(str(f))
    doc_metadata["files"] = all_files
    
    # Add wiretap-specific metadata if present
    metadata = file_results.get("metadata", {})
    if metadata.get("time_of_call"):
        time_obj = metadata["time_of_call"]
        if isinstance(time_obj, datetime):
            doc_metadata["wiretap_time_of_call"] = time_obj.isoformat()
        else:
            doc_metadata["wiretap_time_of_call"] = str(time_obj)
    if metadata.get("input_line_id"):
        doc_metadata["wiretap_input_line_id"] = str(metadata["input_line_id"])
    if metadata.get("contact_id"):
        doc_metadata["wiretap_contact_id"] = str(metadata["contact_id"])
    if metadata.get("session_length"):
        doc_metadata["wiretap_session_length"] = str(metadata["session_length"])
    
    if file_results.get("participants"):
        doc_metadata["wiretap_participants"] = file_results["participants"]
    
    # Prepare processing info
    processing_info = {
        "profile_name": profile_name,
        "file_rules_used": len(file_rules),
        "files_processed": sum(len(files) for files in role_files.values()),
        "has_audio": len(role_files.get("audio", [])) > 0,
        "has_metadata": len(role_files.get("metadata", [])) > 0,
        "has_interpretation": len(role_files.get("interpretation", [])) > 0,
    }
    
    log(f"  Processing complete. Generated text: {len(structured_text)} characters")
    
    return {
        "text": structured_text,
        "metadata": doc_metadata,
        "folder_name": folder_name,
        "processing_info": processing_info,
        "file_results": file_results,  # Keep raw results for reference
    }
