"""Real isolated Neo4j: lost acknowledgements, parallel writers and manual edits.

Opt in only for the synthetic local service; never accepts a live database URI.
"""
import asyncio
import os
from uuid import uuid4
import pytest
from app.pipeline import write_graph
from app.pipeline.resolve_entities import ResolvedEntity
from app.services import neo4j_client, ingestion_checkpoints as checkpoints
from app.services.graph_identity import ensure_identity_indexes

pytestmark = pytest.mark.skipif(os.getenv('LOUPE_TEST_LOCAL_GRAPH') != '1',reason='Requires the isolated local Neo4j on port 57687')

@pytest.mark.asyncio
async def test_restart_after_partial_publication_and_lost_ack_retains_manual_edits(tmp_path,monkeypatch):
    assert neo4j_client.settings.neo4j_uri == 'bolt://127.0.0.1:57687'
    monkeypatch.setattr(checkpoints.settings,'storage_path',str(tmp_path))
    async def no_pause():return False
    async def no_geocode(_):pass
    monkeypatch.setattr(write_graph,'_apply_geocoding',no_geocode)
    case=str(uuid4());scope=str(uuid4())
    entities=[ResolvedEntity(id=f'synthetic-{i}',category='Event',specific_type='Incident',name=f'Example event {i}',
        properties={'description':'Extracted description','date':'2025-01-01'},summary='Example summary') for i in range(201)]
    await ensure_identity_indexes()
    actual=neo4j_client.execute_write
    calls=0
    async def interrupted(query,params):
        nonlocal calls
        calls+=1
        await actual(query,params)
        if calls==2:raise TimeoutError('Lost acknowledgement after the second committed chunk')
    monkeypatch.setattr(neo4j_client,'execute_write',interrupted)
    try:
        with pytest.raises(TimeoutError):
            async with checkpoints.checkpoint_scope(scope,case,no_pause):
                await write_graph._write_entities(entities,case,scope)
        monkeypatch.setattr(neo4j_client,'execute_write',actual)
        await actual("MATCH (n:Event {case_id:$case,id:'synthetic-150'}) SET n.name='Investigator name', n.description='', n.manual_fields=['name','description']",{'case':case})
        # Close the connection to exercise a fresh database session after restart.
        await neo4j_client.close_neo4j()
        async with checkpoints.checkpoint_scope(scope,case,no_pause):
            await write_graph._write_entities(entities,case,scope)
        result=await neo4j_client.execute_query('MATCH (n:Event {case_id:$case}) RETURN count(n) AS total,count(DISTINCT n.id) AS ids',{'case':case})
        assert result==[{'total':201,'ids':201}]
        manual=await neo4j_client.execute_query("MATCH (n:Event {case_id:$case,id:'synthetic-150'}) RETURN n.name AS name,n.description AS description",{'case':case})
        assert manual==[{'name':'Investigator name','description':''}]
        # Different runs race on the same new identity: one node, both finishes.
        fresh=[ResolvedEntity(id='concurrent',category='Event',specific_type='Incident',name='Shared example',properties={},summary='')]
        await asyncio.gather(*(write_graph._write_entities(fresh,case,str(uuid4())) for _ in range(4)))
        rows=await neo4j_client.execute_query("MATCH (n:Event {case_id:$case,id:'concurrent'}) RETURN count(n) AS total",{'case':case})
        assert rows==[{'total':1}]
    finally:
        await actual('MATCH (n {case_id:$case}) DETACH DELETE n',{'case':case})
        await neo4j_client.close_neo4j()
