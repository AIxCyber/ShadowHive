from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Import models so they register on ModelsBase.metadata
import backend.database  # noqa: F401 — patched below
import backend.models.company  # noqa: F401
import backend.models.log  # noqa: F401
import backend.models.user  # noqa: F401
from backend.main import app
from backend.models.company import Base as ModelsBase
from backend.utils.config import Config

TEST_DB_URL = "sqlite+aiosqlite:///file::memory:?cache=shared"


@pytest_asyncio.fixture
async def engine():
    _engine = create_async_engine(
        TEST_DB_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )
    # Drop and recreate all tables to ensure clean state
    async with _engine.begin() as conn:
        await conn.run_sync(ModelsBase.metadata.drop_all)
        await conn.run_sync(ModelsBase.metadata.create_all)
    # Patch database module so endpoints that call get_session() directly
    # use the test engine instead of connecting to PostgreSQL.
    backend.database._engine = _engine
    backend.database._async_session_maker = async_sessionmaker(
        _engine, class_=AsyncSession, expire_on_commit=False
    )
    yield _engine
    backend.database._engine = None
    backend.database._async_session_maker = None
    await _engine.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s


@pytest_asyncio.fixture
async def db_session(session) -> AsyncGenerator[AsyncSession, None]:
    async def _override():
        yield session

    app.dependency_overrides[backend.database.get_session] = _override
    yield session
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(db_session) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(autouse=True)
async def _reset_config():
    Config._data = {}
    Config.load()
    Config._data.setdefault("auth", {})["enabled"] = True
    Config._data.setdefault("auth", {}).setdefault("rate_limiting", {})["enabled"] = False
    yield
    Config._data = {}
    Config.load()


@pytest_asyncio.fixture
async def admin_token(client) -> str:
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": "admin@test.local",
            "password": "admin123",
            "display_name": "Admin",
            "full_name": "Test Admin",
        },
    )
    assert resp.status_code in (200, 409)
    resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@test.local", "password": "admin123"},
    )
    data = resp.json()
    return data.get("access_token", "")


@pytest_asyncio.fixture
async def admin_headers(admin_token: str) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}
