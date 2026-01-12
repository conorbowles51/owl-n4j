"""
Script to reset ChromaDB collections when changing embedding models.

This script deletes the ChromaDB data directory to reset the collections,
allowing them to be recreated with the correct dimensions for the new embedding model.

Usage:
    python backend/scripts/reset_chromadb.py
    
Warning: This will delete all existing embeddings in ChromaDB!
"""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from config import BASE_DIR, CHROMADB_PATH
import shutil

def reset_chromadb():
    """Delete ChromaDB data directory to reset collections."""
    db_path = BASE_DIR / CHROMADB_PATH
    
    if not db_path.exists():
        print(f"ChromaDB directory does not exist: {db_path}")
        print("No action needed.")
        return
    
    print(f"ChromaDB directory found: {db_path}")
    print(f"WARNING: This will delete all embeddings in ChromaDB!")
    
    # Ask for confirmation
    response = input("Are you sure you want to delete all ChromaDB data? (yes/no): ")
    if response.lower() != "yes":
        print("Aborted.")
        return
    
    try:
        # Delete the entire ChromaDB directory
        shutil.rmtree(db_path)
        print(f"✓ Successfully deleted ChromaDB directory: {db_path}")
        print("")
        print("Next steps:")
        print("1. Restart your backend server")
        print("2. The ChromaDB collections will be recreated automatically with the correct dimensions")
        print("3. You may need to backfill your documents to regenerate embeddings with the new model")
    except Exception as e:
        print(f"✗ Error deleting ChromaDB directory: {e}")
        sys.exit(1)

if __name__ == "__main__":
    reset_chromadb()
