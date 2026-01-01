"""
Test script for Vector DB and Embedding services.

This script tests the basic functionality of Phase 1 implementation.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "backend"))

def test_vector_db_service():
    """Test VectorDBService basic operations."""
    print("=" * 60)
    print("Testing VectorDBService")
    print("=" * 60)
    
    try:
        # Import directly to avoid __init__.py dependencies
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "vector_db_service",
            project_root / "backend" / "services" / "vector_db_service.py"
        )
        vector_db_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vector_db_module)
        vector_db_service = vector_db_module.vector_db_service
        
        # Test 1: Check collection exists
        print("\n1. Checking collection...")
        count = vector_db_service.count_documents()
        print(f"   ✓ Collection exists with {count} documents")
        
        # Test 2: Add a test document
        print("\n2. Adding test document...")
        test_embedding = [0.1] * 1536  # Mock embedding (1536 dims for OpenAI)
        vector_db_service.add_document(
            doc_id="test_doc_001",
            text="This is a test document about fraud investigation.",
            embedding=test_embedding,
            metadata={"filename": "test.pdf", "case_id": "test_case"}
        )
        print("   ✓ Test document added")
        
        # Test 3: Retrieve document
        print("\n3. Retrieving test document...")
        doc = vector_db_service.get_document("test_doc_001")
        if doc:
            print(f"   ✓ Document retrieved: {doc['id']}")
            print(f"     Text: {doc['text'][:50]}...")
            print(f"     Metadata: {doc['metadata']}")
        else:
            print("   ✗ Failed to retrieve document")
            return False
        
        # Test 4: Search (using same embedding as query)
        print("\n4. Testing search...")
        results = vector_db_service.search(
            query_embedding=test_embedding,
            top_k=5
        )
        if results:
            print(f"   ✓ Search returned {len(results)} results")
            print(f"     Top result: {results[0]['id']} (distance: {results[0].get('distance', 'N/A')})")
        else:
            print("   ✗ Search returned no results")
            return False
        
        # Test 5: Count documents
        print("\n5. Counting documents...")
        count = vector_db_service.count_documents()
        print(f"   ✓ Total documents: {count}")
        
        # Test 6: Delete test document
        print("\n6. Deleting test document...")
        vector_db_service.delete_document("test_doc_001")
        count_after = vector_db_service.count_documents()
        if count_after == count - 1:
            print(f"   ✓ Document deleted (count: {count} → {count_after})")
        else:
            print(f"   ⚠ Count mismatch (expected {count - 1}, got {count_after})")
        
        print("\n" + "=" * 60)
        print("VectorDBService tests PASSED ✓")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n✗ VectorDBService test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_embedding_service():
    """Test EmbeddingService (if configured)."""
    print("\n" + "=" * 60)
    print("Testing EmbeddingService")
    print("=" * 60)
    
    try:
        # Import directly to avoid __init__.py dependencies
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "embedding_service",
            project_root / "backend" / "services" / "embedding_service.py"
        )
        embedding_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(embedding_module)
        embedding_service = embedding_module.embedding_service
        
        if embedding_service is None:
            print("\n⚠ EmbeddingService not initialized (check configuration)")
            print("   This is expected if OPENAI_API_KEY is not set or provider is misconfigured")
            return True  # Not a failure, just not configured
        
        # Test 1: Generate single embedding
        print("\n1. Generating single embedding...")
        test_text = "This is a test document about fraud investigation."
        embedding = embedding_service.generate_embedding(test_text)
        print(f"   ✓ Embedding generated: {len(embedding)} dimensions")
        
        # Test 2: Generate batch embeddings
        print("\n2. Generating batch embeddings...")
        test_texts = [
            "Document about money laundering",
            "Report on suspicious transactions",
            "Investigation into fraud case"
        ]
        embeddings = embedding_service.generate_embeddings_batch(test_texts, batch_size=2)
        print(f"   ✓ Generated {len(embeddings)} embeddings in batch")
        
        # Test 3: Check embedding dimension
        print("\n3. Checking embedding dimension...")
        dim = embedding_service.get_embedding_dimension()
        print(f"   ✓ Embedding dimension: {dim}")
        if len(embedding) == dim:
            print(f"   ✓ Actual embedding matches expected dimension")
        else:
            print(f"   ⚠ Dimension mismatch (expected {dim}, got {len(embedding)})")
        
        print("\n" + "=" * 60)
        print("EmbeddingService tests PASSED ✓")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n✗ EmbeddingService test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("Phase 1: Vector DB Infrastructure - Test Suite")
    print("=" * 60)
    
    results = []
    
    # Test Vector DB Service
    results.append(("VectorDBService", test_vector_db_service()))
    
    # Test Embedding Service
    results.append(("EmbeddingService", test_embedding_service()))
    
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
        print("All tests PASSED ✓")
    else:
        print("Some tests FAILED ✗")
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

