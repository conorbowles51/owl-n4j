from typing import Any

import chromadb
from chromadb.api import ClientAPI

from app.config import settings

_client: ClientAPI | None = None


def get_chroma_client() -> ClientAPI:
    global _client
    if _client is None:
        _client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
    return _client


def get_or_create_collection(name: str) -> chromadb.Collection:
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def delete_collection(name: str) -> None:
    client = get_chroma_client()
    try:
        client.delete_collection(name=name)
    except ValueError:
        pass


def add_embeddings(
    collection: chromadb.Collection,
    ids: list[str],
    embeddings: list[list[float]],
    documents: list[str],
    metadatas: list[dict[str, Any]],
) -> None:
    batch_size = 500
    for i in range(0, len(ids), batch_size):
        end = i + batch_size
        collection.add(
            ids=ids[i:end],
            embeddings=embeddings[i:end],
            documents=documents[i:end],
            metadatas=metadatas[i:end],
        )


def query_similar(
    collection: chromadb.Collection,
    query_embeddings: list[list[float]],
    n_results: int = 5,
    where: dict[str, Any] | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "query_embeddings": query_embeddings,
        "n_results": n_results,
    }
    if where:
        kwargs["where"] = where
    return collection.query(**kwargs)


def check_connection() -> bool:
    try:
        client = get_chroma_client()
        client.heartbeat()
        return True
    except Exception:
        return False
