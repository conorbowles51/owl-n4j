# Decisions

## 2026-05-24: Isolated LangGraph Agent Surface

- Added Agent mode as a separate backend and frontend slice instead of modifying the existing Chat/RAG route.
- Agent API lives under `/api/agent`; the first working message endpoint is `POST /api/agent/messages`, with thread history under `/api/agent/threads`.
- Agent persistence uses new `agent_*` tables so failures are isolated from existing chat tables.
- The LangGraph runtime owns the tool loop, with tools scoped to one case and a strict read-only Cypher guard for generated queries.
- Agent artifacts use stable typed payloads (`graph`, `timeline`, `table`, `map`, `financial`) so the frontend can render mini workspaces now and saved artifacts can be added later.
