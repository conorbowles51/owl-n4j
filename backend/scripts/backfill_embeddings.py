"""
Backfill embeddings for existing documents.

This script generates embeddings for all documents that are already in Neo4j
but don't have embeddings in the vector database yet.
"""

import sys
from pathlib import Path
from typing import List, Dict, Optional
import time

# Add project root to path
project_root = Path(__file__).parent.parent.parent
backend_dir = project_root / "backend"

# Add backend directory FIRST so config imports resolve correctly
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Import services
from services.neo4j_service import neo4j_service
from services.vector_db_service import vector_db_service
from services.embedding_service import embedding_service
from services.evidence_storage import evidence_storage, EVIDENCE_ROOT_DIR
from config import BASE_DIR

# Import text extraction utilities
sys.path.insert(0, str(project_root / "ingestion" / "scripts"))
try:
    from pdf_ingestion import extract_text_from_pdf
    PDF_EXTRACTION_AVAILABLE = True
except ImportError:
    PDF_EXTRACTION_AVAILABLE = False
    print("Warning: PDF extraction not available")


def extract_text_from_file(file_path: Path) -> Optional[str]:
    """
    Extract text from a file based on its extension.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Extracted text or None if extraction fails
    """
    if not file_path.exists():
        return None
    
    suffix = file_path.suffix.lower()
    
    try:
        if suffix == '.pdf':
            if PDF_EXTRACTION_AVAILABLE:
                return extract_text_from_pdf(file_path)
            else:
                print(f"  Warning: PDF extraction not available for {file_path.name}")
                return None
        elif suffix in ['.txt', '.md', '.csv', '.json', '.xml', '.html']:
            # Text files - read directly
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        else:
            # Try to read as text anyway
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            except:
                print(f"  Warning: Could not extract text from {file_path.name} (unsupported format)")
                return None
    except Exception as e:
        print(f"  Error extracting text from {file_path.name}: {e}")
        return None


def find_evidence_file(doc_name: str) -> Optional[Path]:
    """
    Find the evidence file corresponding to a document name.
    
    Args:
        doc_name: Document name/filename
        
    Returns:
        Path to the file or None if not found
    """
    # Search through all evidence records
    all_evidence = evidence_storage.get_all()
    
    for evidence in all_evidence:
        original_filename = evidence.get("original_filename", "")
        if original_filename == doc_name:
            stored_path_str = evidence.get("stored_path", "")
            if stored_path_str:
                stored_path = Path(stored_path_str)
                if stored_path.exists():
                    return stored_path
    
    # Also try direct search in evidence root directory
    # Documents might be in case subdirectories
    for case_dir in EVIDENCE_ROOT_DIR.iterdir():
        if case_dir.is_dir():
            # Check root of case directory
            potential_file = case_dir / doc_name
            if potential_file.exists():
                return potential_file
            
            # Check recursively in subdirectories
            for file_path in case_dir.rglob(doc_name):
                if file_path.is_file():
                    return file_path
    
    return None


def backfill_embeddings(
    dry_run: bool = False,
    skip_existing: bool = True,
    batch_size: int = 10,
) -> Dict:
    """
    Generate embeddings for all existing documents.
    
    Args:
        dry_run: If True, only report what would be done without making changes
        skip_existing: If True, skip documents that already have embeddings
        batch_size: Number of documents to process before showing progress
        
    Returns:
        Dictionary with statistics
    """
    print("=" * 60)
    print("Backfilling Embeddings for Existing Documents")
    print("=" * 60)
    
    if embedding_service is None:
        print("\n✗ Embedding service is not configured!")
        print("  Please set OPENAI_API_KEY or configure Ollama")
        return {"status": "error", "reason": "embedding_service_not_configured"}
    
    if dry_run:
        print("\n[DRY RUN MODE] - No changes will be made\n")
    
    # Get all documents from Neo4j
    print("Querying Neo4j for all documents...")
    try:
        cypher = """
        MATCH (d:Document)
        RETURN d.id AS id, d.key AS key, d.name AS name, 
               COALESCE(d.vector_db_id, null) AS vector_db_id
        ORDER BY d.name
        """
        documents = neo4j_service.run_cypher(cypher)
        print(f"Found {len(documents)} documents in Neo4j")
    except Exception as e:
        print(f"✗ Error querying Neo4j: {e}")
        return {"status": "error", "reason": str(e)}
    
    if not documents:
        print("No documents found in Neo4j")
        return {"status": "complete", "processed": 0, "skipped": 0, "failed": 0}
    
    # Statistics
    stats = {
        "total": len(documents),
        "processed": 0,
        "skipped": 0,
        "failed": 0,
        "already_embedded": 0,
        "file_not_found": 0,
        "extraction_failed": 0,
        "embedding_failed": 0,
    }
    
    print(f"\nProcessing {stats['total']} documents...")
    print("-" * 60)
    
    start_time = time.time()
    
    for i, doc in enumerate(documents, 1):
        doc_id = doc.get("id") or doc.get("d.id")
        doc_key = doc.get("key") or doc.get("d.key")
        doc_name = doc.get("name") or doc.get("d.name")
        vector_db_id = doc.get("vector_db_id") or doc.get("d.vector_db_id")
        
        if not doc_id or not doc_name:
            print(f"\n[{i}/{stats['total']}] Skipping document with missing ID/name")
            stats["skipped"] += 1
            continue
        
        # Check if already embedded
        if skip_existing and vector_db_id:
            # Verify it actually exists in vector DB
            existing_doc = vector_db_service.get_document(vector_db_id)
            if existing_doc:
                print(f"\n[{i}/{stats['total']}] {doc_name} - Already embedded (skipping)")
                stats["already_embedded"] += 1
                continue
        
        print(f"\n[{i}/{stats['total']}] Processing: {doc_name}")
        
        # Find the file
        file_path = find_evidence_file(doc_name)
        if not file_path:
            print(f"  ✗ File not found for document: {doc_name}")
            stats["file_not_found"] += 1
            stats["failed"] += 1
            continue
        
        print(f"  Found file: {file_path}")
        
        # Extract text
        print("  Extracting text...")
        text = extract_text_from_file(file_path)
        if not text or not text.strip():
            print(f"  ✗ Could not extract text from file")
            stats["extraction_failed"] += 1
            stats["failed"] += 1
            continue
        
        text_length = len(text)
        print(f"  ✓ Extracted {text_length:,} characters")
        
        if dry_run:
            print(f"  [DRY RUN] Would generate embedding and store for document {doc_id}")
            stats["processed"] += 1
            continue
        
        # Generate embedding
        try:
            print("  Generating embedding...")
            embedding = embedding_service.generate_embedding(text)
            print(f"  ✓ Embedding generated ({len(embedding)} dimensions)")
        except Exception as e:
            print(f"  ✗ Failed to generate embedding: {e}")
            stats["embedding_failed"] += 1
            stats["failed"] += 1
            continue
        
        # Store in vector DB
        try:
            print("  Storing in vector DB...")
            vector_db_service.add_document(
                doc_id=doc_id,
                text=text[:10000],  # Limit text length for storage
                embedding=embedding,
                metadata={
                    "filename": doc_name,
                    "doc_key": doc_key,
                    "source_type": file_path.suffix.lower().lstrip('.') or "unknown",
                }
            )
            print("  ✓ Stored in vector DB")
        except Exception as e:
            print(f"  ✗ Failed to store in vector DB: {e}")
            stats["failed"] += 1
            continue
        
        # Update Neo4j Document node
        try:
            print("  Updating Neo4j document node...")
            update_cypher = """
            MATCH (d:Document {id: $doc_id})
            SET d.vector_db_id = $doc_id
            RETURN d
            """
            neo4j_service.run_cypher(update_cypher, params={"doc_id": doc_id})
            print("  ✓ Updated Neo4j document node")
        except Exception as e:
            print(f"  ⚠ Warning: Failed to update Neo4j node: {e}")
            # Don't fail the whole operation, embedding is stored
        
        stats["processed"] += 1
        
        # Progress update every batch_size documents
        if i % batch_size == 0:
            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            remaining = stats["total"] - i
            eta = remaining / rate if rate > 0 else 0
            print(f"\n  Progress: {i}/{stats['total']} ({i/stats['total']*100:.1f}%)")
            print(f"  Rate: {rate:.1f} docs/sec, ETA: {eta:.0f} seconds")
    
    # Final summary
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("Backfill Complete")
    print("=" * 60)
    print(f"Total documents: {stats['total']}")
    print(f"Processed: {stats['processed']}")
    print(f"Skipped: {stats['skipped']}")
    print(f"Already embedded: {stats['already_embedded']}")
    print(f"Failed: {stats['failed']}")
    print(f"  - File not found: {stats['file_not_found']}")
    print(f"  - Extraction failed: {stats['extraction_failed']}")
    print(f"  - Embedding failed: {stats['embedding_failed']}")
    print(f"\nTime elapsed: {elapsed:.1f} seconds")
    if stats['processed'] > 0:
        print(f"Average time per document: {elapsed/stats['processed']:.1f} seconds")
    
    return {
        "status": "complete",
        **stats,
        "elapsed_seconds": elapsed,
    }


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Backfill embeddings for existing documents"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without making changes (dry run mode)"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip documents that already have embeddings"
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_false",
        dest="skip_existing",
        help="Re-process documents that already have embeddings"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of documents to process before showing progress (default: 10)"
    )
    
    args = parser.parse_args()
    
    result = backfill_embeddings(
        dry_run=args.dry_run,
        skip_existing=args.skip_existing,
        batch_size=args.batch_size,
    )
    
    if result.get("status") == "error":
        sys.exit(1)
    
    sys.exit(0)


if __name__ == "__main__":
    main()

