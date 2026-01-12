# AI Assistant Prompt Generation Explanation

This document explains how prompts are generated when using the AI Assistant in the graph view.

## Overview

When you ask a question in the AI Assistant, the system builds a comprehensive prompt that includes:
1. System context (from your profile configuration)
2. Graph context (entities, relationships, summaries)
3. Optional query results (from Cypher queries)
4. Your question
5. Analysis guidelines and formatting instructions

## Prompt Structure

The final prompt sent to the LLM has this structure:

```
{system_context}

You have access to the following information from the investigation graph:

{context}
{query_results}

Based on this information, please answer the investigator's question:
"{question}"

Guidelines:
- {analysis_guidance}
- Format your response using markdown (use **bold** for emphasis, bullet points with -)
- Do NOT use tables - use bullet points or numbered lists instead for structured data
- Be specific and cite entity names when relevant
- If you identify suspicious patterns, explain them
- Use ALL available information from the context above - extract and synthesize details from summaries, notes, and relationships
- If specific details (like exact dates, amounts, or names) are mentioned in the context, include them in your answer
- Only say "insufficient information" if the context truly contains NO relevant information about the question
- If the context has related information (even if incomplete), provide what you can find and note what additional details would be helpful
- Keep your response focused and professional
- Highlight any connections or patterns you notice

Answer:
```

## Components Explained

### 1. System Context (`system_context`)

**Source**: Loaded from your profile's `chat.system_context` field (default profile is `profiles/generic.json`)

**Example** (from generic profile):
```
You are an AI assistant helping to analyze and understand documents.
```

**Where it's set**: Profile editor → Chat Configuration → System Context

**Purpose**: Sets the role and general behavior of the AI assistant

### 2. Graph Context (`context`)

The context varies based on how you're querying:

#### A. Focused Context (When nodes are selected)

If you've selected specific nodes in the graph:
- **Mode**: `focused`
- **Content**: Information about the selected nodes and their connections
- **Format**:
```
=== SELECTED ENTITIES AND CONNECTIONS ===

[EntityType] EntityName (key: entity-key)
  Summary: [summary text]
  Notes: [notes text]
  Connections:
    → [RELATIONSHIP_TYPE] ConnectedEntity (EntityType)
       Summary: [connection summary]
```

#### B. Hybrid-Filtered Context (Automatic filtering)

If no nodes are selected, the system tries to filter relevant entities:
- **Mode**: `hybrid-filtered`
- **Methods**:
  1. **Vector Search**: Semantic search of document embeddings to find relevant documents and their entities
  2. **Cypher Filtering**: LLM-generated Cypher query to find relevant entities based on the question
- **Content**: Same format as focused context, but only includes filtered entities
- **Condition**: Only used if filtered entities are < 70% of total entities

#### C. Full Graph Context (Fallback)

If filtering doesn't work or returns too many results:
- **Mode**: `full`
- **Content**: Overview of all entities in the graph
- **Format**:
```
=== INVESTIGATION GRAPH OVERVIEW ===
Total Entities: [count]
Total Relationships: [count]

Entity Types:
  - Person: [count]
  - Company: [count]
  ...

Relationship Types:
  - TRANSFERRED_TO: [count]
  - WORKS_FOR: [count]
  ...

=== ENTITIES ===

[EntityType] EntityName (key: entity-key)
  Summary: [summary text - truncated if > 1000 chars]
  Notes: [notes text - truncated if > 800 chars]
```

**Limits**:
- Maximum 200 entities shown (prioritizes entities with summaries/notes)
- Summaries truncated to 1000 characters
- Notes truncated to 800 characters

### 3. Query Results (`query_results`)

**Optional**: Only included if a direct Cypher query was generated and executed

**When it appears**: The system attempts to generate a Cypher query for specific, answerable questions (e.g., "How many transactions are there?", "List all companies")

**Format**:
```
Query Results:
[formatted query results from Neo4j]
```

**Purpose**: Provides direct database query results for factual questions

### 4. User Question (`question`)

Your exact question as typed in the AI Assistant interface.

### 5. Analysis Guidance (`analysis_guidance`)

**Source**: Loaded from your profile's `chat.analysis_guidance` field

**Example** (from generic profile):
```
Provide clear explanations and highlight important connections.
```

**Where it's set**: Profile editor → Chat Configuration → Analysis Guidance

**Purpose**: Provides domain-specific guidance for how to analyze and present information

## Where to See the Generated Prompt

The generated prompt is logged in multiple places:

1. **Backend Console**: The prompt is logged using `log_section()` with the title "Prompt: final (answer synthesis)"

2. **System Logs**: The full prompt is stored in `debug_log["final_prompt"]` in the system logs (accessible via the system logs feature)

3. **Debug Log**: Each AI Assistant response includes a debug log with:
   - `final_prompt`: The complete prompt sent to the LLM
   - `context_mode`: Which context mode was used (focused/hybrid-filtered/full)
   - `context_preview`: First 1000 characters of the context
   - `graph_summary`: Overview of the graph
   - `vector_search`: Results from vector search (if used)
   - `cypher_filter_query`: Cypher filtering results (if used)
   - `cypher_answer_query`: Direct Cypher query results (if used)

## Code Locations

- **Prompt Generation**: `backend/services/llm_service.py` → `answer_question_with_prompt()` (lines 330-378)
- **Context Building**: `backend/services/rag_service.py` → `answer_question()` (lines 544-810)
- **System Context Loading**: `backend/services/llm_service.py` (line 28-30)
- **Profile Loading**: `backend/profile_loader.py` → `get_chat_config()`

## Customization

You can customize the prompt by editing your profile:

1. Go to **Settings** → **LLM Profiles**
2. Edit or create a profile
3. In the **Chat Configuration** section:
   - **System Context**: Define the AI's role and general behavior
   - **Analysis Guidance**: Provide domain-specific analysis instructions
   - **Temperature**: Control response creativity (0.0-1.0)

Changes take effect immediately for new queries.
