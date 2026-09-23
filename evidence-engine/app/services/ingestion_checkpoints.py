"""Durable work units on the engine's shared evidence volume.

Only explicitly opted-in ingestion workers use this store. JSON, never pickle;
an atomic rename makes a unit visible only after its result is complete.
"""
import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import fields, is_dataclass
import fcntl
from functools import wraps
import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
import tempfile
from uuid import UUID

from app.config import settings

VERSION = "interruption-v1"
_current = ContextVar("ingestion_checkpoints", default=None)
_ALLOWED = {
    "app.pipeline.extract_text.ExtractedDocument",
    "app.pipeline.chunk_embed.TextChunk",
    "app.pipeline.chunk_embed.StagedChunkRevision",
    "app.pipeline.extract_entities.RawEntity",
    "app.pipeline.extract_entities.RawRelationship",
    "app.pipeline.resolve_entities.ResolvedEntity",
    "app.pipeline.resolve_entities.ResolvedRelationship",
    "app.pipeline.verify_claims.ClaimVerificationResult",
    "app.services.openai_client.AudioTranscriptionResult",
}


class IngestionPaused(BaseException):
    """Control flow, not an extraction failure."""


def encode(value):
    if is_dataclass(value):
        name = type(value).__module__ + "." + type(value).__name__
        if name not in _ALLOWED:
            raise TypeError(f"Unsupported checkpoint type: {name}")
        return ["object", name, encode({f.name: getattr(value, f.name) for f in fields(value)})]
    if isinstance(value, dict):
        return ["dict", [[k, encode(v)] for k, v in sorted(value.items())]]
    if isinstance(value, (tuple, list)):
        return ["tuple" if isinstance(value, tuple) else "list", [encode(v) for v in value]]
    if isinstance(value, UUID):
        return ["uuid", str(value)]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(f"Unsupported checkpoint value: {type(value).__name__}")


def decode(value):
    if not isinstance(value, list):
        return value
    kind = value[0]
    if kind == "object":
        name = value[1]
        if name not in _ALLOWED:
            raise ValueError("Unrecognised checkpoint type")
        module, cls = name.rsplit(".", 1)
        return getattr(importlib.import_module(module), cls)(**decode(value[2]))
    if kind == "dict":
        return {k: decode(v) for k, v in value[1]}
    if kind == "uuid":
        return UUID(value[1])
    if kind in ("tuple", "list"):
        result = [decode(v) for v in value[1]]
        return tuple(result) if kind == "tuple" else result
    raise ValueError("Invalid checkpoint")


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".writing-")
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(value, output, ensure_ascii=False, allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        # Persist the rename as well as the file contents across host failure.
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Checkpoints:
    def __init__(self, root, pause_check):
        self.root = Path(root)
        self.pause_check = pause_check

    async def guard(self):
        if await self.pause_check():
            raise IngestionPaused()

    async def call(self, name, operation, args, kwargs, *, key_inputs=None):
        await self.guard()
        # Callbacks are controls, not source inputs. Their results aren't cached.
        inputs = key_inputs if key_inputs is not None else (args, {k: v for k, v in kwargs.items() if not callable(v)})
        digest = hashlib.sha256(json.dumps(encode((VERSION, name, inputs)), sort_keys=True).encode()).hexdigest()
        target = self.root / (digest + ".json")
        if target.exists():
            # Corrupt checkpoints must fail visibly, not silently redo paid work.
            payload = await asyncio.to_thread(target.read_text)
            return decode(json.loads(payload))
        result = await operation(*args, **kwargs)
        await asyncio.to_thread(atomic_json, target, encode(result))
        await self.guard()
        return result


def checkpointed(name, *, ignore=()):
    def decorate(operation):
        signature = inspect.signature(operation)
        @wraps(operation)
        async def run(*args, **kwargs):
            store = _current.get()
            if store is None:
                return await operation(*args, **kwargs)
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            inputs = {k: v for k, v in bound.arguments.items() if k not in ignore and not callable(v)}
            if not name.startswith('pipeline/extract_text.py:'):
                # Outer extraction/resolution stages must not return a cache
                # from an earlier model policy before the inner model call can
                # notice the changed policy. Never include credential secrets.
                from app.services.ai_model_policy import get_ai_runtime_snapshot
                inputs['runtime'] = get_ai_runtime_snapshot()
            return await store.call(name, operation, args, kwargs, key_inputs=inputs)
        return run
    return decorate


async def pause_boundary():
    store = _current.get()
    if store:
        await store.guard()


def current_checkpoint_root():
    """Synchronous worker adapters inherit this context through to_thread."""
    store = _current.get()
    return store.root if store else None


def page_checkpoint_root(file_path):
    store = _current.get()
    if not store:
        return None
    # The uploaded source is immutable within a run. Include its content hash
    # anyway so a replaced local source can never borrow another PDF's OCR.
    with open(file_path, 'rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    return str(store.root / 'pages' / digest)


@asynccontextmanager
async def checkpoint_scope(scope_id, case_id, pause_check):
    root = Path(settings.storage_path) / "_checkpoints" / str(UUID(case_id)) / str(UUID(scope_id)) / VERSION
    root.mkdir(parents=True, exist_ok=True)
    # All current workers share this volume. A process crash releases flock.
    # A second resume must wait instead of publishing concurrently.
    with (root / "run.lock").open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            from arq import Retry
            raise Retry(defer=5)
        token = _current.set(Checkpoints(root, pause_check))
        try:
            await pause_boundary()
            yield
        finally:
            _current.reset(token)
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
