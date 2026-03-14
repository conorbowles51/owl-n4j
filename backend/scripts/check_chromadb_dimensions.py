"""
Diagnostic: Check ChromaDB collections for mixed embedding dimensions.

Run from backend directory:
    python scripts/check_chromadb_dimensions.py
"""
import sys
sys.path.insert(0, ".")

from services.vector_db_service import vector_db_service

if vector_db_service is None:
    print("ERROR: VectorDBService not available")
    sys.exit(1)

for name, col in [
    ("entities", vector_db_service.entity_collection),
    ("chunks", vector_db_service.chunk_collection),
]:
    count = col.count()
    if count == 0:
        print(f"{name}: empty")
        continue

    try:
        results = col.get(include=["embeddings"])
    except Exception as e:
        print(f"{name}: CORRUPTED - {count} items but cannot read index: {e}")
        continue

    dims = {}
    for emb in results["embeddings"]:
        dims.setdefault(len(emb), 0)
        dims[len(emb)] += 1

    if len(dims) == 1:
        dim, n = next(iter(dims.items()))
        print(f"{name}: OK - all {n} embeddings are {dim}-dimensional")
    else:
        print(f"{name}: MISMATCH DETECTED - {len(dims)} different dimensions:")
        for dim, n in sorted(dims.items()):
            print(f"  {dim}d: {n} items")
