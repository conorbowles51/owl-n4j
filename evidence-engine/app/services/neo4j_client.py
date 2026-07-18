from typing import Any

from neo4j import AsyncGraphDatabase, AsyncDriver

from app.config import settings

_driver: AsyncDriver | None = None


def get_neo4j_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
    return _driver


async def close_neo4j() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


async def execute_query(
    query: str, parameters: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    driver = get_neo4j_driver()
    async with driver.session() as session:
        result = await session.run(query, parameters or {})
        return [record.data() async for record in result]


async def execute_write(
    query: str, parameters: dict[str, Any] | None = None
) -> None:
    driver = get_neo4j_driver()
    async with driver.session() as session:
        await session.run(query, parameters or {})


async def get_case_geocoded_locations(case_id: str) -> list[dict[str, Any]]:
    query = """
    MATCH (n:Location {case_id: $case_id})
    WHERE n.latitude IS NOT NULL
      AND n.longitude IS NOT NULL
      AND NOT 'Document' IN labels(n)
      AND NOT 'System' IN labels(n)
      AND coalesce(n.source_type, '') <> 'document'
    RETURN
      n.id AS id,
      n.key AS key,
      n.name AS name,
      'Location' AS type,
      n.latitude AS latitude,
      n.longitude AS longitude,
      n.location_raw AS location_raw,
      n.location_formatted AS location_formatted,
      n.geocoding_granularity AS geocoding_granularity,
      n.geocoding_precision AS geocoding_precision,
      n.manual_fields AS manual_fields,
      n.source_files AS source_files,
      n.job_id AS job_id
    """
    return await execute_query(query, {"case_id": case_id})


async def check_connection() -> bool:
    try:
        driver = get_neo4j_driver()
        async with driver.session() as session:
            await session.run("RETURN 1")
        return True
    except Exception:
        return False
