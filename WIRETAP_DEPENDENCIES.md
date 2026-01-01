# Wiretap Processing Dependencies Installation Guide

This guide covers installing the required dependencies for wiretap audio processing on your server.

## Required Dependencies

Wiretap processing requires:
1. **openai-whisper** - Python package for audio transcription
2. **striprtf** - Python package for parsing RTF files  
3. **ffmpeg** - System dependency for audio processing (required by whisper)

## Installation Steps

### Step 1: Install System Dependencies

#### Ubuntu/Debian
```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
```

#### CentOS/RHEL
```bash
sudo yum install -y ffmpeg
# Or for newer versions:
sudo dnf install -y ffmpeg
```

#### macOS
```bash
brew install ffmpeg
```

#### Windows
Download and install from: https://ffmpeg.org/download.html
Add ffmpeg to your system PATH.

### Step 2: Install Python Dependencies

Make sure you're in the correct Python environment (same one used by your backend application).

#### Using pip (recommended)
```bash
pip install openai-whisper striprtf
```

#### Using requirements.txt
Add these lines to your `requirements.txt`:
```
openai-whisper>=20231117
striprtf>=0.0.26
```

Then install:
```bash
pip install -r requirements.txt
```

### Step 3: Verify Installation

Test that all dependencies are installed correctly:

```bash
# Check ffmpeg
ffmpeg -version

# Check Python packages
python -c "import whisper; print('Whisper OK')"
python -c "from striprtf.striprtf import rtf_to_text; print('striprtf OK')"
```

If all commands succeed, the dependencies are installed correctly.

## Docker Deployment

If deploying with Docker, add to your Dockerfile:

```dockerfile
# Install system dependencies
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install openai-whisper striprtf
```

## Virtual Environment

If using a virtual environment, activate it first:

```bash
# Activate virtual environment
source venv/bin/activate  # Linux/macOS
# OR
venv\Scripts\activate  # Windows

# Install dependencies
pip install openai-whisper striprtf
```

## Troubleshooting

### "ffmpeg not found" error
- Ensure ffmpeg is installed and in your system PATH
- Verify with: `which ffmpeg` (Linux/macOS) or `where ffmpeg` (Windows)

### "No module named 'whisper'" error
- Ensure you're installing in the same Python environment as your backend
- Check Python version: `python --version` (should be 3.8+)
- Try: `pip install --upgrade openai-whisper`

### "No module named 'striprtf'" error
- Install with: `pip install striprtf`
- Verify: `python -c "import striprtf"`

### Different Python environments
If your backend and ingestion scripts use different Python environments:
1. Find which Python your backend uses: Check your startup script or `which python`
2. Install dependencies in that environment
3. Or ensure both environments have the dependencies installed

## Additional Notes

- **Whisper models**: The first time you use a Whisper model, it will be downloaded automatically (can be 100MB-3GB depending on model size)
- **Disk space**: Ensure you have sufficient disk space for model downloads
- **Network**: Model downloads require internet access on first use
- **Performance**: Larger models (medium, large) are more accurate but slower and require more memory

## Quick Install Script

For Ubuntu/Debian systems, you can use this one-liner:

```bash
sudo apt-get update && sudo apt-get install -y ffmpeg && pip install openai-whisper striprtf
```



