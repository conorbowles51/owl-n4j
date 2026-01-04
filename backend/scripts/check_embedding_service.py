#!/usr/bin/env python3
"""
Diagnostic script to check if the embedding service is properly configured.
"""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

try:
    from services.embedding_service import embedding_service
    from config import EMBEDDING_PROVIDER, EMBEDDING_MODEL, OPENAI_API_KEY
    
    from config import LLM_PROVIDER
    
    print("=" * 60)
    print("Embedding Service Diagnostic")
    print("=" * 60)
    
    print("\nConfiguration:")
    print(f"  LLM_PROVIDER: {LLM_PROVIDER}")
    print(f"  EMBEDDING_PROVIDER: {EMBEDDING_PROVIDER} (auto-matched to LLM if not set)")
    print(f"  EMBEDDING_MODEL: {EMBEDDING_MODEL}")
    
    if embedding_service is None:
        print("\n❌ ERROR: Embedding service is not initialized")
        if EMBEDDING_PROVIDER == "openai":
            if OPENAI_API_KEY:
                print(f"  OPENAI_API_KEY: {'*' * 20} (set)")
            else:
                print("  OPENAI_API_KEY: ❌ NOT SET")
        print("\nPossible issues:")
        print("  1. Missing OPENAI_API_KEY (if using OpenAI)")
        print("  2. Invalid EMBEDDING_PROVIDER (must be 'openai' or 'ollama')")
        print("  3. Embedding service failed to initialize (check logs)")
        print("  4. Ollama not running (if using Ollama)")
        sys.exit(1)
    else:
        print("✅ Embedding service is initialized")
        print(f"  Provider: {embedding_service.provider}")
        print(f"  Model: {embedding_service.model}")
        
        # Test embedding generation
        print("\nTesting embedding generation...")
        try:
            test_text = "This is a test document for embedding generation."
            embedding = embedding_service.generate_embedding(test_text)
            print(f"✅ Successfully generated embedding (dimension: {len(embedding)})")
        except Exception as e:
            print(f"❌ Failed to generate embedding: {e}")
            sys.exit(1)
    
    print("\n" + "=" * 60)
    print("✅ All checks passed! Embedding service is working.")
    print("=" * 60)
    
except Exception as e:
    print(f"❌ Error checking embedding service: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

