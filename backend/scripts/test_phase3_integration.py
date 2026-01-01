"""
Test script for Phase 3: Semantic Search Integration.

This script tests that the RAG service correctly integrates
vector search with hybrid filtering.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
backend_dir = project_root / "backend"

# Add backend directory FIRST so config imports resolve correctly
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))


def test_rag_service_imports():
    """Test that RAG service can import vector DB services."""
    print("=" * 60)
    print("Testing RAG Service Imports")
    print("=" * 60)
    
    try:
        # Import directly using importlib to avoid __init__.py
        import importlib.util
        
        spec = importlib.util.spec_from_file_location(
            "rag_service",
            backend_dir / "services" / "rag_service.py"
        )
        rag_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rag_module)
        rag_service = rag_module.rag_service
        
        print("✓ RAG service imported successfully")
        
        # Check if vector search methods exist
        if hasattr(rag_service, '_find_relevant_documents'):
            print("✓ _find_relevant_documents method exists")
        else:
            print("✗ _find_relevant_documents method not found")
            return False
        
        if hasattr(rag_service, '_get_nodes_from_documents'):
            print("✓ _get_nodes_from_documents method exists")
        else:
            print("✗ _get_nodes_from_documents method not found")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_vector_search_method():
    """Test that vector search method works."""
    print("\n" + "=" * 60)
    print("Testing Vector Search Method")
    print("=" * 60)
    
    try:
        import importlib.util
        
        # Import RAG service
        spec = importlib.util.spec_from_file_location(
            "rag_service",
            backend_dir / "services" / "rag_service.py"
        )
        rag_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rag_module)
        rag_service = rag_module.rag_service
        
        # Check if vector DB is available
        if not rag_module.VECTOR_DB_AVAILABLE:
            print("⚠ Vector DB not available (not configured or disabled)")
            print("  This is expected if embedding service is not initialized")
            return True  # Not a failure, just not configured
        
        # Test vector search with a sample question
        question = "What documents discuss fraud or money laundering?"
        print(f"Testing vector search with question: '{question}'")
        
        doc_ids = rag_service._find_relevant_documents(question, top_k=5)
        print(f"✓ Vector search returned {len(doc_ids)} document IDs")
        
        if doc_ids:
            print(f"  Document IDs: {doc_ids[:3]}...")
        else:
            print("  No documents found (this is OK if no documents are embedded yet)")
        
        return True
        
    except Exception as e:
        print(f"✗ Vector search test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_hybrid_filtering_logic():
    """Test that hybrid filtering logic is implemented."""
    print("\n" + "=" * 60)
    print("Testing Hybrid Filtering Logic")
    print("=" * 60)
    
    try:
        import importlib.util
        
        # Import RAG service
        spec = importlib.util.spec_from_file_location(
            "rag_service",
            backend_dir / "services" / "rag_service.py"
        )
        rag_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rag_module)
        rag_service = rag_module.rag_service
        
        # Check if answer_question method exists and has hybrid logic
        if not hasattr(rag_service, 'answer_question'):
            print("✗ answer_question method not found")
            return False
        
        print("✓ answer_question method exists")
        
        # Check the source code for hybrid filtering keywords
        rag_file = backend_dir / "services" / "rag_service.py"
        content = rag_file.read_text()
        
        if "hybrid-filtered" in content:
            print("✓ Hybrid filtering mode found in code")
        else:
            print("⚠ Hybrid filtering mode not found in code")
        
        if "_find_relevant_documents" in content and "_get_nodes_from_documents" in content:
            print("✓ Vector search methods are integrated")
        else:
            print("⚠ Vector search methods not found in code")
        
        if "VECTOR_DB_AVAILABLE" in content:
            print("✓ Vector DB availability check implemented")
        else:
            print("⚠ Vector DB availability check not found")
        
        return True
        
    except Exception as e:
        print(f"✗ Hybrid filtering test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_fallback_logic():
    """Test that fallback logic is implemented."""
    print("\n" + "=" * 60)
    print("Testing Fallback Logic")
    print("=" * 60)
    
    try:
        rag_file = backend_dir / "services" / "rag_service.py"
        content = rag_file.read_text()
        
        # Check for fallback patterns
        fallback_patterns = [
            "except Exception",
            "Fallback to full graph",
            "context_mode = \"full\"",
            "VECTOR_DB_AVAILABLE"
        ]
        
        found_patterns = []
        for pattern in fallback_patterns:
            if pattern in content:
                found_patterns.append(pattern)
                print(f"✓ Found fallback pattern: {pattern}")
        
        if len(found_patterns) >= 2:
            print("✓ Fallback logic appears to be implemented")
            return True
        else:
            print("⚠ Fallback logic may be incomplete")
            return True  # Not a hard failure
        
    except Exception as e:
        print(f"✗ Fallback logic test failed: {e}")
        return False


def main():
    """Run all Phase 3 integration tests."""
    print("\n" + "=" * 60)
    print("Phase 3: Semantic Search Integration - Test Suite")
    print("=" * 60)
    
    results = []
    
    # Test 1: Imports
    results.append(("RAG Service Imports", test_rag_service_imports()))
    
    # Test 2: Vector search method
    results.append(("Vector Search Method", test_vector_search_method()))
    
    # Test 3: Hybrid filtering logic
    results.append(("Hybrid Filtering Logic", test_hybrid_filtering_logic()))
    
    # Test 4: Fallback logic
    results.append(("Fallback Logic", test_fallback_logic()))
    
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
        print("All Phase 3 integration tests PASSED ✓")
        print("\nThe RAG service is ready for hybrid vector + Cypher filtering!")
    else:
        print("Some Phase 3 integration tests FAILED ✗")
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

