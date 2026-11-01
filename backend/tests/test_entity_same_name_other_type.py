"""The similar-entities scan suggests the same name extracted as two types, which the type-by-type pass never pairs.

People merged groups such as a Bank and an Organization both named 'Wells Fargo' by hand: the scan compared names
only within one type. A Neo4j read is faked; the comparison is the real code."""
import asyncio
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import importlib

from services.neo4j.entity_service import EntityService, same_name_other_type_pairs

# The package exports an EntityService instance under the module's name; patch the module itself.
entity_service = importlib.import_module('services.neo4j.entity_service')


def _entity(key, name, type_):
    return dict(key=key, id=key, name=name, type=type_, summary=None, notes=None, verified_facts=None,
                ai_insights=None, properties={})


ENTITIES = [
    _entity('k1', 'Wells Fargo', 'Bank'),
    _entity('k2', 'WELLS FARGO', 'Organization'),
    _entity('k3', 'Wells-Fargo', 'Bank'),
    _entity('k4', 'Hezbollah', 'Group'),
    _entity('k5', 'Hezbollah', 'Organization'),
    _entity('k6', 'Henrico', 'Location'),
    _entity('k7', 'Jose', 'Person'),
    _entity('k8', 'José', 'Location'),
]


@contextmanager
def _graph(entities):
    session = MagicMock()
    session.run.return_value = [dict(e) for e in entities]
    driver = MagicMock()
    driver.session.return_value.__enter__.return_value = session
    with patch.object(entity_service, 'driver', driver):
        yield


def _keys(pairs):
    return sorted(tuple(sorted((p['entity1']['key'], p['entity2']['key']))) for p in pairs)


def test_same_name_of_different_types_is_paired_and_same_type_is_left_to_the_type_pass():
    pairs = same_name_other_type_pairs(ENTITIES)
    assert sorted(tuple(sorted((a['key'], b['key']))) for a, b, _ in pairs) == [
        ('k1', 'k2'), ('k2', 'k3'), ('k4', 'k5'), ('k7', 'k8')]
    assert all(0 < similarity <= 1 for _, _, similarity in pairs)


def test_rejected_pairs_stay_rejected():
    pairs = same_name_other_type_pairs(ENTITIES, {('k1', 'k2'), ('k4', 'k5')})
    assert sorted(tuple(sorted((a['key'], b['key']))) for a, b, _ in pairs) == [('k2', 'k3'), ('k7', 'k8')]


def test_the_scan_and_the_streaming_scan_suggest_them():
    with _graph(ENTITIES):
        plain = EntityService().find_similar_entities('case', name_similarity_threshold=0.88, max_results=100)

        async def stream():
            events = [e async for e in EntityService().find_similar_entities_streaming(
                'case', name_similarity_threshold=0.88, rejected_pairs={('k7', 'k8')})]
            return events[-1]['data']['limited_results']
        streamed = asyncio.run(stream())
    for pairs in (plain, streamed):
        keys = _keys(pairs)
        assert ('k1', 'k2') in keys and ('k4', 'k5') in keys and ('k2', 'k3') in keys
        cross = [p for p in pairs if p['entity1']['type'] != p['entity2']['type']]
        assert {p['entity1']['name'].lower().replace('-', ' ') for p in cross} >= {'wells fargo', 'hezbollah'}
    assert ('k7', 'k8') in _keys(plain) and ('k7', 'k8') not in _keys(streamed)
