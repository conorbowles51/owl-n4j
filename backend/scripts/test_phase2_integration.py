"""
Test script for Phase 2: Document Embedding During Ingestion.

This script tests that the ingestion pipeline correctly integrates
with the vector DB and embedding services.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
backend_dir = project_root / "backend"

# Add backend directory FIRST so config imports resolve correctly
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(project_root / "ingestion" / "scripts"))


def test_imports():
    """Test that vector DB services can be imported from ingestion scripts."""
    print("=" * 60)
    print("Testing Imports")
    print("=" * 60)
    
    try:
        # Import directly using importlib to avoid __init__.py
        import importlib.util
        
        # Temporarily remove ingestion scripts from path to avoid config conflicts
        ingestion_path = str(project_root / "ingestion" / "scripts")
        if ingestion_path in sys.path:
            sys.path.remove(ingestion_path)
        
        # Import vector_db_service
        spec = importlib.util.spec_from_file_location(
            "vector_db_service",
            backend_dir / "services" / "vector_db_service.py"
        )
        vector_db_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vector_db_module)
        vector_db_service = vector_db_module.vector_db_service
        
        # Import embedding_service
        spec = importlib.util.spec_from_file_location(
            "embedding_service",
            backend_dir / "services" / "embedding_service.py"
        )
        embedding_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(embedding_module)
        embedding_service = embedding_module.embedding_service
        
        # Restore path
        sys.path.insert(0, ingestion_path)
        
        print("✓ Vector DB service imported successfully")
        print("✓ Embedding service imported successfully")
        
        if embedding_service is None:
            print("⚠ Embedding service is None (not configured)")
            return False
        
        print("✓ Embedding service is initialized")
        return True
        
    except Exception as e:
        print(f"✗ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_neo4j_update_method():
    """Test that Neo4j client has update_document method."""
    print("\n" + "=" * 60)
    print("Testing Neo4j Client Update Method")
    print("=" * 60)
    
    try:
        from neo4j_client import Neo4jClient
        
        # Check if update_document method exists
        if hasattr(Neo4jClient, 'update_document'):
            print("✓ update_document method exists")
            return True
        else:
            print("✗ update_document method not found")
            return False
            
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False


def test_embedding_generation():
    """Test that embedding can be generated for a sample document."""
    print("\n" + "=" * 60)
    print("Testing Embedding Generation")
    print("=" * 60)
    
    try:
        # Import directly using importlib
        import importlib.util
        ingestion_path = str(project_root / "ingestion" / "scripts")
        if ingestion_path in sys.path:
            sys.path.remove(ingestion_path)
        
        spec = importlib.util.spec_from_file_location(
            "embedding_service",
            backend_dir / "services" / "embedding_service.py"
        )
        embedding_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(embedding_module)
        embedding_service = embedding_module.embedding_service
        
        sys.path.insert(0, ingestion_path)
        
        if embedding_service is None:
            print("⚠ Embedding service not configured, skipping test")
            return True  # Not a failure, just not configured
        
        # Test with sample document text
        sample_text = """
        This is a test document about fraud investigation.
        It contains information about suspicious transactions and money laundering.
        The document discusses various entities and their relationships.
        """
        
        print("Generating embedding for sample document...")
        embedding = embedding_service.generate_embedding(sample_text.strip())
        
        print(f"✓ Embedding generated: {len(embedding)} dimensions")
        
        # Verify embedding is not empty
        if len(embedding) > 0:
            print("✓ Embedding is valid")
            return True
        else:
            print("✗ Embedding is empty")
            return False
            
    except Exception as e:
        print(f"✗ Embedding generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_vector_storage():
    """Test that embeddings can be stored in vector DB."""
    print("\n" + "=" * 60)
    print("Testing Vector DB Storage")
    print("=" * 60)
    
    try:
        # Import directly using importlib
        import importlib.util
        ingestion_path = str(project_root / "ingestion" / "scripts")
        if ingestion_path in sys.path:
            sys.path.remove(ingestion_path)
        
        # Import vector_db_service
        spec = importlib.util.spec_from_file_location(
            "vector_db_service",
            backend_dir / "services" / "vector_db_service.py"
        )
        vector_db_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vector_db_module)
        vector_db_service = vector_db_module.vector_db_service
        
        # Import embedding_service
        spec = importlib.util.spec_from_file_location(
            "embedding_service",
            backend_dir / "services" / "embedding_service.py"
        )
        embedding_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(embedding_module)
        embedding_service = embedding_module.embedding_service
        
        sys.path.insert(0, ingestion_path)
        
        if embedding_service is None:
            print("⚠ Embedding service not configured, skipping test")
            return True
        
        # Generate test embedding
        test_text = "Test document for Phase 2 integration testing"
        embedding = embedding_service.generate_embedding(test_text)
        
        # Store in vector DB
        test_doc_id = "test_phase2_integration"
        vector_db_service.add_document(
            doc_id=test_doc_id,
            text=test_text,
            embedding=embedding,
            metadata={
                "filename": "test_phase2.txt",
                "doc_key": "test-phase2-integration",
                "source_type": "test",
            }
        )
        print("✓ Document stored in vector DB")
        
        # Retrieve it
        doc = vector_db_service.get_document(test_doc_id)
        if doc and doc["id"] == test_doc_id:
            print("✓ Document retrieved from vector DB")
        else:
            print("✗ Failed to retrieve document")
            return False
        
        # Test search
        results = vector_db_service.search(
            query_embedding=embedding,
            top_k=1
        )
        if results and results[0]["id"] == test_doc_id:
            print("✓ Vector search works correctly")
        else:
            print("✗ Vector search failed")
            return False
        
        # Clean up
        vector_db_service.delete_document(test_doc_id)
        print("✓ Test document cleaned up")
        
        return True
        
    except Exception as e:
        print(f"✗ Vector storage test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all Phase 2 integration tests."""
    print("\n" + "=" * 60)
    print("Phase 2: Document Embedding During Ingestion - Integration Tests")
    print("=" * 60)
    
    results = []
    
    # Test 1: Imports
    results.append(("Imports", test_imports()))
    
    # Test 2: Neo4j update method
    results.append(("Neo4j Update Method", test_neo4j_update_method()))
    
    # Test 3: Embedding generation
    results.append(("Embedding Generation", test_embedding_generation()))
    
    # Test 4: Vector storage
    results.append(("Vector Storage", test_vector_storage()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    for name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{name}: {status}")
    
    all_passed = all(result[1] for result in results)
    print("\n" + "=" * 60)
    if all_passed:
        print("All Phase 2 integration tests PASSED ✓")
        print("\nThe ingestion pipeline is ready to generate embeddings!")
    else:
        print("Some Phase 2 integration tests FAILED ✗")
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

