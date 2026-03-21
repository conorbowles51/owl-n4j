"""
Vector DB Service for semantic document search.

Handles storage and retrieval of document embeddings using ChromaDB.
"""

from typing import List, Dict, Optional
from pathlib import Path

from config import BASE_DIR, CHROMADB_PATH, CHROMADB_HOST, CHROMADB_PORT


class VectorDBService:
    """Service for managing entity and chunk embeddings in ChromaDB."""

    def __init__(self):
        try:
            import chromadb
            from chromadb.config import Settings
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)

            if "ConfigError" in error_type or "pydantic" in error_msg.lower() or "infer type" in error_msg.lower():
                raise RuntimeError(
                    f"ChromaDB is not compatible with Python 3.14 due to Pydantic v1 issues. "
                    f"Please use Python 3.13 or earlier, or wait for ChromaDB to support Python 3.14. "
                    f"Original error: {error_type}: {error_msg}"
                ) from e
            else:
                raise ImportError(
                    f"ChromaDB is not available: {error_type}: {error_msg}"
                ) from e

        # Connect to ChromaDB via HTTP (shared with evidence engine)
        try:
            self.client = chromadb.HttpClient(
                host=CHROMADB_HOST,
                port=CHROMADB_PORT,
                settings=Settings(anonymized_telemetry=False),
            )
            self.client.heartbeat()
        except Exception as e:
            # Fall back to file-based client if HTTP is unavailable
            print(f"[VectorDB] HTTP client failed ({CHROMADB_HOST}:{CHROMADB_PORT}): {e}")
            print("[VectorDB] Falling back to file-based PersistentClient")
            db_path = BASE_DIR / CHROMADB_PATH
            db_path.mkdir(parents=True, exist_ok=True)
            self.client = chromadb.PersistentClient(
                path=str(db_path),
                settings=Settings(anonymized_telemetry=False),
            )

        # Get or create collection for entities
        self.entity_collection = self.client.get_or_create_collection(
            name="entities",
            metadata={"description": "Entity embeddings for semantic search"}
        )

        # Get or create collection for chunks (passage-level embeddings)
        self.chunk_collection = self.client.get_or_create_collection(
            name="chunks",
            metadata={"description": "Chunk embeddings for passage-level semantic search"}
        )

        # Health flags — set by _validate_collection()
        self._chunks_healthy = True
        self._entities_healthy = True

        # Run startup health checks
        self._chunks_healthy = self._validate_collection("chunks", self.chunk_collection)
        self._entities_healthy = self._validate_collection("entities", self.entity_collection)

        # Clean up legacy documents collection if it exists
        self._delete_legacy_documents_collection()

    def _validate_collection(self, name: str, collection) -> bool:
        """
        Validate that a collection's HNSW index is healthy.

        Returns True if healthy, False otherwise.
        """
        try:
            count = collection.count()
            if count == 0:
                return True

            # peek reads from SQLite — should always work
            peeked = collection.peek(1)
            embeddings = peeked.get("embeddings")
            if not peeked or embeddings is None or len(embeddings) == 0:
                print(f"[VectorDB] WARNING: Collection '{name}' has {count} items but peek() returned no embeddings")
                return False

            # Attempt a minimal query to exercise the HNSW index
            sample_embedding = peeked["embeddings"][0]
            collection.query(query_embeddings=[sample_embedding], n_results=1)
            return True
        except Exception as e:
            print(f"[VectorDB] WARNING: Collection '{name}' failed health check: {e}")
            print(f"[VectorDB] Run 'python backend/scripts/repair_chromadb.py' to rebuild.")
            return False

    def _delete_legacy_documents_collection(self):
        """Delete the legacy 'documents' collection if it exists."""
        try:
            existing = [c.name for c in self.client.list_collections()]
            if "documents" in existing:
                self.client.delete_collection("documents")
                print("[VectorDB] Deleted legacy 'documents' collection")
        except Exception as e:
            print(f"[VectorDB] Warning: Could not delete legacy documents collection: {e}")

    def _check_dimension(self, collection, collection_name: str, query_embedding: List[float]) -> bool:
        """
        Check that query_embedding dimension matches collection's stored dimension.

        Returns True if dimensions match (or collection is empty), False on mismatch.
        """
        try:
            if collection.count() == 0:
                return True
            sample = collection.peek(1)
            if sample and sample.get("embeddings") and len(sample["embeddings"]) > 0:
                expected = len(sample["embeddings"][0])
                actual = len(query_embedding)
                if expected != actual:
                    print(
                        f"[VectorDB] Dimension mismatch in '{collection_name}': "
                        f"collection has {expected}d, query has {actual}d. "
                        f"Run 'python backend/scripts/repair_chromadb.py' to fix."
                    )
                    return False
            return True
        except Exception:
            return True  # If we can't check, let the query proceed

    # =====================
    # Entity Methods
    # =====================

    def add_entity(
        self,
        entity_key: str,
        text: str,
        embedding: List[float],
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Add or update an entity embedding.

        Args:
            entity_key: Unique entity key (human-readable identifier like 'john-smith')
            text: Entity text content for retrieval (name + summary + verified_facts)
            embedding: Vector embedding (list of floats)
            metadata: Optional metadata (entity_type, name, etc.)
        """
        # Check dimension consistency with existing embeddings
        if self.entity_collection.count() > 0:
            sample = self.entity_collection.peek(1)
            if sample and sample.get("embeddings") is not None and len(sample["embeddings"]) > 0:
                expected = len(sample["embeddings"][0])
                actual = len(embedding)
                if expected != actual:
                    raise ValueError(
                        f"Embedding dimension mismatch: entity collection has {expected} dims, "
                        f"new embedding has {actual} dims. "
                        f"Delete data/chromadb/ and re-ingest with consistent embedding model."
                    )

        metadata = metadata or {}
        metadata["entity_key"] = entity_key

        # Filter out None values - ChromaDB only accepts str, int, float, bool
        cleaned_metadata = {}
        for k, v in metadata.items():
            if v is None:
                cleaned_metadata[k] = ""
            elif isinstance(v, (str, int, float, bool)):
                cleaned_metadata[k] = v
            else:
                cleaned_metadata[k] = str(v)

        # Truncate text to avoid storage issues
        text_truncated = text[:10000] if len(text) > 10000 else text

        self.entity_collection.upsert(
            ids=[entity_key],
            embeddings=[embedding],
            documents=[text_truncated],
            metadatas=[cleaned_metadata]
        )

    def search_entities(
        self,
        query_embedding: List[float],
        top_k: int = 50,
        filter_metadata: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Search for similar entities.

        Args:
            query_embedding: Query vector embedding
            top_k: Number of results to return
            filter_metadata: Optional metadata filters (e.g., {"entity_type": "Person"})

        Returns:
            List of dicts with: id (entity_key), text, metadata, distance
        """
        if not self._entities_healthy:
            print("[VectorDB] Entity collection is unhealthy — skipping search. Run repair_chromadb.py.")
            return []

        if not self._check_dimension(self.entity_collection, "entities", query_embedding):
            return []

        where = filter_metadata if filter_metadata else None

        # Clamp n_results to collection size
        count = self.entity_collection.count()
        if count == 0:
            return []
        n_results = min(top_k, count)

        try:
            results = self.entity_collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where
            )

            formatted = []
            if results["ids"] and len(results["ids"][0]) > 0:
                for i in range(len(results["ids"][0])):
                    formatted.append({
                        "id": results["ids"][0][i],
                        "text": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "distance": results["distances"][0][i] if "distances" in results and results["distances"] else None
                    })

            return formatted
        except Exception as e:
            print(f"[VectorDB] Entity search error: {e}")
            return []

    def delete_entity(self, entity_key: str) -> None:
        """Delete an entity embedding."""
        try:
            self.entity_collection.delete(ids=[entity_key])
        except Exception as e:
            print(f"[VectorDB] Entity delete error: {e}")

    def get_entity(self, entity_key: str) -> Optional[Dict]:
        """Get an entity by key."""
        try:
            results = self.entity_collection.get(ids=[entity_key])
            if results["ids"]:
                return {
                    "id": results["ids"][0],
                    "text": results["documents"][0] if results["documents"] else "",
                    "metadata": results["metadatas"][0] if results["metadatas"] else {}
                }
            return None
        except Exception as e:
            print(f"[VectorDB] Get entity error: {e}")
            return None

    def count_entities(self) -> int:
        """Get the total number of entities in the collection."""
        try:
            return self.entity_collection.count()
        except Exception as e:
            print(f"[VectorDB] Entity count error: {e}")
            return 0

    # =====================
    # Chunk Methods
    # =====================

    def add_chunk(
        self,
        chunk_id: str,
        text: str,
        embedding: List[float],
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Add or update a chunk embedding.

        Args:
            chunk_id: Unique chunk identifier (format: "{doc_id}_chunk_{index}")
            text: Chunk text content
            embedding: Vector embedding (list of floats)
            metadata: Metadata including doc_id, doc_name, case_id, chunk_index, etc.
        """
        # Check dimension consistency with existing embeddings
        if self.chunk_collection.count() > 0:
            sample = self.chunk_collection.peek(1)
            if sample and sample.get("embeddings") is not None and len(sample["embeddings"]) > 0:
                expected = len(sample["embeddings"][0])
                actual = len(embedding)
                if expected != actual:
                    raise ValueError(
                        f"Embedding dimension mismatch: chunk collection has {expected} dims, "
                        f"new embedding has {actual} dims. "
                        f"Delete data/chromadb/ and re-ingest with consistent embedding model."
                    )

        metadata = metadata or {}
        metadata["chunk_id"] = chunk_id

        # Filter out None values - ChromaDB only accepts str, int, float, bool
        cleaned_metadata = {}
        for k, v in metadata.items():
            if v is None:
                cleaned_metadata[k] = ""
            elif isinstance(v, (str, int, float, bool)):
                cleaned_metadata[k] = v
            else:
                cleaned_metadata[k] = str(v)

        self.chunk_collection.upsert(
            ids=[chunk_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[cleaned_metadata]
        )

    def search_chunks(
        self,
        query_embedding: List[float],
        top_k: int = 50,
        filter_metadata: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Search for similar chunks.

        Args:
            query_embedding: Query vector embedding
            top_k: Number of results to return
            filter_metadata: Optional metadata filters (e.g., {"case_id": "case_123"})

        Returns:
            List of dicts with: id (chunk_id), text, metadata, distance
        """
        if not self._chunks_healthy:
            print("[VectorDB] Chunks collection is unhealthy — skipping search. Run repair_chromadb.py.")
            return []

        if not self._check_dimension(self.chunk_collection, "chunks", query_embedding):
            return []

        where = filter_metadata if filter_metadata else None

        # Clamp n_results to collection size
        count = self.chunk_collection.count()
        if count == 0:
            return []
        n_results = min(top_k, count)

        try:
            results = self.chunk_collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where
            )

            formatted = []
            if results["ids"] and len(results["ids"][0]) > 0:
                for i in range(len(results["ids"][0])):
                    formatted.append({
                        "id": results["ids"][0][i],
                        "text": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "distance": results["distances"][0][i] if "distances" in results and results["distances"] else None
                    })

            return formatted
        except Exception as e:
            print(f"[VectorDB] Chunk search error: {e}")
            return []

    def count_chunks(self) -> int:
        """Get the total number of chunks in the collection."""
        try:
            return self.chunk_collection.count()
        except Exception as e:
            print(f"[VectorDB] Chunk count error: {e}")
            return 0

    def delete_chunks_by_doc(self, doc_id: str) -> None:
        """Delete all chunks belonging to a document."""
        try:
            results = self.chunk_collection.get(where={"doc_id": doc_id})
            if results and results["ids"]:
                self.chunk_collection.delete(ids=results["ids"])
        except Exception as e:
            print(f"[VectorDB] Delete chunks error: {e}")

    def delete_chunk(self, chunk_id: str) -> None:
        """Delete a single chunk embedding."""
        try:
            self.chunk_collection.delete(ids=[chunk_id])
        except Exception as e:
            print(f"[VectorDB] Chunk delete error: {e}")

    # =====================
    # Case-level Operations
    # =====================

    def delete_chunks_by_case(self, case_id: str) -> int:
        """Delete all chunk embeddings for a case. Returns count deleted."""
        try:
            results = self.chunk_collection.get(where={"case_id": case_id})
            if results and results["ids"]:
                self.chunk_collection.delete(ids=results["ids"])
                return len(results["ids"])
            return 0
        except Exception as e:
            print(f"[VectorDB] Delete chunks by case error: {e}")
            return 0

    def delete_entities_by_case(self, case_id: str) -> int:
        """Delete all entity embeddings for a case. Returns count deleted."""
        try:
            results = self.entity_collection.get(where={"case_id": case_id})
            if results and results["ids"]:
                self.entity_collection.delete(ids=results["ids"])
                return len(results["ids"])
            return 0
        except Exception as e:
            print(f"[VectorDB] Delete entities by case error: {e}")
            return 0

    # =====================
    # Audit / Maintenance
    # =====================

    def get_all_metadata(self, collection_name: str) -> list:
        """
        Get all IDs and metadata from a collection (for audit).

        Args:
            collection_name: One of 'entities', 'chunks'

        Returns:
            List of (id, metadata) tuples.
        """
        try:
            col = {
                "entities": self.entity_collection,
                "chunks": self.chunk_collection,
            }[collection_name]
            results = col.get(include=["metadatas"])
            return list(zip(results.get("ids", []), results.get("metadatas", [])))
        except Exception as e:
            print(f"[VectorDB] get_all_metadata error: {e}")
            return []

    def delete_by_ids(self, collection_name: str, ids: list) -> int:
        """
        Delete specific IDs from a named collection.

        Args:
            collection_name: One of 'entities', 'chunks'
            ids: List of IDs to delete

        Returns:
            Count of items deleted.
        """
        if not ids:
            return 0
        try:
            col = {
                "entities": self.entity_collection,
                "chunks": self.chunk_collection,
            }[collection_name]
            col.delete(ids=ids)
            return len(ids)
        except Exception as e:
            print(f"[VectorDB] delete_by_ids error: {e}")
            return 0


# Lazy singleton instance - only create when accessed
_vector_db_service = None

def get_vector_db_service():
    """Get or create the vector DB service singleton (lazy initialization)."""
    global _vector_db_service
    if _vector_db_service is None:
        try:
            _vector_db_service = VectorDBService()
        except ImportError as e:
            # If ChromaDB can't be imported (e.g., Python 3.14 compatibility), return None
            print(f"Warning: VectorDBService unavailable: {e}")
            return None
    return _vector_db_service

# For backwards compatibility, try to create instance but handle errors gracefully
# This will fail on Python 3.14 due to ChromaDB's Pydantic v1 incompatibility
# but we catch it so the app can still start
vector_db_service = None
try:
    vector_db_service = VectorDBService()
except Exception as e:
    # Catch any exception - ImportError, RuntimeError, ConfigError, or any other error
    error_type = type(e).__name__
    error_msg = str(e)

    # Check if it's a Python 3.14 / ChromaDB compatibility issue
    if "ConfigError" in error_type or "pydantic" in error_msg.lower() or "infer type" in error_msg.lower() or "Python 3.14" in error_msg:
        print(f"Warning: VectorDBService unavailable due to Python 3.14 / ChromaDB compatibility issue.")
        print(f"   Error: {error_type}")
        print(f"   Vector search will be disabled. Consider using Python 3.13 or earlier.")
    else:
        print(f"Warning: Could not initialize VectorDBService: {error_type}: {error_msg}")
        print("   Vector search will be disabled.")
    vector_db_service = None
