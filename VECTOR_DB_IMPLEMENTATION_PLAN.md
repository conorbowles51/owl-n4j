# Vector DB + Neo4j Hybrid Implementation Plan

## Executive Summary

This document outlines the implementation plan for integrating a vector database with the existing Neo4j-based investigation system. The goal is to enable semantic document search to reduce LLM context window size while maintaining all existing graph-based investigation capabilities.

---

## Architecture Overview

### Current State
- **Neo4j**: Stores entities, relationships, and graph structure
- **Document Storage**: Files stored in `ingestion/data/` with metadata in `evidence.json`
- **RAG Service**: Uses LLM-generated Cypher queries to filter graph context (Phase 1 ✅)
- **Context Building**: Sends graph entities to LLM for question answering

### Target State
- **Neo4j**: Continues to store entities, relationships, and graph structure
- **Vector DB**: Stores document embeddings for semantic search
- **Hybrid RAG**: Combines vector search → Neo4j queries → focused context
- **Reduced Context**: Sends only relevant entities (50-200 nodes) instead of full graph

### Data Flow
```
User Question
    ↓
1. Vector DB: Semantic search → Find relevant documents
    ↓
2. Neo4j: Query nodes cited by those documents
    ↓
3. Neo4j: Also apply LLM-generated Cypher filter (existing)
    ↓
4. Combine: Merge document-related nodes + Cypher-filtered nodes
    ↓
5. Build focused context (50-200 nodes)
    ↓
6. Send to LLM for answer
```

---

## Technology Selection

### Recommended: **ChromaDB**

**Why ChromaDB:**
- ✅ Python-native, easy integration
- ✅ Lightweight, no external dependencies
- ✅ Simple API for embedding storage and search
- ✅ Can run embedded (no separate service needed)
- ✅ Good for small-medium datasets (thousands to hundreds of thousands of documents)
- ✅ Supports metadata filtering
- ✅ Open source, MIT licensed

**Alternatives Considered:**
- **pgvector**: Requires PostgreSQL (we don't use Postgres)
- **Pinecone**: Managed service, adds cost and complexity
- **Weaviate**: More complex, overkill for current needs
- **Qdrant**: Good option, but ChromaDB is simpler to start

### Embedding Model Selection

**Recommended: OpenAI `text-embedding-3-small`**
- ✅ High quality embeddings
- ✅ 1536 dimensions (good balance of quality/size)
- ✅ Fast API
- ✅ Cost-effective ($0.02 per 1M tokens)

**Alternative: Local Model (Ollama)**
- ✅ No API costs
- ✅ Privacy (embeddings stay local)
- ✅ Can use `nomic-embed-text` or similar
- ❌ Requires local GPU/CPU resources
- ❌ Slower for large batches

**Decision**: Start with OpenAI for simplicity, add local option later if needed.

---

## Implementation Phases

### Phase 1: Vector DB Infrastructure Setup
**Goal**: Set up ChromaDB and basic embedding storage

**Tasks:**
1. Install ChromaDB (`pip install chromadb`)
2. Create `backend/services/vector_db_service.py`
3. Create vector collection for documents
4. Add embedding generation utility
5. Add configuration for embedding model selection

**Deliverables:**
- Vector DB service with basic CRUD operations
- Embedding generation function
- Configuration options

**Estimated Time**: 2-3 hours

---

### Phase 2: Document Embedding During Ingestion
**Goal**: Generate and store embeddings when documents are processed

**Tasks:**
1. Modify `ingestion/scripts/ingestion.py` to generate embeddings
2. Store embeddings in ChromaDB after document processing
3. Link document IDs between Neo4j and ChromaDB
4. Add error handling for embedding failures
5. Add batch embedding support for efficiency

**Integration Points:**
- `ingestion/scripts/ingestion.py`: `ingest_document()` function
- `backend/services/evidence_service.py`: After document processing
- Neo4j Document nodes: Store ChromaDB document ID as property

**Deliverables:**
- Documents automatically embedded during ingestion
- Document IDs linked between Neo4j and ChromaDB
- Batch embedding for multiple documents

**Estimated Time**: 4-5 hours

---

### Phase 3: Semantic Search Integration
**Goal**: Add semantic search endpoint and integrate with RAG service

**Tasks:**
1. Add semantic search method to `vector_db_service.py`
2. Create API endpoint `/api/vector/search` (optional, for testing)
3. Modify `rag_service.py` to use vector search
4. Implement hybrid filtering (vector + Cypher)
5. Add fallback logic if vector search fails

**Code Changes:**
- `backend/services/rag_service.py`: Add `_find_relevant_documents()` method
- `backend/services/rag_service.py`: Modify `answer_question()` to use hybrid approach
- `backend/routers/chat.py`: Optional endpoint for testing

**Deliverables:**
- Semantic search integrated into RAG pipeline
- Hybrid filtering (vector + Cypher) working
- Fallback to existing Cypher-only filtering

**Estimated Time**: 5-6 hours

---

### Phase 4: Backfill Existing Documents
**Goal**: Generate embeddings for all existing documents

**Tasks:**
1. Create migration script `backend/scripts/backfill_embeddings.py`
2. Query all documents from Neo4j
3. Read document text from storage
4. Generate embeddings in batches
5. Store in ChromaDB
6. Update Neo4j Document nodes with ChromaDB IDs

**Deliverables:**
- Migration script for backfilling embeddings
- All existing documents have embeddings
- Document nodes linked to ChromaDB

**Estimated Time**: 2-3 hours (depends on document count)

---

### Phase 5: Testing & Optimization
**Goal**: Test, optimize, and refine the hybrid approach

**Tasks:**
1. Test with various question types
2. Measure context size reduction
3. Compare answer quality (with/without vector search)
4. Optimize embedding batch sizes
5. Add caching for frequently asked questions
6. Add monitoring/logging for vector search performance

**Deliverables:**
- Test suite for hybrid RAG
- Performance metrics
- Optimization recommendations
- Documentation

**Estimated Time**: 4-5 hours

---

## Detailed Implementation

### 1. Vector DB Service (`backend/services/vector_db_service.py`)

```python
"""
Vector DB Service for semantic document search.
"""

import chromadb
from chromadb.config import Settings
from typing import List, Dict, Optional
from pathlib import Path
import os

from config import BASE_DIR


class VectorDBService:
    """Service for managing document embeddings in ChromaDB."""
    
    def __init__(self):
        # Store ChromaDB data in project data directory
        self.db_path = BASE_DIR / "data" / "chromadb"
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize ChromaDB client (persistent mode)
        self.client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Get or create collection for documents
        self.collection = self.client.get_or_create_collection(
            name="documents",
            metadata={"description": "Document embeddings for semantic search"}
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
            text: Document text content (for retrieval)
            embedding: Vector embedding (list of floats)
            metadata: Optional metadata (filename, case_id, etc.)
        """
        metadata = metadata or {}
        metadata["doc_id"] = doc_id
        
        self.collection.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],  # Store text for retrieval
            metadatas=[metadata]
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
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i] if "distances" in results else None
                })
        
        return formatted
    
    def delete_document(self, doc_id: str) -> None:
        """Delete a document embedding."""
        self.collection.delete(ids=[doc_id])
    
    def get_document(self, doc_id: str) -> Optional[Dict]:
        """Get a document by ID."""
        results = self.collection.get(ids=[doc_id])
        if results["ids"]:
            return {
                "id": results["ids"][0],
                "text": results["documents"][0],
                "metadata": results["metadatas"][0]
            }
        return None


# Singleton instance
vector_db_service = VectorDBService()
```

---

### 2. Embedding Generation Utility (`backend/services/embedding_service.py`)

```python
"""
Embedding generation service.
Supports both OpenAI and local (Ollama) models.
"""

from typing import List, Optional
import os

# Try to import OpenAI (optional)
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Try to import Ollama (optional)
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

from config import settings


class EmbeddingService:
    """Service for generating text embeddings."""
    
    def __init__(self):
        self.provider = os.getenv("EMBEDDING_PROVIDER", "openai").lower()
        self.model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        
        if self.provider == "openai" and OPENAI_AVAILABLE:
            self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        elif self.provider == "ollama" and OLLAMA_AVAILABLE:
            self.client = ollama
        else:
            raise ValueError(f"Embedding provider '{self.provider}' not available")
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats (embedding vector)
        """
        if self.provider == "openai":
            response = self.client.embeddings.create(
                model=self.model,
                input=text
            )
            return response.data[0].embedding
        
        elif self.provider == "ollama":
            response = self.client.embeddings(
                model=self.model,
                prompt=text
            )
            return response["embedding"]
        
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
    
    def generate_embeddings_batch(
        self,
        texts: List[str],
        batch_size: int = 100
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches.
        
        Args:
            texts: List of texts to embed
            batch_size: Number of texts per batch
            
        Returns:
            List of embedding vectors
        """
        embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            if self.provider == "openai":
                # OpenAI supports batch requests
                response = self.client.embeddings.create(
                    model=self.model,
                    input=batch
                )
                batch_embeddings = [item.embedding for item in response.data]
            else:
                # Ollama: process one by one
                batch_embeddings = [
                    self.generate_embedding(text) for text in batch
                ]
            
            embeddings.extend(batch_embeddings)
        
        return embeddings


# Singleton instance
embedding_service = EmbeddingService()
```

---

### 3. Integration with Ingestion Pipeline

**Modify `ingestion/scripts/ingestion.py`:**

```python
# Add at top of file
import sys
from pathlib import Path

# Add backend services to path
backend_dir = Path(__file__).parent.parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

from services.vector_db_service import vector_db_service
from services.embedding_service import embedding_service

# Modify ingest_document() function
def ingest_document(
    text: str,
    doc_name: str,
    doc_metadata: Optional[Dict] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Dict:
    """
    Ingest a document: extract entities, create graph, and store embeddings.
    """
    # ... existing ingestion logic ...
    
    # NEW: Generate and store embedding
    try:
        if log_callback:
            log_callback("Generating document embedding...")
        
        # Generate embedding for full document text
        embedding = embedding_service.generate_embedding(text)
        
        # Get document ID from Neo4j (or generate if not exists)
        doc_key = normalise_key(doc_name)
        # Query Neo4j to get document UUID
        doc_node = db.find_document_by_key(doc_key)
        doc_id = doc_node.get("id") if doc_node else str(uuid.uuid4())
        
        # Store in vector DB
        vector_db_service.add_document(
            doc_id=doc_id,
            text=text[:10000],  # Limit text length for storage
            embedding=embedding,
            metadata={
                "filename": doc_name,
                "doc_key": doc_key,
                "case_id": doc_metadata.get("case_id") if doc_metadata else None,
            }
        )
        
        # Update Neo4j Document node with vector_db_id
        db.update_document(doc_key, {"vector_db_id": doc_id})
        
        if log_callback:
            log_callback("Document embedding stored successfully")
    
    except Exception as e:
        # Don't fail ingestion if embedding fails
        if log_callback:
            log_callback(f"Warning: Failed to generate embedding: {e}")
        print(f"Warning: Embedding generation failed: {e}")
    
    # ... return existing result ...
```

---

### 4. Enhanced RAG Service with Vector Search

**Modify `backend/services/rag_service.py`:**

```python
# Add imports
from services.vector_db_service import vector_db_service
from services.embedding_service import embedding_service

class RAGService:
    # ... existing code ...
    
    def _find_relevant_documents(
        self,
        question: str,
        top_k: int = 10
    ) -> List[str]:
        """
        Use vector search to find documents relevant to the question.
        
        Args:
            question: User's question
            top_k: Number of documents to retrieve
            
        Returns:
            List of document IDs (Neo4j Document.id values)
        """
        try:
            # Generate embedding for question
            query_embedding = embedding_service.generate_embedding(question)
            
            # Search for similar documents
            results = vector_db_service.search(
                query_embedding=query_embedding,
                top_k=top_k
            )
            
            # Extract document IDs
            doc_ids = [r["id"] for r in results]
            return doc_ids
        
        except Exception as e:
            print(f"[RAG] Vector search error: {e}")
            return []
    
    def _get_nodes_from_documents(
        self,
        doc_ids: List[str]
    ) -> List[str]:
        """
        Query Neo4j to find nodes cited by the given documents.
        
        Args:
            doc_ids: List of document IDs from vector search
            
        Returns:
            List of node keys
        """
        if not doc_ids:
            return []
        
        # Query Neo4j for nodes related to these documents
        cypher = """
        MATCH (n)-[:MENTIONED_IN|CITED_IN]->(d:Document)
        WHERE d.id IN $doc_ids OR d.vector_db_id IN $doc_ids
        RETURN DISTINCT n.key AS key
        """
        
        try:
            results = self.neo4j.run_cypher(cypher, doc_ids=doc_ids)
            node_keys = []
            for row in results:
                if isinstance(row, dict):
                    key = row.get('key')
                else:
                    key = row[0] if len(row) > 0 else None
                if key:
                    node_keys.append(key)
            return node_keys
        except Exception as e:
            print(f"[RAG] Error querying nodes from documents: {e}")
            return []
    
    def answer_question(
        self,
        question: str,
        selected_keys: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Answer a question using hybrid vector + graph filtering.
        """
        graph_summary = self.neo4j.get_graph_summary()
        
        # Determine context mode
        if selected_keys and len(selected_keys) > 0:
            # Focused context (user-selected nodes)
            context_mode = "focused"
            node_context = self.neo4j.get_context_for_nodes(selected_keys)
            context = self._build_focused_context(node_context)
            context_description = f"Focused on {len(selected_keys)} selected entity(ies)"
        
        else:
            # Hybrid filtering: Vector search + Cypher filtering
            all_relevant_keys = set()
            
            # 1. Vector search for relevant documents
            doc_ids = self._find_relevant_documents(question, top_k=10)
            doc_node_keys = self._get_nodes_from_documents(doc_ids)
            all_relevant_keys.update(doc_node_keys)
            
            # 2. LLM-generated Cypher filtering (existing)
            cypher_node_keys = self._generate_relevance_filter_query(
                question, graph_summary
            ) or []
            all_relevant_keys.update(cypher_node_keys)
            
            # 3. Determine which context to use
            total_nodes = graph_summary.get('total_nodes', 0)
            relevant_keys_list = list(all_relevant_keys)
            
            if relevant_keys_list and len(relevant_keys_list) < total_nodes * 0.7:
                # Use hybrid filtered context
                context_mode = "hybrid-filtered"
                node_context = self.neo4j.get_context_for_nodes(relevant_keys_list)
                context = self._build_focused_context(node_context)
                context_description = (
                    f"Hybrid-filtered graph ({len(relevant_keys_list)} relevant entities "
                    f"from {total_nodes} total, {len(doc_ids)} documents matched)"
                )
            else:
                # Fallback to full graph context
                context_mode = "full"
                context = self._build_full_context(graph_summary)
                context_description = f"Full graph ({total_nodes} entities)"
        
        # Try Cypher query for specific questions
        query_results = self._try_cypher_query(question, graph_summary)
        
        # Generate answer
        answer = self.llm.answer_question(
            question=question,
            context=context,
            query_results=query_results,
        )
        
        return {
            "answer": answer,
            "context_mode": context_mode,
            "context_description": context_description,
            "cypher_used": query_results is not None,
        }
```

---

### 5. Backfill Script (`backend/scripts/backfill_embeddings.py`)

```python
"""
Backfill embeddings for existing documents.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.services.neo4j_service import neo4j_service
from backend.services.vector_db_service import vector_db_service
from backend.services.embedding_service import embedding_service
from backend.services.evidence_storage import evidence_storage
from config import BASE_DIR

def backfill_embeddings():
    """Generate embeddings for all existing documents."""
    
    # Get all documents from Neo4j
    cypher = """
    MATCH (d:Document)
    RETURN d.id AS id, d.key AS key, d.name AS name
    """
    documents = neo4j_service.run_cypher(cypher)
    
    print(f"Found {len(documents)} documents to process")
    
    processed = 0
    failed = 0
    
    for doc in documents:
        doc_id = doc.get("id") or doc.get("d.id")
        doc_key = doc.get("key") or doc.get("d.key")
        doc_name = doc.get("name") or doc.get("d.name")
        
        if not doc_id or not doc_key:
            print(f"Skipping document with missing ID/key: {doc}")
            continue
        
        try:
            # Find document file
            evidence_file = evidence_storage.find_by_filename(doc_name)
            if not evidence_file:
                print(f"Warning: File not found for document: {doc_name}")
                continue
            
            # Read document text
            file_path = BASE_DIR / evidence_file["stored_path"]
            if not file_path.exists():
                print(f"Warning: File path does not exist: {file_path}")
                continue
            
            # Read text (simplified - may need to handle PDFs, etc.)
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            
            # Generate embedding
            embedding = embedding_service.generate_embedding(text[:10000])
            
            # Store in vector DB
            vector_db_service.add_document(
                doc_id=doc_id,
                text=text[:10000],
                embedding=embedding,
                metadata={
                    "filename": doc_name,
                    "doc_key": doc_key,
                }
            )
            
            # Update Neo4j with vector_db_id
            neo4j_service.run_cypher(
                """
                MATCH (d:Document {id: $doc_id})
                SET d.vector_db_id = $doc_id
                """,
                doc_id=doc_id
            )
            
            processed += 1
            if processed % 10 == 0:
                print(f"Processed {processed} documents...")
        
        except Exception as e:
            print(f"Error processing document {doc_name}: {e}")
            failed += 1
    
    print(f"\nBackfill complete: {processed} processed, {failed} failed")

if __name__ == "__main__":
    backfill_embeddings()
```

---

## Configuration

### Environment Variables

Add to `.env` or `config.py`:

```python
# Embedding Configuration
EMBEDDING_PROVIDER=openai  # or "ollama"
EMBEDDING_MODEL=text-embedding-3-small  # OpenAI model or Ollama model name
OPENAI_API_KEY=your_key_here  # Required if using OpenAI

# Vector DB Configuration
CHROMADB_PATH=data/chromadb  # Relative to project root

# RAG Configuration
VECTOR_SEARCH_ENABLED=true
VECTOR_SEARCH_TOP_K=10  # Number of documents to retrieve
HYBRID_FILTERING_ENABLED=true
```

---

## Testing Strategy

### Unit Tests
1. **Vector DB Service**: Test CRUD operations, search functionality
2. **Embedding Service**: Test embedding generation (mock API calls)
3. **RAG Service**: Test hybrid filtering logic

### Integration Tests
1. **End-to-End RAG**: Test question answering with vector search
2. **Ingestion Pipeline**: Test embedding generation during document ingestion
3. **Backfill Script**: Test embedding backfill for existing documents

### Performance Tests
1. **Embedding Generation**: Measure time for single/batch embeddings
2. **Vector Search**: Measure search latency
3. **Context Size**: Compare context size before/after vector filtering
4. **Answer Quality**: Compare answer quality with/without vector search

---

## Migration Considerations

### Existing Documents
- Run backfill script to generate embeddings for all existing documents
- May take time depending on document count (estimate: 1-2 seconds per document with OpenAI)

### Data Consistency
- Ensure document IDs match between Neo4j and ChromaDB
- Add validation to check for orphaned embeddings
- Handle document deletion (remove from both Neo4j and ChromaDB)

### Rollback Plan
- Vector search is optional - can disable via config
- If issues arise, can fall back to Cypher-only filtering
- ChromaDB data can be deleted without affecting Neo4j

---

## Success Metrics

### Performance
- **Context Size Reduction**: Target 70-90% reduction (e.g., 1000 nodes → 100-300 nodes)
- **Response Time**: Vector search should add <500ms to query time
- **Answer Quality**: Maintain or improve answer quality vs. full context

### Usage
- **Filtering Effectiveness**: Track how often hybrid filtering is used vs. full context
- **Document Match Rate**: Track how many documents are found per query
- **User Satisfaction**: Monitor user feedback on answer quality

---

## Future Enhancements

1. **Chunk-Level Embeddings**: Store embeddings for document chunks, not just full documents
2. **Entity Embeddings**: Store embeddings for entities (not just documents)
3. **Hybrid Search**: Combine keyword search with vector search
4. **Caching**: Cache embeddings and search results for common queries
5. **Multi-Model Support**: Support multiple embedding models simultaneously
6. **Local Model Optimization**: Optimize Ollama integration for production use

---

## Timeline Estimate

- **Phase 1**: 2-3 hours
- **Phase 2**: 4-5 hours
- **Phase 3**: 5-6 hours
- **Phase 4**: 2-3 hours
- **Phase 5**: 4-5 hours

**Total**: ~18-22 hours of development time

---

## Dependencies

### Python Packages
```bash
pip install chromadb openai ollama
```

### Optional (for local embeddings)
```bash
# If using Ollama for embeddings
ollama pull nomic-embed-text
```

---

## Questions & Decisions Needed

1. **Embedding Provider**: OpenAI (cost) vs. Ollama (local, free)?
2. **Document Text Storage**: Store full text in ChromaDB or just metadata?
3. **Chunking Strategy**: Full document embeddings or chunk-level?
4. **Batch Size**: How many documents to process in parallel during ingestion?
5. **Error Handling**: Fail ingestion if embedding fails, or continue?

---

## Next Steps

1. **Review this plan** with team
2. **Decide on embedding provider** (OpenAI vs. Ollama)
3. **Set up development environment** (install ChromaDB, etc.)
4. **Start with Phase 1** (Vector DB infrastructure)
5. **Iterate and test** each phase before moving to next

---

## References

- [ChromaDB Documentation](https://docs.trychroma.com/)
- [OpenAI Embeddings API](https://platform.openai.com/docs/guides/embeddings)
- [Ollama Embeddings](https://github.com/ollama/ollama)
- Existing code: `backend/services/rag_service.py`, `ingestion/scripts/ingestion.py`


