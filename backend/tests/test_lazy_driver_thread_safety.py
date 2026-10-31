"""Route handlers run in FastAPI's thread pool, so lazily created Neo4j drivers and the vector DB singleton can be
asked for by several threads at once. Each must be built once: a second build leaks a driver (its connection pool)."""

import threading
import time
from types import SimpleNamespace

import pytest

THREADS = 8


def _race(get):
    barrier = threading.Barrier(THREADS, timeout=10)
    results = []

    def run():
        barrier.wait()
        results.append(get())

    threads = [threading.Thread(target=run, daemon=True) for _ in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    return results


class _SlowDriverFactory:
    """Stands in for GraphDatabase: building a driver takes long enough for racing threads to overlap."""

    def __init__(self):
        self.built = []

    def driver(self, *args, **kwargs):
        time.sleep(0.05)
        drv = SimpleNamespace(session=lambda: _NullSession(), close=lambda: None)
        self.built.append(drv)
        return drv


class _NullSession:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, *args, **kwargs):
        return None


@pytest.mark.parametrize(
    "module_name, class_name",
    [
        ("services.triage.triage_service", "TriageService"),
        ("services.triage.classifier_service", "TriageClassifierService"),
        ("services.triage.profiler_service", "TriageProfilerService"),
        ("services.triage.ingest_bridge", "IngestBridge"),
        ("services.triage.processor_registry", "ProcessorRegistry"),
        ("services.triage.scanner_service", "TriageScannerService"),
    ],
)
def test_concurrent_first_calls_build_one_driver(monkeypatch, module_name, class_name):
    import importlib

    module = importlib.import_module(module_name)
    factory = _SlowDriverFactory()
    neo4j_driver = importlib.import_module("services.neo4j.driver")

    # Services build their driver through open_driver (or GraphDatabase directly): both go to the slow factory.
    monkeypatch.setattr(neo4j_driver, "open_driver", lambda *args, **kwargs: factory.driver())
    if hasattr(module, "GraphDatabase"):
        monkeypatch.setattr(module, "GraphDatabase", factory)
    service = getattr(module, class_name)()

    results = _race(service._get_driver)

    assert len(results) == THREADS
    assert len(factory.built) == 1
    assert all(r is factory.built[0] for r in results)


def test_concurrent_first_calls_build_one_vector_db_service(monkeypatch):
    from services import vector_db_service as module

    built = []

    class SlowService:
        def __init__(self):
            time.sleep(0.05)
            built.append(self)

    monkeypatch.setattr(module, "VectorDBService", SlowService)
    monkeypatch.setattr(module, "_vector_db_service", None)

    results = _race(module.get_vector_db_service)

    assert len(built) == 1
    assert all(r is built[0] for r in results)
