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


async def check_connection() -> bool:
    try:
        driver = get_neo4j_driver()
        async with driver.session() as session:
            await session.run("RETURN 1")
        return True
    except Exception:
        return False
