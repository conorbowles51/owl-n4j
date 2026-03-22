# Flexible Folder Upload Profiles & Audio Processing Plan

## Overview

Transform the hard-coded wiretap processing into a flexible, user-configurable system that supports:
1. **Standalone audio file processing** with transcription/translation options
2. **Custom folder upload profiles** defined by users via natural language
3. **Special folder processing rules** that understand file relationships and dependencies
4. **LLM-guided processing** that interprets user-defined rules during ingestion

---

## Current State Analysis

### Hard-Coded Components

1. **`check_wiretap_suitable()`** in `backend/services/wiretap_service.py`
   - Detects folders by checking for specific file types (.wav, .mp3, .sri, .rtf)
   - Logic is hard-coded to wiretap structure

2. **`process_wiretap_folder()`** in `ingestion/scripts/audio_processor.py`
   - Hard-coded file type handling (.sri metadata, .rtf interpretation)
   - Hard-coded transcription workflow (Spanish + English)
   - Hard-coded text preparation format

3. **Upload Flow** in `backend/routers/evidence.py`
   - `is_folder` parameter triggers folder handling
   - No profile selection or rule configuration

### Existing Assets to Leverage

1. **Profile System** (`backend/profile_loader.py`, `profiles/*.json`)
   - Already exists for LLM prompts and entity extraction
   - Can be extended for folder processing rules

2. **Audio Processing Infrastructure**
   - Whisper transcription is already set up
   - `transcribe_audio()` function supports multiple languages and tasks
   - Audio file detection logic exists

3. **LLM Service** (`backend/services/llm_service.py`)
   - Can interpret natural language rules
   - Can guide processing based on user instructions

---

## Proposed Solution Architecture

### 1. Folder Upload Profile System

#### 1.1 Profile Structure

Extend the existing profile system to include `folder_processing` configurations:

```json
{
  "name": "wiretap",
  "description": "Wiretap folder with audio, metadata, and interpretation files",
  "folder_processing": {
    "type": "special",  // "standard" or "special"
    "file_rules": [
      {
        "pattern": "*.wav,*.mp3,*.m4a,*.flac",
        "role": "audio",
        "actions": ["transcribe", "translate"],
        "transcribe_languages": ["es"],
        "translate_languages": ["en"],
        "metadata_extraction": null
      },
      {
        "pattern": "*.sri",
        "role": "metadata",
        "parser": "sri",
        "metadata_extraction": {
          "time_of_call": "datetime",
          "contact_id": "string",
          "input_line_id": "string",
          "session_length": "integer"
        }
      },
      {
        "pattern": "*.rtf",
        "role": "interpretation",
        "parser": "rtf",
        "extract_participants": true,
        "extract_interpretation": true
      }
    ],
    "processing_rules": "Extract metadata from .sri files, transcribe audio in Spanish, translate to English, extract participants and interpretation from .rtf files. All files in this folder are related to the same wiretap recording.",
    "output_format": "wiretap_structured",
    "related_files_indicator": true
  }
}
```

#### 1.2 User-Defined Profile Creation Flow

**Option A: Natural Language Rule Builder (Recommended)**
- User uploads folder
- System detects file types in folder
- User selects "Create Custom Profile" or "Use Existing Profile"
- User provides natural language description:
  - *"These are wiretap recordings. Each folder has an audio file that should be transcribed in Spanish and translated to English. There are .sri files with call metadata and .rtf files with prosecutor interpretations. All files are related to the same call."*
- LLM interprets the description and generates a profile structure
- User can review/edit the generated profile
- Profile is saved for reuse

**Option B: Guided Form Builder**
- Step-by-step form to define:
  - File patterns and roles
  - Transcription/translation languages
  - Metadata extraction rules
  - File relationships

#### 1.3 Profile Storage

- Store custom profiles in `profiles/` directory (same as existing profiles)
- Profile naming: `{user-defined-name}.json`
- Profiles can reference "base" profiles for common patterns
- System profiles (e.g., `wiretap.json`) provided as templates

### 2. Audio Processing Enhancements

#### 2.1 Standalone Audio File Processing

Enable processing individual audio files without requiring folder structure:

- **API Endpoint**: `POST /evidence/audio/process`
- **Request**:
  ```json
  {
    "case_id": "...",
    "file_path": "path/to/audio.wav",
    "transcription": {
      "enabled": true,
      "languages": ["es"],  // Languages to transcribe
      "task": "transcribe"  // "transcribe" or "translate"
    },
    "translation": {
      "enabled": true,
      "target_languages": ["en"]  // Languages to translate to
    }
  }
  ```

- **Processing**: 
  - Transcribe in specified languages
  - Translate to target languages
  - Ingest transcriptions as separate documents
  - Link transcriptions to source audio file

#### 2.2 Transcription Configuration

Make transcription configurable per profile or per request:

```json
{
  "whisper_model": "base",  // tiny, base, small, medium, large
  "transcription_tasks": [
    {
      "source_language": "es",
      "task": "transcribe",
      "output_field": "spanish_transcription"
    },
    {
      "source_language": "es",
      "task": "translate",
      "target_language": "en",
      "output_field": "english_transcription"
    }
  ]
}
```

### 3. Special Folder Processing Rules

#### 3.1 Rule Interpretation

When `folder_processing.type == "special"`:

1. **File Relationship Detection**
   - System analyzes file patterns and roles
   - Understands which files are related/dependent
   - Groups related files for combined processing

2. **LLM-Guided Processing**
   - `processing_rules` text is passed to LLM during ingestion
   - LLM receives context about:
     - File types and roles found
     - Extracted metadata
     - Relationships between files
   - LLM uses rules to:
     - Combine information from multiple files intelligently
     - Extract entities/relationships considering file context
     - Create appropriate relationships in Neo4j

3. **Output Format Customization**
   - `output_format` determines how files are combined for LLM ingestion
   - Options:
     - `"wiretap_structured"`: Current wiretap format
     - `"combined"`: Merge all text content
     - `"linked_documents"`: Keep separate but link in Neo4j
     - `"custom"`: LLM interprets format from rules

#### 3.2 Processing Rules Examples

**Wiretap Example:**
```
These folders contain wiretap recordings. Each folder represents one call.
- Audio files (.wav) should be transcribed in Spanish and translated to English
- .sri files contain call metadata (time, participants, duration)
- .rtf files contain prosecutor interpretation
- Combine all information when extracting entities, as they describe the same event
- Link transcriptions and interpretations to the same wiretap recording node
```

**Multi-Part Document Example:**
```
This folder contains a multi-part report split across multiple PDFs.
- Files named "report_part1.pdf", "report_part2.pdf", etc. are sequential pages
- Process them in order and maintain page context
- "appendix.pdf" is a supporting document, link it but keep separate
- Extract entities across all parts as if they were one document
```

**Evidence Package Example:**
```
This folder contains related evidence files from an investigation.
- "summary.pdf" is an overview document, extract key entities first
- "interview_transcript.pdf" references people mentioned in summary
- "photos/" subfolder contains related images, extract metadata only
- Create relationships between entities mentioned across different files
```

### 4. Implementation Components

#### 4.1 New Files to Create

1. **`backend/services/folder_profile_service.py`**
   - Profile creation/management
   - Profile validation
   - Profile-to-processing-config conversion

2. **`backend/services/audio_processing_service.py`**
   - Standalone audio file processing
   - Transcription/translation orchestration
   - Audio ingestion pipeline

3. **`backend/services/folder_processor.py`**
   - Replaces hard-coded wiretap logic
   - Profile-based folder processing
   - File relationship detection
   - Rule interpretation

4. **`ingestion/scripts/folder_processor.py`** (or extend `audio_processor.py`)
   - Profile-driven processing logic
   - Dynamic file handling based on rules
   - LLM-guided text preparation

#### 4.2 Files to Modify

1. **`backend/routers/evidence.py`**
   - Add profile selection to upload endpoint
   - Add audio processing endpoint
   - Add profile creation/management endpoints

2. **`backend/services/evidence_service.py`**
   - Integrate folder profile processing
   - Route to appropriate processor based on profile

3. **`backend/services/wiretap_service.py`**
   - Deprecate hard-coded `check_wiretap_suitable()`
   - Replace with profile-based detection
   - Keep for backward compatibility initially

4. **`ingestion/scripts/audio_processor.py`**
   - Refactor `process_wiretap_folder()` to be profile-driven
   - Extract file handling logic into configurable functions
   - Make transcription workflow configurable

5. **Profile System** (`backend/profile_loader.py`, `profiles/*.json`)
   - Extend to support `folder_processing` section
   - Add validation for folder profiles

#### 4.3 Frontend Changes

1. **Upload UI Enhancement**
   - Add profile selection dropdown (with "Create New" option)
   - Show "Special Folder" checkbox/option
   - If "Create New" selected, show rule builder UI

2. **Rule Builder UI**
   - Natural language input field (with examples)
   - Preview of detected files and their proposed roles
   - Preview of generated profile (editable)
   - Save profile option

3. **Audio Processing UI**
   - Individual audio file processing option
   - Transcription/translation language selection
   - Processing status for audio files

### 5. Processing Flow

#### 5.1 Standalone Audio Processing Flow

```
User uploads audio file
  ↓
User selects transcription/translation options
  ↓
System transcribes audio (if requested)
  ↓
System translates audio (if requested)
  ↓
System ingests transcription(s) as document(s)
  ↓
Links transcription nodes to audio file node in Neo4j
  ↓
Returns processing result
```

#### 5.2 Folder Upload with Profile Flow

```
User uploads folder
  ↓
User selects profile (or creates new one)
  ↓
System scans folder for files matching profile patterns
  ↓
If profile.type == "special":
  - System identifies file relationships
  - Applies processing rules to each file based on role
  - Combines information according to output_format
  - Passes processing_rules to LLM during ingestion
  ↓
System processes folder using profile configuration
  ↓
System ingests with LLM-guided entity extraction
  ↓
Returns processing result
```

#### 5.3 Profile Creation Flow

```
User uploads folder
  ↓
User selects "Create Custom Profile"
  ↓
System scans folder and detects file types
  ↓
User provides natural language rules
  ↓
LLM interprets rules and generates profile structure
  ↓
User reviews/edits generated profile
  ↓
Profile saved to profiles/{name}.json
  ↓
Profile available for future use
```

### 6. Backward Compatibility

#### 6.1 Migration Strategy

1. **Keep existing wiretap detection** (deprecated but functional)
   - If folder matches wiretap pattern and no profile specified, use default wiretap behavior
   - Log deprecation warning

2. **Default Profile**
   - Create `profiles/wiretap.json` with current wiretap logic
   - Existing wiretap processing uses this profile automatically

3. **Gradual Migration**
   - New folders use profile system
   - Existing workflows continue to work
   - Users can migrate to profiles when ready

### 7. LLM Integration Points

#### 7.1 Profile Generation from Natural Language

**Prompt Template:**
```
You are helping a user configure a folder processing profile. 

The user has uploaded a folder with these files:
{file_list}

The user wants this processing:
{user_rules}

Generate a JSON profile structure that defines:
1. File patterns and their roles (audio, metadata, interpretation, etc.)
2. Transcription/translation requirements
3. Metadata extraction rules
4. Processing rules for how files relate to each other
5. Output format for combining files

Respond with valid JSON only, matching this structure:
{profile_schema}
```

#### 7.2 Rule Application During Ingestion

**Enhanced Ingestion Prompt:**
```
You are extracting entities and relationships from a folder of related files.

Folder Processing Rules:
{processing_rules}

Files in this folder:
{file_descriptions}

Extracted Metadata:
{metadata}

File Content:
{combined_content}

Based on the processing rules, extract entities and relationships, considering:
- How files relate to each other
- Cross-file entity references
- Context from metadata
- Special handling specified in the rules
```

### 8. Database/Storage Considerations

#### 8.1 Profile Storage

- JSON files in `profiles/` directory
- Version control for profile changes
- Profile metadata (creator, created date, usage count)

#### 8.2 Processing History

- Track which profile was used for each folder
- Store processing rules used
- Link to source profile for audit

### 9. Benefits

1. **Flexibility**: Support any folder structure, not just wiretap
2. **Reusability**: Save and reuse profiles for similar cases
3. **Natural Language**: Users define rules in plain English
4. **LLM-Powered**: System interprets rules intelligently
5. **Extensibility**: Easy to add new file types and processors
6. **Standalone Audio**: Process audio files independently
7. **Maintainability**: Remove hard-coded logic, use configuration

### 10. Risks & Considerations

1. **LLM Interpretation Accuracy**: Natural language rules may be misinterpreted
   - **Mitigation**: Provide preview/editing of generated profiles
   - **Mitigation**: Validate profiles before saving

2. **Performance**: LLM-based profile generation adds latency
   - **Mitigation**: Cache generated profiles
   - **Mitigation**: Provide template-based quick setup

3. **Complexity**: More options may confuse users
   - **Mitigation**: Provide good defaults
   - **Mitigation**: Include examples and templates
   - **Mitigation**: Progressive disclosure in UI

4. **Migration**: Existing wiretap workflows need to continue working
   - **Mitigation**: Backward compatibility mode
   - **Mitigation**: Clear migration path

### 11. Testing Strategy

1. **Unit Tests**
   - Profile parsing and validation
   - File pattern matching
   - Rule interpretation

2. **Integration Tests**
   - End-to-end folder processing with profiles
   - Audio transcription workflow
   - Profile creation from natural language

3. **User Acceptance Tests**
   - Create profiles for different folder structures
   - Verify backward compatibility with wiretap
   - Test edge cases (missing files, unexpected patterns)

### 12. Documentation Needs

1. **User Guide**
   - How to create folder profiles
   - Natural language rule examples
   - Profile best practices

2. **Developer Guide**
   - Profile structure specification
   - How to add new file processors
   - Extending the profile system

3. **API Documentation**
   - New endpoints for audio processing
   - Profile management endpoints
   - Updated upload endpoint

---

## Implementation Phases

### Phase 1: Foundation (Week 1-2)
- ✅ Design profile structure
- ✅ Implement profile storage and loading
- ✅ Create basic profile validation
- ✅ Extend profile system to support folder_processing

### Phase 2: Audio Processing (Week 2-3)
- ✅ Standalone audio file processing endpoint
- ✅ Configurable transcription/translation
- ✅ Audio ingestion pipeline

### Phase 3: Folder Processor (Week 3-4)
- ✅ Profile-based folder processor
- ✅ File pattern matching
- ✅ Dynamic file handling
- ✅ Remove hard-coded wiretap logic (keep backward compat)

### Phase 4: Profile Creation (Week 4-5)
- ✅ LLM-based profile generation from natural language
- ✅ Profile creation UI
- ✅ Profile management endpoints

### Phase 5: LLM Rule Integration (Week 5-6)
- ✅ Pass processing rules to LLM during ingestion
- ✅ Enhanced ingestion prompts
- ✅ Cross-file entity extraction

### Phase 6: Frontend Integration (Week 6-7)
- ✅ Profile selection in upload UI
- ✅ Rule builder UI
- ✅ Audio processing UI
- ✅ Testing and refinement

---

## Open Questions

1. **Profile Sharing**: Should profiles be case-specific, user-specific, or global?
   - **Recommendation**: User-specific with option to share globally

2. **File Pattern Matching**: Regex vs glob patterns?
   - **Recommendation**: Glob patterns (simpler) with optional regex for advanced users

3. **LLM for Profile Generation**: Which model? Cost considerations?
   - **Recommendation**: Use same model as entity extraction, cache results

4. **Error Handling**: What if profile rules are unclear or files don't match?
   - **Recommendation**: Validation with clear error messages, fallback to default behavior

5. **Performance**: How to handle very large folders with complex rules?
   - **Recommendation**: Background processing (already exists), progress tracking

---

## Success Metrics

1. **Adoption**: Users create and use custom profiles
2. **Flexibility**: Support at least 3 different folder structure types beyond wiretap
3. **Accuracy**: LLM interpretation of rules matches user intent >90% of the time
4. **Performance**: Profile-based processing doesn't add significant latency
5. **Backward Compatibility**: Existing wiretap workflows continue to work
