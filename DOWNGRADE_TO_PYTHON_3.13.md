# Downgrade to Python 3.13

This guide will help you downgrade from Python 3.14 to Python 3.13 to restore ChromaDB/vector search functionality.

## Step 1: Install Python 3.13

If you're using Homebrew (which you appear to be based on your system):

```bash
# Install Python 3.13
brew install python@3.13

# Verify installation
python3.13 --version
```

## Step 2: Create a New Virtual Environment with Python 3.13

```bash
# Navigate to your project directory
cd /Users/neilbyrne/Documents/Owl/owl-n4j

# Remove or rename the old virtual environment (optional - you can keep it as backup)
mv .venv .venv-python3.14-backup

# Create a new virtual environment with Python 3.13
python3.13 -m venv .venv

# Activate the new virtual environment
source .venv/bin/activate

# Verify Python version
python --version
# Should show: Python 3.13.x
```

## Step 3: Upgrade pip and Install Dependencies

```bash
# Upgrade pip
pip install --upgrade pip

# Install all requirements
cd backend
pip install -r requirements.txt

# Verify ChromaDB works
python -c "import chromadb; print('ChromaDB imported successfully!')"
```

## Step 4: Test the Application

```bash
# Test database connection
python backend/scripts/test_db_connection.py

# Start the backend server
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

You should no longer see the ChromaDB compatibility warning, and vector search should be available.

## Alternative: Using pyenv (Recommended for Multiple Python Versions)

If you want to manage multiple Python versions easily:

```bash
# Install pyenv if not already installed
brew install pyenv

# Install Python 3.13 via pyenv
pyenv install 3.13.2

# Set Python 3.13 as the local version for this project
cd /Users/neilbyrne/Documents/Owl/owl-n4j
pyenv local 3.13.2

# Create new virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
cd backend
pip install --upgrade pip
pip install -r requirements.txt
```

## Troubleshooting

### If you get "command not found: python3.13"

Make sure Homebrew's Python 3.13 is in your PATH. Add to `~/.zshrc`:

```bash
export PATH="/opt/homebrew/opt/python@3.13/bin:$PATH"
```

Then reload:
```bash
source ~/.zshrc
```

### If ChromaDB still doesn't work

1. Make sure you're in the new virtual environment:
   ```bash
   which python
   # Should point to .venv/bin/python
   ```

2. Reinstall ChromaDB:
   ```bash
   pip uninstall chromadb
   pip install chromadb==1.4.0
   ```

### If you need to switch back to Python 3.14

Just activate the old virtual environment:
```bash
source .venv-python3.14-backup/bin/activate
```

## Notes

- Your old virtual environment is backed up as `.venv-python3.14-backup`
- All your project files remain unchanged
- Only the Python interpreter and installed packages change
- Database migrations and data are unaffected
