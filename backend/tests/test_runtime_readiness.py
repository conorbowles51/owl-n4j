import unittest
from unittest.mock import MagicMock
from services.runtime_readiness import database_readiness, overall_readiness, expected_database_heads


class RuntimeReadinessTests(unittest.TestCase):
    def engine(self, revisions):
        engine = MagicMock()
        connection = engine.connect.return_value.__enter__.return_value
        connection.execute.return_value.scalars.return_value = revisions
        return engine, connection

    def test_current_schema_is_ready_and_queries_are_read_only_bounded(self):
        engine, connection = self.engine(['head'])
        result = database_readiness(engine=engine, expected_heads=['head'])
        self.assertEqual(result, {'status':'connected','schema':'current'})
        commands=[str(call.args[0]) for call in connection.execute.call_args_list]
        self.assertEqual(commands[:2], ['SET TRANSACTION READ ONLY', "SET LOCAL statement_timeout = '2000ms'"])
        self.assertEqual(overall_readiness('connected','ok',result),'ok')

    def test_behind_ahead_and_missing_revisions_never_report_ready(self):
        for revisions in ([], ['old'], ['head','unexpected']):
            engine,_ = self.engine(revisions)
            result = database_readiness(engine=engine,expected_heads=['head'])
            self.assertEqual(result['schema'],'outdated')
            self.assertEqual(overall_readiness('connected','ok',result),'degraded')

    def test_connection_failure_does_not_disclose_connection_details(self):
        engine=MagicMock();engine.connect.side_effect=RuntimeError('private-password@private-host')
        result=database_readiness(engine=engine,expected_heads=['head'])
        self.assertEqual(result, {'status':'unavailable','schema':'unknown'})
        self.assertNotIn('private',str(result))

    def test_other_unhealthy_dependencies_remain_degraded(self):
        db={'status':'connected','schema':'current'}
        self.assertEqual(overall_readiness('error: unavailable','ok',db),'degraded')
        self.assertEqual(overall_readiness('connected','unavailable',db),'degraded')

    def test_repository_has_one_migration_head(self):
        self.assertEqual(len(expected_database_heads()),1)


class HealthEndpointReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_database_outage_degrades_the_public_health_response(self):
        from unittest.mock import AsyncMock, patch
        import main
        graph=MagicMock();graph.session.return_value.__enter__.return_value.run.return_value.single.return_value={'total_nodes':0}
        with patch.object(main,'driver',graph), patch.object(main.evidence_engine_client,'health_check',AsyncMock(return_value={'status':'ok'})), patch('services.runtime_readiness.database_readiness',return_value={'status':'unavailable','schema':'unknown'}):
            response=await main.health()
        self.assertEqual(response['status'],'degraded')
        self.assertEqual(response['postgres'],'unavailable')
        self.assertEqual(response['database_schema'],'unknown')

    async def test_driver_errors_do_not_escape_into_the_public_health_response(self):
        from unittest.mock import AsyncMock, patch
        import main
        graph=MagicMock();graph.session.side_effect=RuntimeError('private graph credentials')
        with patch.object(main,'driver',graph), patch.object(main.evidence_engine_client,'health_check',AsyncMock(side_effect=RuntimeError('private engine credentials'))), patch('services.runtime_readiness.database_readiness',return_value={'status':'connected','schema':'current'}):
            response=await main.health()
        self.assertEqual(response['status'],'degraded')
        self.assertNotIn('private',str(response))
