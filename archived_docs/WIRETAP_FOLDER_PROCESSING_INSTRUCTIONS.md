# Wiretap Folder Processing Instructions

Use these instructions when creating a custom folder processing profile for wiretap recordings:

---

## Standard Wiretap Processing Instructions

```
These folders contain wiretap recordings from law enforcement investigations. Each folder represents one recorded phone call or conversation. The folder contains multiple related files that must be processed together as a single unit.

Processing Requirements:

1. Audio Files (.wav, .mp3, .m4a, .flac):
   - Transcribe the audio in its original language (typically Spanish)
   - Translate the transcription to English
   - Both transcriptions are essential for entity extraction and analysis

2. Metadata Files (.sri):
   - Extract call metadata including:
     - Time and date of the call
     - Phone numbers (contact ID, input line ID)
     - Call duration (session length)
   - This metadata provides context for the conversation

3. Interpretation Files (.rtf):
   - Extract prosecutor's or investigator's interpretation/notes about the call
   - Extract participant names mentioned in the interpretation
   - This provides additional context and key entity identification

File Relationships:
All files in each folder describe the same wiretap recording. The audio, metadata, and interpretation files are interdependent - they all refer to the same phone call. When extracting entities and relationships, treat all information from these files as describing a single event. Participants mentioned in any file should be linked to the same recording.

Output Format:
Combine all information into a structured format that preserves the relationships between the audio transcriptions, metadata, and interpretations. This allows the LLM to understand the full context when extracting entities and relationships.
```

---

## Simplified Version (Copy-Paste Ready)

```
These folders contain wiretap recordings. Each folder represents one phone call with multiple related files:

- Audio files (.wav, .mp3, .m4a, .flac) should be transcribed in Spanish and translated to English
- .sri files contain call metadata (time, phone numbers, duration)
- .rtf files contain prosecutor interpretation and participant names

All files in a folder describe the same call and should be processed together. Extract entities considering that all information relates to one conversation event.
```

---

## Even Shorter Version (Quick Entry)

```
Wiretap folders: Audio files (.wav, .mp3) need Spanish transcription and English translation. .sri files have call metadata (time, phone numbers). .rtf files have prosecutor interpretations and participant names. All files in each folder describe the same call.
```

---

## Instructions for Other Folder Types

### Multi-Part Document Folders

```
This folder contains a report split across multiple PDF files:
- Files named "report_part1.pdf", "report_part2.pdf", etc. are sequential pages - process them in order
- "appendix.pdf" is supporting material - keep separate but link it
- Extract entities across all parts as if they were one continuous document
- Maintain page context when combining
```

### Evidence Package Folders

```
This folder contains related evidence files from an investigation:
- "summary.pdf" is an overview - extract key entities first
- "interview_transcript.pdf" references people from the summary
- "photos/" subfolder contains related images - extract metadata only
- Create relationships between entities mentioned across different files
- All files are related to the same investigation case
```

### Mixed Document Folders

```
This folder contains related case documents:
- PDF files are primary documents - extract full text and entities
- Image files (.jpg, .png) should have metadata extracted (filename, date if in name)
- Text files (.txt) contain notes or summaries
- All documents reference the same case - link entities mentioned across files
- Maintain document type context in metadata
```

---

## Usage

1. **In the FolderProfileModal**: Copy one of the wiretap instructions above into the "Processing Instructions" text area
2. **Click "Generate Profile"**: The LLM will create a profile structure based on these instructions
3. **Review and Test**: Check the generated profile JSON and test it on a folder

The instructions tell the LLM:
- What file types exist
- How each file type should be processed
- How files relate to each other
- What the output format should be
