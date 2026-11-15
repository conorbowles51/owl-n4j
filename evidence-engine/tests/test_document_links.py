"""Graph writes link each entity to the Document node of every file it was read from (lx-retrieval C).

Before, no code wrote (entity)-[:MENTIONED_IN]->(Document) on purpose, so the backend's Significant scope and
selected-document reads found few documents (13 links over 40 documents in the demo case). These tests fail on that
code: the module does not exist and the graph write makes no link.
"""
import json

import pytest

from app.pipeline import write_graph as write_graph_module
from app.pipeline.document_links import ENSURE_DOCUMENTS, LINK_ORIGIN, WRITE_LINKS, plan
from app.pipeline.resolve_entities import ResolvedEntity

LOC = {"source_document_id": "b484f0f3-d0b6-4049-b9d6-103e18940520", "revision_id": "r", "chunk_index": 0,
       "source_file": "kell-proffer-transcript-2024-06-20.docx", "quote": "Mateo's garage"}


def test_plan_names_every_file_with_its_document_key_and_evidence_id():
    files, links = plan([
        {"id": "e1", "source_files": ["bay4-lease-2023-10-01.pdf"], "source_locations": json.dumps([LOC])},
        {"id": "e2", "source_files": ["bay4-lease-2023-10-01.pdf", "  "], "source_locations": None},
        {"id": "e3", "source_files": [], "source_locations": []},
    ])
    by_name = {f["name"]: f for f in files}
    assert by_name["kell-proffer-transcript-2024-06-20.docx"] == {
        "name": "kell-proffer-transcript-2024-06-20.docx", "key": "kell-proffer-transcript-2024-06-20docx",
        "evidence_file_id": LOC["source_document_id"]}
    # the chunk doc_key of the same file (chunk_embed.normalize_document_key)
    assert by_name["bay4-lease-2023-10-01.pdf"]["key"] == "bay4-lease-2023-10-01pdf"
    assert links == [
        {"entity_id": "e1", "files": ["bay4-lease-2023-10-01.pdf", "kell-proffer-transcript-2024-06-20.docx"]},
        {"entity_id": "e2", "files": ["bay4-lease-2023-10-01.pdf"]},
    ]


def test_an_existing_document_node_of_the_file_is_reused_and_links_are_marked_as_provenance():
    assert "WHERE d.name = f.name" in ENSURE_DOCUMENTS and "WHERE existing = 0" in ENSURE_DOCUMENTS
    assert "MERGE (e)-[m:MENTIONED_IN]->(d)" in WRITE_LINKS and "NOT e:Document" in WRITE_LINKS
    assert LINK_ORIGIN == "source_files"


@pytest.mark.asyncio
async def test_the_graph_write_links_entities_to_their_documents(monkeypatch):
    writes = []

    async def nothing(*args, **kwargs):
        return None

    async def record(query, parameters):
        writes.append((query, parameters))

    monkeypatch.setattr(write_graph_module, "_ensure_indexes", nothing)
    monkeypatch.setattr(write_graph_module, "_write_entities", nothing)
    monkeypatch.setattr(write_graph_module, "_write_relationships", nothing)
    monkeypatch.setattr(write_graph_module, "_embed_entities", nothing)
    monkeypatch.setattr(write_graph_module, "_checkpointed_graph_write", record)

    await write_graph_module.write_graph(
        [ResolvedEntity(id="p1", category="Person", specific_type="", name="Mateo",
                        source_files=[LOC["source_file"]], source_locations=[LOC]),
         ResolvedEntity(id="d1", category="Document", specific_type="", name="Proffer",
                        source_files=[LOC["source_file"]])],
        [], "case-1", "job-1")

    link_writes = [p for q, p in writes if q == WRITE_LINKS]
    assert link_writes == [{"links": [{"entity_id": "p1", "files": [LOC["source_file"]]}], "case_id": "case-1",
                            "origin": LINK_ORIGIN}]
    file_writes = [p for q, p in writes if q == ENSURE_DOCUMENTS]
    assert file_writes[0]["files"][0]["evidence_file_id"] == LOC["source_document_id"]
