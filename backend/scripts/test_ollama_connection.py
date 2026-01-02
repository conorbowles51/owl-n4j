#!/usr/bin/env python3
"""
Test script to verify Ollama connection and qwen2.5 model usage.
"""

import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from services.llm_service import llm_service
import requests

def test_ollama_api():
    """Test direct Ollama API connection."""
    print("=" * 60)
    print("Testing Ollama API Connection")
    print("=" * 60)
    
    print(f"\nOllama Base URL: {OLLAMA_BASE_URL}")
    print(f"Configured Model: {OLLAMA_MODEL}")
    
    try:
        # Test if Ollama is running
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        response.raise_for_status()
        models = response.json().get("models", [])
        
        print(f"\n✓ Ollama is running")
        print(f"\nAvailable models:")
        for model in models:
            model_name = model.get("name", "Unknown")
            is_active = "✓ ACTIVE" if model_name == OLLAMA_MODEL else ""
            print(f"  - {model_name} {is_active}")
        
        # Check if configured model is available
        model_names = [m.get("name") for m in models]
        if OLLAMA_MODEL in model_names:
            print(f"\n✓ Configured model '{OLLAMA_MODEL}' is available")
        else:
            print(f"\n✗ WARNING: Configured model '{OLLAMA_MODEL}' is NOT available")
            print(f"  Available models: {', '.join(model_names)}")
            return False
            
        return True
    except requests.exceptions.ConnectionError:
        print(f"\n✗ ERROR: Cannot connect to Ollama at {OLLAMA_BASE_URL}")
        print("  Make sure Ollama is running")
        return False
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        return False

def test_llm_service():
    """Test LLM service with a simple question."""
    print("\n" + "=" * 60)
    print("Testing LLM Service")
    print("=" * 60)
    
    print(f"\nUsing model: {llm_service.model}")
    
    test_question = "What is 2+2? Answer in one sentence."
    print(f"\nTest question: {test_question}")
    print("\nCalling LLM service...")
    
    try:
        response = llm_service.call(
            prompt=test_question,
            temperature=0.3,
        )
        
        print(f"\n✓ LLM Service responded successfully")
        print(f"\nResponse:")
        print(f"  {response[:200]}{'...' if len(response) > 200 else ''}")
        
        return True
    except Exception as e:
        print(f"\n✗ ERROR calling LLM service: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_rag_service():
    """Test RAG service with a simple question."""
    print("\n" + "=" * 60)
    print("Testing RAG Service (Full Integration)")
    print("=" * 60)
    
    try:
        from services.rag_service import rag_service
        
        test_question = "How many entities are in the graph?"
        print(f"\nTest question: {test_question}")
        print("\nCalling RAG service...")
        
        result = rag_service.answer_question(
            question=test_question,
            selected_keys=None,
        )
        
        print(f"\n✓ RAG Service responded successfully")
        print(f"\nAnswer:")
        print(f"  {result.get('answer', 'No answer')[:300]}{'...' if len(result.get('answer', '')) > 300 else ''}")
        print(f"\nContext Mode: {result.get('context_mode', 'Unknown')}")
        print(f"Context Description: {result.get('context_description', 'Unknown')}")
        print(f"Cypher Used: {result.get('cypher_used', False)}")
        
        if result.get('used_node_keys'):
            print(f"Used Node Keys: {len(result.get('used_node_keys', []))} nodes")
        
        return True
    except Exception as e:
        print(f"\n✗ ERROR calling RAG service: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Ollama & qwen2.5 Model Connection Test")
    print("=" * 60)
    
    results = []
    
    # Test 1: Ollama API
    results.append(("Ollama API", test_ollama_api()))
    
    # Test 2: LLM Service
    if results[0][1]:  # Only test if Ollama API works
        results.append(("LLM Service", test_llm_service()))
    
    # Test 3: RAG Service
    if results[-1][1] if len(results) > 1 else False:  # Only test if LLM service works
        results.append(("RAG Service", test_rag_service()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test_name}: {status}")
    
    all_passed = all(result[1] for result in results)
    
    if all_passed:
        print("\n✓ All tests passed! Your application is working with qwen2.5 model.")
    else:
        print("\n✗ Some tests failed. Check the errors above.")
    
    sys.exit(0 if all_passed else 1)

