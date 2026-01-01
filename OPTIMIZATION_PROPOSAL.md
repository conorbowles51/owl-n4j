# Graph Context Optimization Proposal

## Problem
As the graph grows, LLM context becomes too large because:
1. `get_graph_summary()` returns ALL entities with summaries/notes
2. `_build_full_context()` includes ALL entities in the context string
3. No semantic filtering based on the user's question

## Proposed Solution: Two-Stage Intelligent Filtering

### Stage 1: LLM-Generated Cypher Query for Graph Filtering
Before sending context to LLM, use the LLM to generate a Cypher query that finds only relevant nodes based on the question.

**Implementation:**
1. Add a new method `_generate_relevant_subgraph_query()` that:
   - Takes the user's question
   - Uses LLM to generate a Cypher query that finds relevant nodes
   - Returns a filtered set of node keys

2. Modify `answer_question()` to:
   - First generate a relevance-filtering Cypher query
   - Execute it to get relevant node keys
   - Use those keys to build focused context instead of full graph

**Benefits:**
- Reduces context size dramatically (e.g., from 1000 nodes to 50 relevant nodes)
- Maintains accuracy by focusing on question-relevant entities
- Leverages existing Cypher generation infrastructure

### Stage 2: Vector Database for Document-Based Filtering (Optional Enhancement)
Add a vector database (e.g., ChromaDB, Pinecone, or pgvector) to:
1. Store document embeddings during ingestion
2. Use semantic search to find relevant documents for the question
3. Query Neo4j for nodes related to those documents
4. Combine document-based nodes with Cypher-filtered nodes

**Benefits:**
- Finds relevant context even when question doesn't mention specific entities
- Works well for exploratory questions
- Can identify related documents that might not be directly connected in graph

## Implementation Plan

### Phase 1: LLM-Generated Graph Filtering (Recommended First)
1. Add `_generate_relevance_query()` method to `RAGService`
2. Modify `answer_question()` to use filtered context
3. Add configuration for max context size (e.g., 100 nodes max)
4. Fallback to full context if filtering fails

### Phase 2: Vector Database Integration (Future Enhancement)
1. Add vector database service
2. Store document embeddings during ingestion
3. Add semantic search endpoint
4. Integrate with RAG service for hybrid filtering

## Code Structure

```python
# In rag_service.py

def _generate_relevance_query(
    self, 
    question: str, 
    graph_summary: Dict
) -> Optional[List[str]]:
    """
    Generate a Cypher query to find nodes relevant to the question.
    Returns list of node keys, or None if filtering not applicable.
    """
    schema_info = self._build_schema_info(graph_summary)
    
    prompt = f"""
    Based on this question: "{question}"
    
    Generate a Cypher query that finds nodes relevant to answering this question.
    Focus on nodes that are likely to contain information needed to answer it.
    
    {schema_info}
    
    Return ONLY a Cypher query that:
    1. Finds relevant nodes (use MATCH and WHERE clauses)
    2. Returns DISTINCT node keys
    3. Limits results to top 100 most relevant nodes
    
    Example: MATCH (n) WHERE n.name CONTAINS 'suspicious' OR n.summary CONTAINS 'fraud' RETURN DISTINCT n.key LIMIT 100
    """
    
    cypher = self.llm.generate_cypher(question, schema_info)
    if not cypher:
        return None
    
    # Execute and return node keys
    results = self.neo4j.run_cypher(cypher)
    return [row.get('key') for row in results if 'key' in row]

def answer_question(self, question: str, selected_keys: Optional[List[str]] = None):
    graph_summary = self.neo4j.get_graph_summary()
    
    # NEW: Try to filter graph based on question relevance
    if not selected_keys:
        relevant_keys = self._generate_relevance_query(question, graph_summary)
        if relevant_keys and len(relevant_keys) < graph_summary.get('total_nodes', 0) * 0.5:
            # Use filtered context if it's significantly smaller
            selected_keys = relevant_keys
            context_mode = "question-filtered"
        else:
            # Fallback to full context
            context_mode = "full"
    else:
        context_mode = "focused"
    
    # Rest of existing logic...
```

## Configuration Options

Add to config:
- `MAX_CONTEXT_NODES`: Maximum nodes to include in context (default: 100)
- `ENABLE_QUESTION_FILTERING`: Enable LLM-based filtering (default: true)
- `FALLBACK_TO_FULL_CONTEXT`: Fallback if filtering fails (default: true)

## Vector Database Option (Future Enhancement)

**Why Vector DB Helps:**
- Finds relevant documents even when question doesn't mention specific entities
- Works well for exploratory questions ("What's suspicious here?")
- Can identify related documents that might not be directly connected in graph
- Reduces need to send full graph context

**Recommended Options:**
- **ChromaDB**: Lightweight, easy to integrate, good for small-medium datasets
  - Python-native, simple API
  - Can store alongside Neo4j
  - Good for prototyping and small deployments
  
- **pgvector**: If already using PostgreSQL, can add vector extension
  - Leverages existing database infrastructure
  - Good performance, mature solution
  
- **Pinecone**: Managed service, good for production scale
  - Fully managed, scales automatically
  - Good for production deployments

**Integration Architecture:**
1. **During Document Ingestion:**
   - Generate embeddings for each document (using OpenAI, Ollama, or local model)
   - Store embeddings in vector DB with document metadata
   - Link document IDs to Neo4j nodes via citations

2. **During Query:**
   - User asks question → generate question embedding
   - Vector search → find top K relevant documents
   - Query Neo4j for nodes cited by those documents
   - Combine with Cypher-filtered nodes
   - Send smaller, focused context to LLM

3. **Hybrid Approach:**
   - Use vector DB for semantic document search
   - Use Cypher filtering for entity-based queries
   - Combine both for comprehensive context
   - Fallback to full context only if both fail

**Implementation Example:**
```python
def answer_question_with_vector_search(self, question: str):
    # 1. Vector search for relevant documents
    relevant_docs = vector_db.similarity_search(question, k=10)
    doc_ids = [doc.id for doc in relevant_docs]
    
    # 2. Query Neo4j for nodes related to those documents
    cypher = """
    MATCH (n)-[:CITED_IN]->(d:Document)
    WHERE d.id IN $doc_ids
    RETURN DISTINCT n.key AS key
    """
    doc_related_keys = self.neo4j.run_cypher(cypher, doc_ids=doc_ids)
    
    # 3. Also use LLM-generated Cypher for entity filtering
    entity_keys = self._generate_relevance_filter_query(question, graph_summary)
    
    # 4. Combine both sets of keys
    all_relevant_keys = list(set(doc_related_keys + entity_keys))
    
    # 5. Build focused context from combined keys
    context = self._build_focused_context(
        self.neo4j.get_context_for_nodes(all_relevant_keys)
    )
    
    return self.llm.answer_question(question, context)
```

