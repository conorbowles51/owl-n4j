# 8. Loupe's case-wide screens and where phone data fits

Read-only, 2026-10-29, on `integration/evidence-main-reunion`. Main claims re-checked by hand (listed at the
end). Headline: Graph, Table, Timeline and Map read Neo4j with no fixed list of node types, so phone nodes
already appear on all four with no phone-specific code. Phone data is missing from semantic search: the old
Cellebrite pipeline embeds nothing in Chroma.

## 1. Top-level screens

Routes `frontend_v2/src/app/routes.tsx:149-171`; navigation `components/ui/sidebar.tsx:47-81`. Sidebar
groups: Investigation (Cases, Triage), Workspace (Workspace, Dossiers, Reports), Case views (Graph, Timeline,
Map, Table, with a layer switcher), Full case data (Financial, Cellebrite, Evidence), AI (Chat, Agent).

- **Case layer switcher** ("All data" / "Significant", `features/significant/components/CaseLayerSwitcher.tsx:28-41`),
  backed by `routers/significant.py:79-157` and `services/significant_service.py` (at most 10,000 keys per
  operation, `:17`); also narrows Chat and Agent.
- **Workspace**: Overview, Casework (Notes, Findings, Theories), Deadlines (`WorkspaceRedesignPage.tsx:54-76`);
  findings and theories carry state, significance and confidence 0 to 100 (`postgres/models/workspace_entry.py:30-41`);
  attachments to evidence, graph_entity, dossier, entry, task, deadline, timeline_event, agent_artifact or
  witness, each supports, contradicts or context, with a `source_anchor` (`:43-53`, `:310`).
- **Workspace AI panel**: statement summaries, comparisons, theory analyses (`services/workspace_ai_service.py:30`),
  accepted or rejected by the investigator.
- **Notebook**: side panel in Graph, Evidence and Agent; notes are workspace entries linked to entity,
  evidence, document, timeline_event or agent_artifact (`notebook_service.py:17-22`, `routers/notebook.py:100-205`).
- **Evidence**: folder tree, upload including resumable, processing profiles; AI file summaries with page
  citations (`FileSummaryPanel.tsx`); transcript viewer with speaker rename and merge (`evidence.py:903`);
  case text search (`evidence.py:844`); previews by extension (`FilePreviewPanel.tsx:10-55`), none for a phone
  extraction; Cellebrite zips queued to the engine (`FileListToolbar.tsx:280-293`, `evidence.py:1144-1285`).
- **Financial**: tabs in `FinancialNavigation.tsx:18-38`; `routers/financial_ledger.py` (70 read routes),
  `financial_adjudication.py` (29 write routes) and others.
- **Graph**: expand, shortest path, PageRank, Louvain, betweenness (`algorithm_service.py:102,361`); similar
  entities and merge (an engine job, `graph.py:1677`); recycle bin, pinned facts, geocode, node and edge
  editing, comparison, subgraph analysis in the browser.
- **Table**: same fetch as Graph (`TablePage.tsx:78`); bulk edit one update per row; browser CSV.
- **Timeline**: type, entity, date and text filters; keyboard; multi-select curation; saved views; add
  financial items; PDF and CSV (`routers/timeline.py`, `services/neo4j/timeline_service.py`, `services/timeline_entries.py`).
- **Map**: heatmap, confidence tiers, "Needs review" list, proximity, box and polygon filter, pin correction
  (`routers/graph.py:659,694,2172,2210`, `services/neo4j/geo_service.py`). `HotspotPanel`,
  `RouteAnalysisPanel`, `MovementTrails`, `HeatmapLayer` exist but nothing imports them (grep confirmed).
- **Chat**: RAG over Chroma and the graph (`services/rag_service.py`).
- **Agent**: LangGraph (`services/agent/tools.py:2319-2475`) with graph tools, `search_documents`,
  `run_readonly_cypher`, timeline and map tools, three financial tools and artifact builders; no phone tool.
- **Dossiers**: person or entity profile tied to at most one graph entity (`dossier_service.py:321-326`);
  brief, assessments, media, interviews, up to 100 hand-entered contacts (`:268-292`); links (`:41`); source
  viewer opens a page or media time (`DossierSourceViewer.tsx:13-49`).
- **Reports**: builder with HTML or PDF (`ReportBuilder.tsx:30-36,111-117`). **No backend answers it**: the
  frontend calls `/api/reports` (`features/reports/hooks/use-reports.ts:26,35`); the only `/reports` route is
  the Cellebrite router's (`routers/cellebrite.py:48`).
- **Triage**: server-folder inventory built for 500K+ files (`routers/triage.py`, `services/triage/`); none of
  its processors recognise Cellebrite or UFDR.

## 2. Cross-evidence screens: sources, extension points, limits

The old engine writer stamps `case_id` and `source_type:"cellebrite"` on every node
(`evidence-engine/app/pipeline/cellebrite/neo4j_writer.py:181-192,238`).

- **Timeline**: `MATCH (n)` with no label filter (`timeline_service.py:246`); a node qualifies with `case_id`
  and any of `date`, `timestamp`, `start_time`, `capture_time`, `creation_time`, `date_time`, `datetime`
  (`:19-32`); type is `labels(n)[0]`; filter list built from loaded types (`use-timeline-data.ts:122-130`).
  Phone events already appear, untyped and without a source link. Pages of 2,000 server-side (`timeline.py:132`);
  client stops after 100 pages, about 200k events (`use-timeline-data.ts:44-60`).
- **Map**: `MATCH (n)` on nodes with coordinates, excluding Document and RecycleBin (`geo_service.py:72-79`);
  **no LIMIT, no pagination**; geocoding provenance only, no `source_files`.
- **Graph and Table**: whole case loaded with no cap (`use-graph-data.ts:9` passes no `limit` although the
  server supports one, `graph_service.py:241`); search `CONTAINS`, 20 default and 100 max (`graph.py:593`);
  Similar Entities compares every pair with `SequenceMatcher` (`entity_service.py:426-528`).
- **Search**: no global search box (`commandPaletteOpen` unused); full-text is a Postgres `LIKE` over extracted
  document text (`evidence_text_search_service.py:133`), which cannot see phone messages.
- **Chat and Agent**: Chroma collections `entities` and `chunks` (`vector_db_service.py:50,56`); chunks carry
  `doc_id`, `case_id`, `page_start`, `page_end` (`chunk_embed.py:269`); no phone embedding. Chat limits
  (`config.py:73-94`): top_k 50 reranked to 15 chunks and 10 entities, 1 hop, at most 5 sources
  (`rag_service.py:2356`). Agent: 28 tool calls per run (`agent/service.py:42`), Cypher 50 rows, 8 chunks.
- **Dossiers, Workspace, Notebook**: phone items attachable only as `graph_entity`; no link type for a
  message, call or contact; the workspace picker returns nothing for graph_entity (`workspace_entry_service.py:492`).

**Defects found (not fixed):**
- The Cypher panel posts to `/api/graph/cypher`, which does not exist (`graph/api.ts:459`).
- The fallback `/api/query` (`routers/query.py:32,49`) is not limited to the current case, blocks writes only
  by looking for words in the query text, and runs in a write transaction (`driver.py:97-102`).
- "Not a duplicate" calls `/reject-merge-pair`; the backend serves `/reject-merge` (`graph.py:1869`).
- Chat's generated Cypher is not required to use `$case_id`; the agent's check does require it
  (`agent/cypher_safety.py:454`).
- `CitationPanel.tsx` is a stub nothing imports.
- The chat prompt says "If no page number is available, use page 1" (`llm_service.py:503`).
- Agent answers render without `onOpenDocument` (`AgentPage.tsx:1236`), so their links do nothing.

## 3. Citation, correction and proof-class patterns to reuse

- `ref_id` from file sha256 plus row content hash, `TX-XXXX-XXXX-XXXX` (`services/financial/references.py:394`;
  rationale `:1-60`); survives re-ingest.
- Locators: `SourceRectangle` in thousandths of a point (`financial/locators.py:108`); `Locator` kinds
  page_rectangle, page_only, not_positional, unlocated (`:294`, `lib/locator.ts:33`). UI:
  `LedgerSourceDialog.tsx` then `TransactionSourceHighlight` fetches `GET /api/evidence/{id}/page/{n}/image`
  (`evidence.py:2327`); `SourceHighlight.tsx:71` draws the box with a sentence for each missing-box reason;
  citation shape `lib/source-citation.ts:4`. `not_positional` fits a phone record.
- Document viewer opens at a page or media time (`components/ui/document-viewer.tsx:62,166,259-270`), no boxes.
- Workspace AI is strictest: every claim must carry `citation_ids` resolving to sources or generation fails
  (`workspace_ai_service.py:619-670`); each source stores `evidence_file_id`, `source_anchor{page |
  start_seconds/end_seconds | start_char}`, `content_hash`, `excerpt`, `url` (`:115,285`); rendered as "file,
  p.N" or "m:ss" (`WorkspaceAIPanel.tsx:88-107`). A phone source needs a new anchor kind.
- Chat citations are weaker: `ChatSource{filename, excerpt, page}` (`chat.py:67`) matched by filename.
- Corrections: `financial/corrections.py:24` inserts a replacement and marks the original `superseded_by_id`
  (`:76,103-106`); totals count admitted rows only (`ledger_summary.py:103-110`); UI `CorrectionHistory.tsx`,
  `StatementRowCorrectionStatus.tsx`.
- Proof class p0 to p4 (`enums.py:20-39`), computed in `financial/proof_class.py:144`, permissions `:212-233`,
  badges `LedgerTable.tsx:112-118`, wording `lib/ledger-format.ts:237-266`. p4 is "a figure asserted in
  unstructured material".
- Claims about money: `financial/claim_comparison.py:15` (quote, location, speaker, payer, payee, amount
  range, dates); `correlation.py` matches against the ledger as corroborated, contradicted or unresolved;
  "Correlation never promotes".
- Adjudication: append-only decision log (`financial/decisions.py`); every write route records a named person
  and reason (`routers/financial_adjudication.py:1-30`).

## 4. Where phone features plug in

- **Timeline**: phone events present; needs `source_type`, source file and record reference in the page query
  (today only in export, `timeline_service.py:331-344`), a phone filter, readable labels, opening the record.
- **Map**: present; needs a cap or tiling, source provenance, possibly wiring the unused trail, route and
  hotspot panels.
- **Graph, Table, entities**: present; needs resolution between phone contacts and document entities and a
  default cap.
- **Chat and Agent**: embed message, call and email text with record metadata; a phone citation anchor;
  optional phone tools.
- **Financial counterparties**: `account_identity.py:38` `EntityLink{party_id, entity_key}` with
  `identity_graph.py:103-105,213` already writes `(FinancialParty)-[:REVIEWED_SAME_IDENTITY]->(any case node)`;
  the UI picks via `/api/graph/search` (`AccountIdentityReview.tsx:172`). Missing: a phone-number identifier
  type (`account_identity.py:24`) and a link from a counterparty row.
- **Dossiers, Workspace, Notebook**: a link type for a phone record with a record anchor; import dossier
  contacts from a phone person.
- **Reports**: needs a backend first.
- **Evidence**: a preview or summary for an extraction.

## 5. What Loupe lacks entirely

A conversation viewer; a media gallery for an extraction; time-windowed co-location across devices;
multi-phone comparison; contact deduplication across phones; full-text and semantic search over messages; a
citation anchor for a non-page record; scale protection on Map and Graph.

## Recorded feedback (quoted exactly)

- `docs/alex-financial-acceptance.md:118`: "Accepted: select one or several Transactions and add them to
  Loupe's case Timeline; Findings and Observations must also offer the action. This is an addition to the
  financial investigator journey, not an export file or a separate financial-only chart."
- `docs/financial-workflows/finding-cards-2026-09-24.md:3-5`: "The investigator needs to scan saved work and
  reach Edit or Add to Timeline without searching the far edge of a wide screen."
- `docs/financial-workflows/agent-analysis-and-reading-follow-up-2026-09-25.md:5-6`: "From a case's Agent
  screen, ask for an analysis of all imported payments and get an evidence-backed account".
- `release-verification-2026-09-23.md:67`: "Alex's large chat still requires a complete run through the
  actual providers and live host."
- `docs/loupe-build-state.md:668`: the deployed Financial screens were rejected with "please design this from
  an investigators perspective".
- `loupe-build-state.md:200`: "build outward from a simple working flow rather than rethink the whole platform."
- `feedback-implementation-plan-2026-09-23.md:208`: "Reuse one source viewer".
- No recorded feedback about Map, Graph, Dossiers, Reports, the Evidence viewer or the phone screens in
  Loupe. `docs/owl-project-brief.md:15` ("It is not a phone-extraction tool. It is a multi-source forensic
  analysis platform") is Neil's positioning, not user feedback.

Re-checked by hand: Timeline `MATCH (n)`; the writer's `source_type`; the unimported Map panels; no
`/api/reports`; no `/api/graph/cypher`; `/reject-merge` versus `/reject-merge-pair`; no Chroma in the phone
writer; the "use page 1" line; the two quoted documents.
