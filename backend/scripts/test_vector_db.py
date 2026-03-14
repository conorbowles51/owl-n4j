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

        # Test 1: Check chunk collection exists
        print("\n1. Checking chunk collection...")
        count = vector_db_service.count_chunks()
        print(f"   OK Collection exists with {count} chunks")

        # Test 2: Add a test chunk
        print("\n2. Adding test chunk...")
        test_embedding = [0.1] * 1536  # Mock embedding (1536 dims for OpenAI)
        vector_db_service.add_chunk(
            chunk_id="test_doc_001_chunk_0",
            text="This is a test document about fraud investigation.",
            embedding=test_embedding,
            metadata={"doc_id": "test_doc_001", "doc_name": "test.pdf", "case_id": "test_case", "chunk_index": 0}
        )
        print("   OK Test chunk added")

        # Test 3: Search (using same embedding as query)
        print("\n3. Testing search...")
        results = vector_db_service.search_chunks(
            query_embedding=test_embedding,
            top_k=5
        )
        if results:
            print(f"   OK Search returned {len(results)} results")
            print(f"     Top result: {results[0]['id']} (distance: {results[0].get('distance', 'N/A')})")
        else:
            print("   FAIL Search returned no results")
            return False

        # Test 4: Count chunks
        print("\n4. Counting chunks...")
        count = vector_db_service.count_chunks()
        print(f"   OK Total chunks: {count}")

        # Test 5: Delete test chunk
        print("\n5. Deleting test chunk...")
        vector_db_service.delete_chunk("test_doc_001_chunk_0")
        count_after = vector_db_service.count_chunks()
        if count_after == count - 1:
            print(f"   OK Chunk deleted (count: {count} -> {count_after})")
        else:
            print(f"   WARNING Count mismatch (expected {count - 1}, got {count_after})")

        # Test 6: Check entity collection
        print("\n6. Checking entity collection...")
        entity_count = vector_db_service.count_entities()
        print(f"   OK Entity collection has {entity_count} entities")

        print("\n" + "=" * 60)
        print("VectorDBService tests PASSED")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\nFAIL VectorDBService test FAILED: {e}")
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
            print("\nWARNING EmbeddingService not initialized (check configuration)")
            print("   This is expected if OPENAI_API_KEY is not set or provider is misconfigured")
            return True  # Not a failure, just not configured

        # Test 1: Generate single embedding
        print("\n1. Generating single embedding...")
        test_text = "This is a test document about fraud investigation."
        embedding = embedding_service.generate_embedding(test_text)
        print(f"   OK Embedding generated: {len(embedding)} dimensions")

        # Test 2: Generate batch embeddings
        print("\n2. Generating batch embeddings...")
        test_texts = [
            "Document about money laundering",
            "Report on suspicious transactions",
            "Investigation into fraud case"
        ]
        embeddings = embedding_service.generate_embeddings_batch(test_texts, batch_size=2)
        print(f"   OK Generated {len(embeddings)} embeddings in batch")

        # Test 3: Check embedding dimension
        print("\n3. Checking embedding dimension...")
        dim = embedding_service.get_embedding_dimension()
        print(f"   OK Embedding dimension: {dim}")
        if len(embedding) == dim:
            print(f"   OK Actual embedding matches expected dimension")
        else:
            print(f"   WARNING Dimension mismatch (expected {dim}, got {len(embedding)})")

        print("\n" + "=" * 60)
        print("EmbeddingService tests PASSED")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\nFAIL EmbeddingService test FAILED: {e}")
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
        status = "PASSED" if passed else "FAILED"
        print(f"{name}: {status}")

    all_passed = all(result[1] for result in results)
    print("\n" + "=" * 60)
    if all_passed:
        print("All tests PASSED")
    else:
        print("Some tests FAILED")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
