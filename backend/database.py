from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.utils.config import Config


class Base(DeclarativeBase):
    pass


_engine = None
_async_session_maker = None


def get_db_url() -> str:
    pg = Config.get("database.postgresql", {})
    return f"postgresql+asyncpg://{pg['user']}:{pg['password']}@{pg['host']}:{pg['port']}/{pg['database']}"


async def init_db():
    global _engine, _async_session_maker
    db_url = get_db_url()
    _engine = create_async_engine(db_url, pool_size=Config.get("database.postgresql.pool_size", 10))
    _async_session_maker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with _engine.begin() as conn:
        import backend.models.log  # noqa: F401 — ensure app_logs table is created
        import backend.models.user  # noqa: F401 — ensure User tables are created
        from backend.models.company import Base as ModelsBase

        await conn.run_sync(ModelsBase.metadata.create_all)


async def get_session() -> AsyncSession:
    if _async_session_maker is None:
        await init_db()
    async with _async_session_maker() as session:
        yield session


def get_session_maker():
    return _async_session_maker


async def close_db():
    global _engine
    if _engine:
        await _engine.dispose()
