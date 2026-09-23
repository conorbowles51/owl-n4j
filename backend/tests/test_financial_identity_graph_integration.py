"""Opt-in local Neo4j: shared identity projection is idempotent and retractable."""
import os
from uuid import UUID
import pytest
from neo4j import GraphDatabase
from services.financial.account_parties import AccountPartyRequest, account_parties, set_account_party
from services.financial.identity_graph import apply_identity_graph, identity_graph_plan
from tests.test_financial_duplicates import DuplicateTestCase


@pytest.mark.skipif(os.getenv('LOUPE_TEST_LOCAL_GRAPH') != '1', reason='Requires isolated local graph')
class IdentityGraphTests(DuplicateTestCase):
    def test_retry_preserves_graph_notes_and_unlink_retracts_only_reviewed_relationship(self):
        uri = os.environ['NEO4J_URI']
        assert uri == 'bolt://127.0.0.1:57687'
        driver = GraphDatabase.driver(uri, auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASSWORD']))
        case = str(self.case.id)
        try:
            directory = account_parties(self.db, case_id=self.case.id)
            linked = set_account_party(self.db, case_id=self.case.id, request=AccountPartyRequest(
                expected_revision=directory['revision'], account_ids=[self.account.id], new_party_name='Synthetic business',
                relationship={'role':'holder'}, reason='Synthetic ownership source reviewed'), actor=self.actor)
            plan = identity_graph_plan(self.db, self.case.id)
            with driver.session() as graph:
                self.assertTrue(apply_identity_graph(graph, plan))
                self.assertFalse(apply_identity_graph(graph, plan))
                self.assertEqual(graph.run('MATCH (n {case_id:$case}) WHERE n.key IS NOT NULL RETURN count(n) AS n', case=case).single()['n'], len(plan['accounts'])+1)
                account = plan['accounts'][0]['key']
                graph.run("MATCH (n {case_id:$case,key:$key}) SET n.notes='Investigator retained note', n.name='Investigator name'", case=case, key=account).consume()
                party = plan['parties'][0]['key']
                graph.run('MATCH (p {case_id:$case,key:$p}), (a {case_id:$case,key:$a}) CREATE (p)-[:MANUAL_CONNECTION {case_id:$case}]->(a)', case=case, p=party, a=account).consume()
                link = linked['accounts'][0]['relationships'][0]
                set_account_party(self.db, case_id=self.case.id, request=AccountPartyRequest(expected_revision=linked['revision'], account_ids=[self.account.id], clear=True, relationship={'id':link['id']}, reason='Reviewed removal'), actor=self.actor)
                self.assertTrue(apply_identity_graph(graph, identity_graph_plan(self.db, self.case.id)))
                self.assertEqual(graph.run('MATCH ({case_id:$case})-[r:HOLDS_ACCOUNT]->() RETURN count(r) AS n', case=case).single()['n'], 0)
                self.assertEqual(graph.run('MATCH ({case_id:$case})-[r:MANUAL_CONNECTION]->() RETURN count(r) AS n', case=case).single()['n'], 1)
                row = graph.run('MATCH (n {case_id:$case,key:$key}) RETURN n.name AS name,n.notes AS notes', case=case,key=account).single()
                self.assertEqual(dict(row), {'name':'Investigator name','notes':'Investigator retained note'})
                # An ordinary case entity must never be duplicated into a new
                # financial node merely because its key collides.
                graph.run('MATCH (n {case_id:$case,key:$key}) REMOVE n:FinancialAccount SET n:Person', case=case, key=account).consume()
                with self.assertRaisesRegex(ValueError, 'conflicts'):
                    apply_identity_graph(graph, identity_graph_plan(self.db, self.case.id))

        finally:
            with driver.session() as graph:
                graph.run('MATCH (n {case_id:$case}) DETACH DELETE n', case=case).consume()
            driver.close()
