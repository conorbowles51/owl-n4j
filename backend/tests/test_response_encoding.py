"""Route results are encoded in a worker thread (services.response_encoding): the same bytes as FastAPI's own
encoding for every kind of result, and none of the encoding on the event-loop thread."""

from __future__ import annotations

import dataclasses
import datetime
import decimal
import enum
import inspect
import threading
import uuid
from pathlib import Path

import fastapi.encoders
import fastapi.routing as routing
import pytest
from fastapi import BackgroundTasks, FastAPI, Response
from fastapi.testclient import TestClient
from pydantic import BaseModel

from services import response_encoding


class Colour(enum.Enum):
    red = "red"


class Item(BaseModel):
    id: uuid.UUID
    name: str
    amount: decimal.Decimal
    when: datetime.datetime
    note: str | None = None


@dataclasses.dataclass
class Row:
    label: str
    value: float


ITEM = Item(id=uuid.UUID(int=7), name="Café ✓", amount=decimal.Decimal("12.50"),
            when=datetime.datetime(2026, 10, 31, 6, 0, tzinfo=datetime.timezone.utc))


def _app():
    app = FastAPI()

    @app.get("/plain")
    def plain():
        return {"b": [1, 2.5, None, True, "é ✓"], "a": {"n": 10**20}, 3: "int key", "_sa_instance_state": "dropped"}

    @app.get("/types")
    async def types():
        return {"id": uuid.UUID(int=1), "when": datetime.date(2026, 10, 31), "money": decimal.Decimal("1.10"),
                "colour": Colour.red, "path": Path("/x/y"), "set": {"only"}, "row": Row("r", 0.1), "item": ITEM,
                "tuple": (1, "two"), "bytes": b"raw"}

    @app.get("/model", response_model=Item)
    def model():
        return ITEM

    @app.get("/model-dict", response_model=Item, response_model_exclude_none=True)
    async def model_dict():
        return {"id": str(uuid.UUID(int=2)), "name": "n", "amount": "3", "when": "2026-10-31T00:00:00Z"}

    @app.get("/models", response_model=list[Item], response_model_include={"id", "name"})
    def models():
        return [ITEM, ITEM]

    @app.get("/bad", response_model=Item)
    def bad():
        return {"id": "not a uuid"}

    @app.get("/none", status_code=202)
    def none(response: Response, background: BackgroundTasks):
        response.headers["X-Kept"] = "yes"
        background.add_task(lambda: None)
        return None

    @app.get("/big")
    def big():
        return [{"i": i, "s": "x" * 20, "f": i / 7} for i in range(20000)]

    return app


PATHS = ["/plain", "/types", "/model", "/model-dict", "/models", "/none", "/big"]


@pytest.fixture(autouse=True)
def _restore():
    # Importing main installs the wrapper for the whole test process; leave it as it was found.
    installed = routing.serialize_response
    yield
    routing.serialize_response = installed


def _answers(install):
    routing.serialize_response = response_encoding.serialize_response if install else response_encoding._original
    try:
        client = TestClient(_app(), raise_server_exceptions=False)
        return {path: (r.status_code, r.headers.get("content-type"), r.headers.get("x-kept"), r.content)
                for path in PATHS + ["/bad"] for r in [client.get(path)]}
    finally:
        routing.serialize_response = response_encoding._original


def test_every_kind_of_result_is_encoded_to_the_same_bytes():
    before, after = _answers(False), _answers(True)
    for path in PATHS + ["/bad"]:
        assert after[path] == before[path], path
    assert before["/bad"][0] == 500 and before["/none"][0] == 202


def test_the_encoding_runs_off_the_event_loop_thread(monkeypatch):
    original_encoder = fastapi.encoders.jsonable_encoder
    threads = []

    def recording(*args, **kwargs):
        threads.append(threading.current_thread().name)
        return original_encoder(*args, **kwargs)

    monkeypatch.setattr(routing, "jsonable_encoder", recording)
    routing.serialize_response = response_encoding.serialize_response
    try:
        with TestClient(_app()) as client:
            loop_thread = client.portal.call(lambda: threading.current_thread().name)
            assert client.get("/big").status_code == 200
            assert client.get("/model").status_code == 200
    finally:
        routing.serialize_response = response_encoding._original
    assert threads and loop_thread not in threads


def test_main_installs_it_and_the_switch_turns_it_off(monkeypatch):
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text()
    assert "_encode_off_the_loop()" in source.split("app = FastAPI(", 1)[0]
    routing.serialize_response = response_encoding._original
    monkeypatch.setenv("LOUPE_SERIALIZE_OFF_LOOP", "0")
    assert response_encoding.install() is False and routing.serialize_response is response_encoding._original
    monkeypatch.delenv("LOUPE_SERIALIZE_OFF_LOOP")
    assert response_encoding.install() is True and routing.serialize_response is response_encoding.serialize_response


def test_fastapi_still_has_the_function_it_wraps():
    # A FastAPI upgrade that renames or reshapes serialize_response must be looked at, not silently bypassed.
    parameters = inspect.signature(response_encoding._original).parameters
    assert {"field", "response_content", "is_coroutine"} <= set(parameters)
    assert all(p.kind is not inspect.Parameter.POSITIONAL_ONLY for p in parameters.values())


def test_each_event_loop_gets_its_own_limiter():
    # Two clients run two event loops in one process; each encodes through a limiter of its own.
    routing.serialize_response = response_encoding.serialize_response
    for _ in range(2):
        with TestClient(_app()) as client:
            assert client.get("/big").status_code == 200
    limiters = list(response_encoding._limiters.values())
    assert len({id(limiter) for limiter in limiters}) == len(limiters)
    assert all(limiter.total_tokens == response_encoding.ENCODE_SLOTS for limiter in limiters)
