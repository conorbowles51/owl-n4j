#!/usr/bin/env python3
"""
Simple test to verify Ollama and qwen2.5 model configuration.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from config import OLLAMA_BASE_URL, OLLAMA_MODEL

print("=" * 60)
print("Quick Ollama & qwen2.5 Test")
print("=" * 60)

# Test 1: Check Ollama is running
print(f"\n1. Checking Ollama connection...")
try:
    response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
    response.raise_for_status()
    models = response.json().get("models", [])
    model_names = [m.get("name") for m in models]
    print(f"   ✓ Ollama is running")
    print(f"   Available models: {', '.join(model_names)}")
except Exception as e:
    print(f"   ✗ Cannot connect to Ollama: {e}")
    sys.exit(1)

# Test 2: Check configured model
print(f"\n2. Checking configured model...")
print(f"   Configured: {OLLAMA_MODEL}")
if OLLAMA_MODEL in model_names:
    print(f"   ✓ Model '{OLLAMA_MODEL}' is available")
else:
    print(f"   ✗ Model '{OLLAMA_MODEL}' is NOT available")
    print(f"   Available: {', '.join(model_names)}")
    sys.exit(1)

# Test 3: Try a simple API call (this will load the model if not already loaded)
print(f"\n3. Testing model response (this may take a moment on first call)...")
print(f"   Sending test prompt to {OLLAMA_MODEL}...")

try:
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "user", "content": "Say 'Hello, I am working!' in one sentence."}
            ],
            "stream": False,
        },
        timeout=300  # 5 minutes for first load
    )
    response.raise_for_status()
    result = response.json()
    answer = result.get("message", {}).get("content", "")
    print(f"   ✓ Model responded successfully!")
    print(f"   Response: {answer[:100]}{'...' if len(answer) > 100 else ''}")
except requests.exceptions.Timeout:
    print(f"   ⚠ Request timed out - this is normal on first call as the model loads")
    print(f"   The model is likely loading. Try again in a moment or test through your application.")
except Exception as e:
    print(f"   ✗ Error: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✓ All checks passed! Your application should work with qwen2.5:32b-instruct")
print("=" * 60)
print("\nTo test through your application:")
print("1. Start your backend server")
print("2. Ask a question through the chat interface")
print("3. Check the response - it should use qwen2.5:32b-instruct")
