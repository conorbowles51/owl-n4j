# Audio Processor for Wiretap Ingestion

This module processes wiretap audio files and ingests them into the Neo4j knowledge graph using the same LLM-based entity extraction pipeline as other document types.

## Overview

The audio processor:
1. **Processes wiretap folders** (e.g., `00000128`) containing audio files and metadata
2. **Transcribes audio** using WhisperAI locally (Spanish transcription and English translation)
3. **Extracts metadata** from `.sri` files (call time, contact ID, input line ID, etc.)
4. **Extracts prosecutor interpretation** from `.rtf` files
5. **Extracts participant names** from RTF files
6. **Prepares structured text** combining all information
7. **Ingests into Neo4j** using the standard LLM-based entity/relationship extraction pipeline

## File Structure

A wiretap folder (e.g., `00000128`) typically contains:
- **Audio file**: `.WAV`, `.wav`, `.mp3`, `.MP3` - The actual wiretap recording
- **Metadata file**: `.sri` - Contains call metadata (time, contact ID, etc.)
- **Interpretation file**: `.rtf` or `_syn.rtf` - Prosecutor's interpretation of the call
- **XML files**: Various `.XML` files with additional metadata

## Installation

Install required dependencies:

```bash
pip install openai-whisper striprtf
```

**Note**: Whisper requires `ffmpeg` to be installed on your system:
- macOS: `brew install ffmpeg`
- Ubuntu/Debian: `sudo apt-get install ffmpeg`
- Windows: Download from https://ffmpeg.org/download.html

## Usage

### Process a single wiretap folder

```bash
python ingestion/scripts/ingest_audio.py --folder ingestion/audio/example_wiretap/00000128
```

### Process all wiretap folders in a directory

```bash
python ingestion/scripts/ingest_audio.py --dir ingestion/audio/example_wiretap
```

### Use a larger Whisper model (more accurate, slower)

```bash
python ingestion/scripts/ingest_audio.py --dir ingestion/audio/example_wiretap --model large
```

Available model sizes: `tiny`, `base`, `small`, `medium`, `large`

### Clear database before processing

```bash
python ingestion/scripts/ingest_audio.py --dir ingestion/audio/example_wiretap --clear
```

## How It Works

### 1. Metadata Extraction

The processor reads `.sri` files to extract:
- **Time of call**: When the wiretap was recorded
- **Contact ID**: Phone number or contact identifier
- **Input Line ID**: Line identifier
- **Session length**: Duration of the call

### 2. Audio Transcription

Uses WhisperAI to:
- **Transcribe** the audio in Spanish (original language)
- **Translate** the audio to English

Both transcriptions are included in the final document for LLM processing.

### 3. Prosecutor Interpretation

Extracts text from `.rtf` files containing:
- Summary of the call
- Participant names (from "PARTICIPANTS:" line or "TO" pattern)
- Government interpretation of events

### 4. Document Preparation

All information is combined into a structured text format:

```
=== WIRETAP RECORDING ===
Folder: 00000128
Date/Time: 2007-06-17 14:27:43
Input Line ID: 210-237-1858
Contact ID: FMI=157,903,8333

=== PARTICIPANTS ===
- CHARLIE
- UF#96

=== SPANISH TRANSCRIPTION ===
[Spanish transcription text...]

=== ENGLISH TRANSLATION ===
[English translation text...]

=== PROSECUTOR INTERPRETATION ===
[Prosecutor's interpretation text...]
```

### 5. LLM Processing

The structured text is then processed by the standard ingestion pipeline:
- **Chunked** into manageable pieces
- **Entity extraction** using LLM (persons, locations, organizations, etc.)
- **Relationship extraction** (who called whom, mentioned what, etc.)
- **Entity resolution** (matching to existing entities or creating new ones)
- **Stored in Neo4j** with relationships and metadata

## Integration with Existing Pipeline

The audio processor uses the same `ingest_document()` function from `ingestion.py`, so:
- ✅ Same entity types and relationship types
- ✅ Same LLM prompts and extraction logic
- ✅ Same entity resolution (fuzzy matching, disambiguation)
- ✅ Same Neo4j storage format
- ✅ Same summary generation and notes accumulation

## Comparison with FileWalkerProd

**FileWalkerProd.py** (original):
- Uses external `audiototext.py` script for transcription
- Stores data in Elasticsearch
- Processes multiple folders in batch
- Creates separate person entities

**audio_processor.py** (new):
- Uses WhisperAI directly (local, no external script)
- Integrates with Neo4j ingestion pipeline
- Uses LLM for entity/relationship extraction (more intelligent)
- Follows same patterns as PDF/text ingestion
- Better integration with existing graph structure

## Example Output

After processing, the wiretap data will appear in Neo4j as:
- **Document node**: Represents the wiretap recording
- **Person entities**: Participants extracted from the call
- **PhoneCall relationships**: Between participants
- **Mentioned relationships**: Entities mentioned in the call
- **Location entities**: Places mentioned in the transcription
- **Other entities**: Organizations, vehicles, weapons, etc. mentioned

All entities are linked to the source wiretap document, and notes accumulate across multiple wiretaps mentioning the same entities.

## Troubleshooting

### Whisper model download

The first time you run with a model size, Whisper will download it. This can take a few minutes. Models are cached for future use.

### Audio format issues

If Whisper fails to process an audio file, ensure `ffmpeg` is installed and the audio format is supported (WAV, MP3, M4A, FLAC).

### Memory issues

Larger Whisper models require more RAM:
- `tiny`: ~1GB RAM
- `base`: ~1GB RAM
- `small`: ~2GB RAM
- `medium`: ~5GB RAM
- `large`: ~10GB RAM

If you encounter memory issues, use a smaller model size.

