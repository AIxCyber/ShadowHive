from neo4j import AsyncDriver, AsyncGraphDatabase

from backend.utils.config import Config

_driver: AsyncDriver | None = None


async def init_neo4j():
    global _driver
    neo = Config.get("database.neo4j", {})
    _driver = AsyncGraphDatabase.driver(
        neo.get("uri", "bolt://localhost:7687"),
        auth=(neo.get("user", "neo4j"), neo.get("password", "")),
    )
    async with _driver.session() as session:
        await session.run("MATCH (n) RETURN count(n) AS count")


async def get_neo4j_session():
    if _driver is None:
        await init_neo4j()
    async with _driver.session() as session:
        yield session


async def close_neo4j():
    global _driver
    if _driver:
        await _driver.close()
        _driver = None
