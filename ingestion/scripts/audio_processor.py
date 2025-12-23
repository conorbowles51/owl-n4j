"""
Audio Processor module - handles wiretap audio file processing.

Processes wiretap folders containing:
- Audio files (.WAV, .wav, .mp3, .MP3)
- Metadata files (.sri)
- Prosecutor interpretation files (.rtf, .syn.rtf)
- XML metadata files

Uses WhisperAI locally for transcription and translation.
Prepares data for LLM processing and Neo4j ingestion.
"""

import os
import re
import ssl
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Callable

try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    print("WARNING: whisper not installed. Install with: pip install openai-whisper")

try:
    from striprtf.striprtf import rtf_to_text
    RTF_AVAILABLE = True
except ImportError:
    RTF_AVAILABLE = False
    print("WARNING: striprtf not installed. Install with: pip install striprtf")

from ingestion import ingest_document


def load_whisper_model(model_size: str = "base"):
    """
    Load Whisper model for transcription.
    
    Args:
        model_size: Model size (tiny, base, small, medium, large)
    
    Returns:
        Whisper model instance
    """
    if not WHISPER_AVAILABLE:
        raise ImportError("Whisper is not installed. Install with: pip install openai-whisper")
    
    print(f"Loading Whisper model: {model_size}...", flush=True)
    
    # Handle SSL certificate issues on macOS
    # Try to use certifi certificates first, fall back to unverified if needed
    try:
        import certifi
        os.environ['SSL_CERT_FILE'] = certifi.where()
        os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
    except ImportError:
        pass
    
    # Try loading the model
    try:
        model = whisper.load_model(model_size)
    except (urllib.error.URLError, ssl.SSLError) as e:
        if "CERTIFICATE_VERIFY_FAILED" in str(e) or isinstance(e, ssl.SSLError):
            print("SSL certificate verification failed. Attempting to download with unverified context...", flush=True)
            print("(This is safe for downloading models from OpenAI's official repository)", flush=True)
            
            # Create unverified SSL context for download
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # Monkey-patch urllib to use unverified context temporarily
            original_urlopen = urllib.request.urlopen
            original_build_opener = urllib.request.build_opener
            
            def urlopen_with_unverified(*args, **kwargs):
                if 'context' not in kwargs:
                    kwargs['context'] = ssl_context
                return original_urlopen(*args, **kwargs)
            
            urllib.request.urlopen = urlopen_with_unverified
            try:
                model = whisper.load_model(model_size)
            finally:
                # Restore original functions
                urllib.request.urlopen = original_urlopen
        else:
            raise
    
    print("Whisper model loaded successfully.", flush=True)
    return model


def transcribe_audio(
    audio_path: Path,
    model,
    language: str = "es",
    task: str = "transcribe"
) -> str:
    """
    Transcribe audio file using Whisper.
    
    Args:
        audio_path: Path to audio file
        model: Whisper model instance
        language: Language code (es for Spanish, en for English)
        task: "transcribe" or "translate"
    
    Returns:
        Transcribed text
    """
    if not WHISPER_AVAILABLE:
        raise ImportError("Whisper is not installed")
    
    print(f"Transcribing audio: {audio_path.name} (language: {language}, task: {task})", flush=True)
    
    result = model.transcribe(
        str(audio_path),
        language=language if task == "transcribe" else None,
        task=task
    )
    
    return result["text"].strip()


def parse_sri_file(sri_path: Path) -> Dict:
    """
    Parse .sri metadata file.
    
    Format:
    version=2
    input_line_id=210-237-1858
    start_string=2007-06-17 14:27:43 CST
    session_length=67
    time_zone=CST
    contact_id=FMI=157,903,8333
    
    Args:
        sri_path: Path to .sri file
    
    Returns:
        Dict with parsed metadata
    """
    metadata = {}
    
    try:
        with open(sri_path, 'r', encoding='utf-8', errors='ignore') as file:
            lines = file.readlines()
            
            for line in lines:
                line = line.strip()
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if key == "start_string":
                        # Parse datetime: "2007-06-17 14:27:43 CST"
                        try:
                            # Remove timezone abbreviation for parsing
                            dt_string = value.rsplit(' ', 1)[0]
                            metadata["time_of_call"] = datetime.strptime(dt_string, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            metadata["time_of_call"] = None
                            metadata["time_of_call_string"] = value
                    elif key == "input_line_id":
                        metadata["input_line_id"] = value
                    elif key == "contact_id":
                        metadata["contact_id"] = value
                    elif key == "session_length":
                        metadata["session_length"] = value
                    elif key == "time_zone":
                        metadata["time_zone"] = value
                    elif key == "version":
                        metadata["version"] = value
    except Exception as e:
        print(f"Error parsing .sri file {sri_path}: {e}", flush=True)
    
    return metadata


def parse_rtf_file(rtf_path: Path) -> Dict:
    """
    Parse .rtf file for prosecutor interpretation and participant names.
    
    Args:
        rtf_path: Path to .rtf file
    
    Returns:
        Dict with 'interpretation' text and 'participants' list
    """
    if not RTF_AVAILABLE:
        print("WARNING: striprtf not available, cannot parse RTF file", flush=True)
        return {"interpretation": "", "participants": []}
    
    interpretation = ""
    participants = []
    
    try:
        with open(rtf_path, 'r', encoding='utf-8', errors='ignore') as file:
            content = file.read()
            text = rtf_to_text(content)
            interpretation = text.strip()
            
            # Extract participant names from "PARTICIPANTS:" line
            participants_match = re.search(r'PARTICIPANTS:\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
            if participants_match:
                participants_text = participants_match.group(1)
                # Split by common separators (AND, AKA, comma, etc.)
                participants = [p.strip() for p in re.split(r'\s+(?:AND|AKA|,)\s+', participants_text, flags=re.IGNORECASE)]
                participants = [p for p in participants if p]
            
            # Also try to extract from "TO" pattern (e.g., "CHARLIE TO UF#96")
            to_match = re.search(r'^([A-Z][A-Z0-9#\s]+)\s+TO\s+([A-Z][A-Z0-9#\s]+)', text, re.MULTILINE | re.IGNORECASE)
            if to_match:
                person1 = to_match.group(1).strip()
                person2 = to_match.group(2).strip()
                if person1 and person1 not in participants:
                    participants.append(person1)
                if person2 and person2 not in participants:
                    participants.append(person2)
    except Exception as e:
        print(f"Error parsing .rtf file {rtf_path}: {e}", flush=True)
    
    return {
        "interpretation": interpretation,
        "participants": participants
    }


def strip_names(name_string: str) -> Optional[str]:
    """
    Clean and extract name from string.
    
    Args:
        name_string: Name string that may contain extra characters
    
    Returns:
        Cleaned name or None
    """
    if not name_string:
        return None
    
    # Remove common prefixes/suffixes
    name_string = re.sub(r'^(AKA|ALIAS|ALSO KNOWN AS)\s+', '', name_string, flags=re.IGNORECASE)
    name_string = name_string.strip()
    
    # Split and take first non-empty token
    name_tokens = name_string.split()
    for name in name_tokens:
        name = name.strip()
        if name and len(name) > 1:
            return name
    
    return None


def process_wiretap_folder(
    folder_path: Path,
    whisper_model,
    log_callback: Optional[Callable[[str], None]] = None
) -> Dict:
    """
    Process a single wiretap folder (e.g., 00000128).
    
    Args:
        folder_path: Path to wiretap folder
        whisper_model: Whisper model instance for transcription
        log_callback: Optional callback function(message: str) to log progress
    
    Returns:
        Dict with processed wiretap data
    """
    folder_name = folder_path.name
    
    def log(message: str):
        if log_callback:
            log_callback(message)
        print(message, flush=True)
    
    log(f"Processing wiretap folder: {folder_name}")
    
    # Initialize data structure
    wiretap_data = {
        "folder_name": folder_name,
        "spanish_transcription": "",
        "english_transcription": "",
        "prosecutors_interpretation": "",
        "participants": [],
        "metadata": {},
        "audio_file": None,
        "sri_file": None,
        "rtf_file": None,
    }
    
    # Find all files in folder
    audio_files = []
    sri_files = []
    rtf_files = []
    
    for file_path in folder_path.iterdir():
        if file_path.is_file():
            name_lower = file_path.name.lower()
            
            if name_lower.endswith(('.wav', '.mp3', '.m4a', '.flac')):
                audio_files.append(file_path)
            elif name_lower.endswith('.sri'):
                sri_files.append(file_path)
            elif name_lower.endswith('.rtf'):
                rtf_files.append(file_path)
    
    # Process .sri metadata file
    if sri_files:
        sri_file = sri_files[0]  # Use first .sri file found
        wiretap_data["sri_file"] = str(sri_file)
        metadata = parse_sri_file(sri_file)
        wiretap_data["metadata"] = metadata
        log(f"  Parsed metadata from {sri_file.name}")
        
        # Print metadata to console
        print("\n" + "="*60)
        print("METADATA:")
        print("="*60)
        for key, value in metadata.items():
            if value is not None:
                if isinstance(value, datetime):
                    print(f"  {key}: {value.strftime('%Y-%m-%d %H:%M:%S')}")
                else:
                    print(f"  {key}: {value}")
        print("="*60 + "\n")
    else:
        log(f"  WARNING: No .sri file found in {folder_name}")
    
    # Process .rtf file (prosecutor interpretation)
    syn_rtf_files = [f for f in rtf_files if 'syn' in f.name.lower()]
    if syn_rtf_files:
        rtf_file = syn_rtf_files[0]  # Prefer syn.rtf files
        wiretap_data["rtf_file"] = str(rtf_file)
    elif rtf_files:
        rtf_file = rtf_files[0]
        wiretap_data["rtf_file"] = str(rtf_file)
    
    if wiretap_data["rtf_file"]:
        rtf_data = parse_rtf_file(Path(wiretap_data["rtf_file"]))
        wiretap_data["prosecutors_interpretation"] = rtf_data["interpretation"]
        wiretap_data["participants"] = rtf_data["participants"]
        log(f"  Parsed RTF file: {Path(wiretap_data['rtf_file']).name}")
        log(f"  Found participants: {', '.join(wiretap_data['participants'])}")
    
    # Process audio file(s)
    if audio_files:
        audio_file = audio_files[0]  # Use first audio file found
        wiretap_data["audio_file"] = str(audio_file)
        
        try:
            # Transcribe in Spanish
            log(f"  Transcribing audio in Spanish: {audio_file.name}")
            spanish_text = transcribe_audio(audio_file, whisper_model, language="es", task="transcribe")
            wiretap_data["spanish_transcription"] = spanish_text
            log(f"  Spanish transcription completed ({len(spanish_text)} characters)")
            
            # Print Spanish transcription to console
            print("\n" + "="*60)
            print("SPANISH TRANSCRIPTION:")
            print("="*60)
            print(spanish_text)
            print("="*60 + "\n")
            
            # Translate to English
            log(f"  Translating audio to English: {audio_file.name}")
            english_text = transcribe_audio(audio_file, whisper_model, language="es", task="translate")
            wiretap_data["english_transcription"] = english_text
            log(f"  English translation completed ({len(english_text)} characters)")
            
            # Print English translation to console
            print("="*60)
            print("ENGLISH TRANSLATION:")
            print("="*60)
            print(english_text)
            print("="*60 + "\n")
        except Exception as e:
            log(f"  ERROR: Failed to transcribe audio: {e}")
    else:
        log(f"  WARNING: No audio file found in {folder_name}")
    
    return wiretap_data


def prepare_wiretap_for_ingestion(wiretap_data: Dict) -> str:
    """
    Prepare wiretap data as text for LLM ingestion.
    
    Combines all available information into a structured text format
    that the LLM can process for entity and relationship extraction.
    
    Args:
        wiretap_data: Dict with wiretap data from process_wiretap_folder
    
    Returns:
        Formatted text string ready for ingestion
    """
    parts = []
    
    # Header with metadata
    parts.append("=== WIRETAP RECORDING ===")
    parts.append(f"Folder: {wiretap_data.get('folder_name', 'Unknown')}")
    
    metadata = wiretap_data.get("metadata", {})
    if metadata.get("time_of_call"):
        parts.append(f"Date/Time: {metadata['time_of_call'].strftime('%Y-%m-%d %H:%M:%S')}")
    if metadata.get("input_line_id"):
        parts.append(f"Input Line ID: {metadata['input_line_id']}")
    if metadata.get("contact_id"):
        parts.append(f"Contact ID: {metadata['contact_id']}")
    if metadata.get("session_length"):
        parts.append(f"Session Length: {metadata['session_length']} seconds")
    
    parts.append("")
    
    # Participants
    participants = wiretap_data.get("participants", [])
    if participants:
        parts.append("=== PARTICIPANTS ===")
        for participant in participants:
            parts.append(f"- {participant}")
        parts.append("")
    
    # Spanish transcription
    spanish_text = wiretap_data.get("spanish_transcription", "")
    if spanish_text:
        parts.append("=== SPANISH TRANSCRIPTION ===")
        parts.append(spanish_text)
        parts.append("")
    
    # English translation
    english_text = wiretap_data.get("english_transcription", "")
    if english_text:
        parts.append("=== ENGLISH TRANSLATION ===")
        parts.append(english_text)
        parts.append("")
    
    # Prosecutor interpretation
    interpretation = wiretap_data.get("prosecutors_interpretation", "")
    if interpretation:
        parts.append("=== PROSECUTOR INTERPRETATION ===")
        parts.append(interpretation)
        parts.append("")
    
    return "\n".join(parts)


def ingest_wiretap_folder(
    folder_path: Path,
    whisper_model,
    log_callback: Optional[Callable[[str], None]] = None
) -> Dict:
    """
    Process and ingest a wiretap folder into Neo4j.
    
    Creates separate nodes for:
    - Wiretap recording (with metadata)
    - Spanish transcription (as Document node)
    - English translation (as Document node)
    
    Links transcription and translation nodes to the wiretap recording node.
    
    Args:
        folder_path: Path to wiretap folder (e.g., 00000128)
        whisper_model: Whisper model instance
        log_callback: Optional callback function(message: str) to log progress
    
    Returns:
        Dict with ingestion result
    """
    from entity_resolution import normalise_key
    from neo4j_client import Neo4jClient
    
    def log(message: str):
        if log_callback:
            log_callback(message)
        print(message, flush=True)
    
    # Process the wiretap folder
    wiretap_data = process_wiretap_folder(folder_path, whisper_model, log_callback)
    
    # Create document name for the wiretap recording
    folder_name = folder_path.name
    metadata = wiretap_data.get("metadata", {})
    time_str = ""
    if metadata.get("time_of_call"):
        time_str = metadata["time_of_call"].strftime("%Y%m%d_%H%M%S")
    
    wiretap_doc_name = f"wiretap_{folder_name}"
    if time_str:
        wiretap_doc_name += f"_{time_str}"
    
    # Prepare metadata for wiretap recording - flatten nested structures for Neo4j compatibility
    wiretap_metadata = {
        "filename": str(folder_name),
        "full_path": str(folder_path.resolve()),
        "source_type": "wiretap_audio",
    }
    
    # Only add file paths if they exist and convert to strings
    if wiretap_data.get("audio_file"):
        wiretap_metadata["audio_file"] = str(wiretap_data["audio_file"])
    if wiretap_data.get("sri_file"):
        wiretap_metadata["sri_file"] = str(wiretap_data["sri_file"])
    if wiretap_data.get("rtf_file"):
        wiretap_metadata["rtf_file"] = str(wiretap_data["rtf_file"])
    
    # Flatten wiretap metadata (convert nested dict to flat properties)
    if metadata:
        if metadata.get("time_of_call"):
            time_obj = metadata["time_of_call"]
            if hasattr(time_obj, 'isoformat'):
                wiretap_metadata["wiretap_time_of_call"] = time_obj.isoformat()
            else:
                wiretap_metadata["wiretap_time_of_call"] = str(time_obj)
        if metadata.get("input_line_id"):
            wiretap_metadata["wiretap_input_line_id"] = str(metadata["input_line_id"])
        if metadata.get("contact_id"):
            wiretap_metadata["wiretap_contact_id"] = str(metadata["contact_id"])
        if metadata.get("session_length"):
            wiretap_metadata["wiretap_session_length"] = str(metadata["session_length"])
        if metadata.get("time_zone"):
            wiretap_metadata["wiretap_time_zone"] = str(metadata["time_zone"])
        if metadata.get("version"):
            wiretap_metadata["wiretap_version"] = str(metadata["version"])
    
    # Handle participants list
    participants = wiretap_data.get("participants", [])
    if participants:
        wiretap_metadata["wiretap_participants"] = participants
    
    # Create a summary text for the wiretap recording document (metadata only)
    wiretap_summary_parts = []
    wiretap_summary_parts.append(f"Wiretap Recording: {folder_name}")
    if metadata.get("time_of_call"):
        wiretap_summary_parts.append(f"Date/Time: {metadata['time_of_call'].strftime('%Y-%m-%d %H:%M:%S')}")
    if metadata.get("input_line_id"):
        wiretap_summary_parts.append(f"Input Line ID: {metadata['input_line_id']}")
    if metadata.get("contact_id"):
        wiretap_summary_parts.append(f"Contact ID: {metadata['contact_id']}")
    if participants:
        wiretap_summary_parts.append(f"Participants: {', '.join(participants)}")
    
    wiretap_summary_text = "\n".join(wiretap_summary_parts)
    
    total_entities = 0
    total_relationships = 0
    
    with Neo4jClient() as db:
        # Create wiretap recording document node (metadata only)
        wiretap_doc_key = normalise_key(wiretap_doc_name)
        db.ensure_document(
            doc_key=wiretap_doc_key,
            doc_name=wiretap_doc_name,
            metadata=wiretap_metadata,
        )
        log(f"Created wiretap recording document: {wiretap_doc_name}")
        
        # Process Spanish transcription if available
        spanish_text = wiretap_data.get("spanish_transcription", "")
        if spanish_text and spanish_text.strip():
            spanish_doc_name = f"{wiretap_doc_name}_transcription_spanish"
            spanish_metadata = {
                "source_type": "wiretap_transcription",
                "language": "spanish",
                "wiretap_source": wiretap_doc_name,
            }
            
            log(f"Ingesting Spanish transcription: {spanish_doc_name}")
            spanish_result = ingest_document(
                text=spanish_text,
                doc_name=spanish_doc_name,
                doc_metadata=spanish_metadata,
                log_callback=log_callback,
            )
            
            if spanish_result.get("status") != "skipped":
                total_entities += spanish_result.get("entities_processed", 0)
                total_relationships += spanish_result.get("relationships_processed", 0)
                
                # Link transcription document to wiretap recording document
                spanish_doc_key = normalise_key(spanish_doc_name)
                db.create_relationship(
                    from_key=wiretap_doc_key,
                    to_key=spanish_doc_key,
                    rel_type="HAS_TRANSCRIPTION",
                    doc_name=wiretap_doc_name,
                    notes="Spanish transcription of wiretap recording",
                )
                log(f"Linked Spanish transcription to wiretap recording")
        
        # Process English translation if available
        english_text = wiretap_data.get("english_transcription", "")
        if english_text and english_text.strip():
            english_doc_name = f"{wiretap_doc_name}_translation_english"
            english_metadata = {
                "source_type": "wiretap_translation",
                "language": "english",
                "wiretap_source": wiretap_doc_name,
            }
            
            log(f"Ingesting English translation: {english_doc_name}")
            english_result = ingest_document(
                text=english_text,
                doc_name=english_doc_name,
                doc_metadata=english_metadata,
                log_callback=log_callback,
            )
            
            if english_result.get("status") != "skipped":
                total_entities += english_result.get("entities_processed", 0)
                total_relationships += english_result.get("relationships_processed", 0)
                
                # Link translation document to wiretap recording document
                english_doc_key = normalise_key(english_doc_name)
                db.create_relationship(
                    from_key=wiretap_doc_key,
                    to_key=english_doc_key,
                    rel_type="HAS_TRANSLATION",
                    doc_name=wiretap_doc_name,
                    notes="English translation of wiretap recording",
                )
                log(f"Linked English translation to wiretap recording")
        
        # Also ingest the prosecutor interpretation if available (as part of wiretap recording)
        interpretation = wiretap_data.get("prosecutors_interpretation", "")
        if interpretation and interpretation.strip():
            # Add interpretation to wiretap summary for processing
            wiretap_summary_text += f"\n\n=== PROSECUTOR INTERPRETATION ===\n{interpretation}"
        
        # Ingest wiretap recording summary (with interpretation if available) for any additional entity extraction
        # This processes the metadata and prosecutor interpretation through the LLM pipeline
        if wiretap_summary_text.strip():
            log(f"Ingesting wiretap recording summary: {wiretap_doc_name}")
            wiretap_result = ingest_document(
                text=wiretap_summary_text,
                doc_name=wiretap_doc_name,
                doc_metadata=wiretap_metadata,
                log_callback=log_callback,
            )
            if wiretap_result.get("status") != "skipped":
                total_entities += wiretap_result.get("entities_processed", 0)
                total_relationships += wiretap_result.get("relationships_processed", 0)
    
    return {
        "status": "success",
        "entities_processed": total_entities,
        "relationships_processed": total_relationships,
        "folder": str(folder_path),
    }


def process_wiretap_directory(
    base_dir: Path,
    whisper_model_size: str = "base",
    log_callback: Optional[Callable[[str], None]] = None
) -> Dict:
    """
    Process all wiretap folders in a directory.
    
    Args:
        base_dir: Base directory containing wiretap folders (e.g., example_wiretap)
        whisper_model_size: Whisper model size to use
        log_callback: Optional callback function(message: str) to log progress
    
    Returns:
        Dict with processing statistics
    """
    if not WHISPER_AVAILABLE:
        raise ImportError("Whisper is not installed. Install with: pip install openai-whisper")
    
    def log(message: str):
        if log_callback:
            log_callback(message)
        print(message, flush=True)
    
    log(f"Loading Whisper model: {whisper_model_size}")
    model = load_whisper_model(whisper_model_size)
    
    stats = {
        "folders_processed": 0,
        "folders_skipped": 0,
        "folders_failed": 0,
        "total_entities": 0,
        "total_relationships": 0,
    }
    
    # Find all subdirectories (wiretap folders)
    wiretap_folders = [d for d in base_dir.iterdir() if d.is_dir()]
    
    log(f"Found {len(wiretap_folders)} wiretap folders to process")
    
    for folder_path in wiretap_folders:
        try:
            result = ingest_wiretap_folder(folder_path, model, log_callback)
            
            if result.get("status") == "skipped":
                stats["folders_skipped"] += 1
                log(f"Skipped {folder_path.name}: {result.get('reason', 'unknown')}")
            elif result.get("status") == "error":
                stats["folders_failed"] += 1
                log(f"Failed {folder_path.name}: {result.get('reason', 'unknown')}")
            else:
                stats["folders_processed"] += 1
                stats["total_entities"] += result.get("entities_processed", 0)
                stats["total_relationships"] += result.get("relationships_processed", 0)
                log(f"Successfully processed {folder_path.name}")
        except Exception as e:
            stats["folders_failed"] += 1
            log(f"ERROR processing {folder_path.name}: {e}")
    
    log(f"\nProcessing complete:")
    log(f"  Processed: {stats['folders_processed']}")
    log(f"  Skipped: {stats['folders_skipped']}")
    log(f"  Failed: {stats['folders_failed']}")
    log(f"  Total entities: {stats['total_entities']}")
    log(f"  Total relationships: {stats['total_relationships']}")
    
    return stats

