"""Shared state reached by route handlers that now run in FastAPI's thread pool (not one at a time on the event
loop): the triage processor registry's first load and the Nominatim one-request-a-second spacing."""
import threading
import time

from services import geo_rescan_service
from services.triage.processor_registry import ProcessorRegistry


def test_concurrent_first_reads_of_the_processor_registry_see_every_processor():
    expected = len(ProcessorRegistry().list_processors())
    assert expected > 0
    registry = ProcessorRegistry()
    original = registry.register

    def slow_register(processor):
        time.sleep(0.05)
        original(processor)
    registry.register = slow_register
    seen = []
    threads = [threading.Thread(target=lambda: seen.append(len(registry.list_processors()))) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert seen == [expected] * 4


def test_concurrent_geocodes_keep_a_second_apart(monkeypatch):
    monkeypatch.setattr(geo_rescan_service, '_last_request_time', 0.0)
    finished = []

    def request():
        geo_rescan_service._rate_limit()
        finished.append(time.time())
    first = threading.Thread(target=request)
    first.start()
    first.join()
    others = [threading.Thread(target=request) for _ in range(2)]
    for thread in others:
        thread.start()
    for thread in others:
        thread.join(10)
    finished.sort()
    assert finished[1] - finished[0] >= 0.95 and finished[2] - finished[1] >= 0.95


def test_the_similar_entities_stream_reads_the_graph_off_the_event_loop(monkeypatch):
    import asyncio
    import importlib
    entity_service = importlib.import_module('services.neo4j.entity_service')
    seen = {}

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def run(self, query, **params):
            seen['thread'] = threading.get_ident()
            return [dict(key='a', id='a', name='Acme Ltd', type='Organization', summary=None, notes=None,
                         verified_facts=None, ai_insights=None, properties={}),
                    dict(key='b', id='b', name='Acme Ltd.', type='Organization', summary=None, notes=None,
                         verified_facts=None, ai_insights=None, properties={})]

    monkeypatch.setattr(entity_service, 'driver', type('Driver', (), dict(session=lambda self: Session()))())

    async def collect():
        seen['loop'] = threading.get_ident()
        return [event async for event in entity_service.EntityService().find_similar_entities_streaming('case-1')]
    events = asyncio.run(collect())
    assert events[0] == {'event': 'start', 'data': {'total_entities': 2, 'entity_types': ['Organization'],
                                                    'total_types': 1, 'total_comparisons': 1}}
    assert seen['thread'] != seen['loop']
