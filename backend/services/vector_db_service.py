"""
Vector DB Service for semantic document search.

Handles storage and retrieval of document embeddings using ChromaDB.
"""

import chromadb
from chromadb.config import Settings
from typing import List, Dict, Optional
from pathlib import Path

from config import BASE_DIR, CHROMADB_PATH


class VectorDBService:
    """Service for managing document and entity embeddings in ChromaDB."""
    
    def __init__(self):
        # Store ChromaDB data in project data directory
        db_path = BASE_DIR / CHROMADB_PATH
        db_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize ChromaDB client (persistent mode)
        self.client = chromadb.PersistentClient(
            path=str(db_path),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Get or create collection for documents
        self.collection = self.client.get_or_create_collection(
            name="documents",
            metadata={"description": "Document embeddings for semantic search"}
        )
        
        # Get or create collection for entities
        self.entity_collection = self.client.get_or_create_collection(
            name="entities",
            metadata={"description": "Entity embeddings for semantic search"}
        )
    
    def add_document(
        self,
        doc_id: str,
        text: str,
        embedding: List[float],
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Add or update a document embedding.

        Args:
            doc_id: Unique document identifier (should match Neo4j Document.id)
            text: Document text content (for retrieval, truncated to 10k chars)
            embedding: Vector embedding (list of floats)
            metadata: Optional metadata (filename, case_id, etc.)
        """
        # Check dimension consistency with existing embeddings
        if self.collection.count() > 0:
            sample = self.collection.peek(1)
            if sample and sample.get("embeddings") and len(sample["embeddings"]) > 0:
                expected = len(sample["embeddings"][0])
                actual = len(embedding)
                if expected != actual:
                    raise ValueError(
                        f"Embedding dimension mismatch: collection has {expected} dims, "
                        f"new embedding has {actual} dims. "
                        f"Delete data/chromadb/ and re-ingest with consistent embedding model."
                    )

        metadata = metadata or {}
        metadata["doc_id"] = doc_id
        
        # Filter out None values - ChromaDB only accepts str, int, float, bool
        # Convert None values to empty strings to preserve keys
        cleaned_metadata = {}
        for k, v in metadata.items():
            if v is None:
                # Convert None to empty string for ChromaDB compatibility
                cleaned_metadata[k] = ""
            elif isinstance(v, (str, int, float, bool)):
                # Keep valid types as-is
                cleaned_metadata[k] = v
            else:
                # Convert other types to string
                cleaned_metadata[k] = str(v)
        
        # Truncate text to avoid storage issues (ChromaDB has limits)
        text_truncated = text[:10000] if len(text) > 10000 else text
        
        self.collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text_truncated],  # Store text for retrieval
            metadatas=[cleaned_metadata]
        )
    
    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filter_metadata: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Search for similar documents.
        
        Args:
            query_embedding: Query vector embedding
            top_k: Number of results to return
            filter_metadata: Optional metadata filters (e.g., {"case_id": "case_123"})
            
        Returns:
            List of dicts with: id, document (text), metadata, distance
        """
        where = filter_metadata if filter_metadata else None
        
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where
            )
            
            # Format results
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
            print(f"[VectorDB] Search error: {e}")
            return []
    
    def delete_document(self, doc_id: str) -> None:
        """Delete a document embedding."""
        try:
            self.collection.delete(ids=[doc_id])
        except Exception as e:
            print(f"[VectorDB] Delete error: {e}")
    
    def get_document(self, doc_id: str) -> Optional[Dict]:
        """Get a document by ID."""
        try:
            results = self.collection.get(ids=[doc_id])
            if results["ids"]:
                return {
                    "id": results["ids"][0],
                    "text": results["documents"][0] if results["documents"] else "",
                    "metadata": results["metadatas"][0] if results["metadatas"] else {}
                }
            return None
        except Exception as e:
            print(f"[VectorDB] Get document error: {e}")
            return None
    
    def count_documents(self) -> int:
        """Get the total number of documents in the collection."""
        try:
            return self.collection.count()
        except Exception as e:
            print(f"[VectorDB] Count error: {e}")
            return 0
    
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
            if sample and sample.get("embeddings") and len(sample["embeddings"]) > 0:
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
        top_k: int = 10,
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
        where = filter_metadata if filter_metadata else None
        
        try:
            results = self.entity_collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
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


# Singleton instance
vector_db_service = VectorDBService()

