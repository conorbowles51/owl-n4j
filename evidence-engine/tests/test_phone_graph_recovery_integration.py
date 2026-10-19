"""Real local Neo4j only: retry after committed phone-record acknowledgement loss."""
import os
from uuid import uuid4

import pytest

from app.pipeline.cellebrite import ingestion, neo4j_client
from app.pipeline.cellebrite.models import ParsedModel
from app.pipeline.cellebrite.recovery import Recovery
from app.services import ingestion_checkpoints as checkpoints
from tests.test_phone_report_recovery import Parser, never_pause

pytestmark = pytest.mark.skipif(os.getenv('LOUPE_TEST_LOCAL_GRAPH') != '1', reason='Requires isolated local Neo4j on 57687')


@pytest.mark.asyncio
async def test_committed_partial_phone_graph_replays_without_duplicates_or_lost_edits(tmp_path, monkeypatch):
    assert neo4j_client.NEO4J_URI == 'bolt://127.0.0.1:57687'
    monkeypatch.setattr(checkpoints.settings, 'storage_path', str(tmp_path / 'saved'))
    report = tmp_path / 'Phone'; report.mkdir()
    xml = report / 'report.xml'; xml.write_text('<report xmlns="http://pa.cellebrite.com/report/2.0"/>')
    class SmallParser(Parser):
        xml_counts_by_type = {'VisitedPage': 40}
        def stream_models(self, **kwargs):
            yield [ParsedModel(model_type='VisitedPage', model_id=f'{i:012d}', fields={'Url': f'https://example.test/{i}'}) for i in range(40)]
    monkeypatch.setattr(ingestion, 'CellebriteXMLParser', SmallParser)
    real_class = neo4j_client.Neo4jClient
    lost = True
    class InterruptedClient(real_class):
        def run_query(self, query, **params):
            nonlocal lost
            result = super().run_query(query, **params)
            if 'MERGE (n:' in query and params.get('key') == 'page-000000000012' and lost:
                lost = False
                raise TimeoutError('Synthetic acknowledgement lost after commit')
            return result
    monkeypatch.setattr(neo4j_client, 'Neo4jClient', InterruptedClient)
    case, scope = str(uuid4()), str(uuid4())
    with real_class() as inspect:
        try:
            with pytest.raises(RuntimeError, match='completed work is retained'):
                async with checkpoints.checkpoint_scope(scope, case, never_pause):
                    recovery = Recovery(xml, lambda: None); recovery.save(phase='cleanup_complete')
                    ingestion.ingest_cellebrite_report(report, case, recovery=recovery)
            rows = inspect.run_query("MATCH (n {case_id:$case}) WHERE n.key STARTS WITH 'page-' RETURN count(n) AS total", case=case)
            assert rows == [{'total': 13}]
            before = inspect.run_query("MATCH (n {case_id:$case,key:'page-000000000012'}) SET n.name='Investigator correction' RETURN n.id AS id", case=case)
            async with checkpoints.checkpoint_scope(scope, case, never_pause):
                result = ingestion.ingest_cellebrite_report(report, case, recovery=Recovery(xml, lambda: None))
            assert result['status'] == 'success' and result['visited_pages_created'] == 40
            rows = inspect.run_query("MATCH (n {case_id:$case}) WHERE n.key STARTS WITH 'page-' RETURN count(n) AS total, count(DISTINCT n.id) AS ids", case=case)
            assert rows == [{'total': 40, 'ids': 40}]
            corrected = inspect.run_query("MATCH (n {case_id:$case,key:'page-000000000012'}) RETURN n.id AS id,n.name AS name", case=case)
            assert corrected == [{**before[0], 'name': 'Investigator correction'}]
        finally:
            inspect.run_query('MATCH (n {case_id:$case}) DETACH DELETE n', case=case)
