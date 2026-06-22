"""Integration tests for Companies, Events, Sessions, Threats, Admin, and Deploy APIs."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from backend.database import get_session
from backend.models.company import (
    AttackerEvent,
    Company,
    CompanyProfile,
    Employee,
)
from backend.models.user import User

# ── Helpers ───────────────────────────────────────────────────────────────────


async def _seed_company(session) -> Company:
    c = Company(
        id=uuid.uuid4(),
        name="Test Corp",
        industry="Technology",
        size="medium",
        description="A test company",
        location_city="San Francisco",
        location_country="USA",
        founded_year="2020",
        status="active",
        created_at=datetime.now(UTC),
    )
    session.add(c)
    await session.commit()
    return c


async def _seed_employee(session, company_id: uuid.UUID) -> Employee:
    e = Employee(
        id=uuid.uuid4(),
        company_id=company_id,
        first_name="Jane",
        last_name="Doe",
        email="jane@testcorp.com",
        title="Engineer",
        department="Engineering",
        created_at=datetime.now(UTC),
    )
    session.add(e)
    await session.commit()
    return e


async def _seed_event(session, **overrides) -> AttackerEvent:
    defaults = {
        "id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "source_ip": "10.0.0.1",
        "event_type": "ssh_login",
        "command": None,
        "session_id": None,
        "severity": "medium",
        "mitre_technique_id": None,
        "mitre_tactic": None,
        "detected_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    e = AttackerEvent(**defaults)
    session.add(e)
    await session.commit()
    return e


async def _create_admin_user(session) -> User:
    from backend.auth import _hash_password

    u = User(
        id=uuid.uuid4(),
        email="admin-int@test.local",
        password_hash=_hash_password("admin123"),
        display_name="Integration Admin",
        role="admin",
        is_active=True,
        must_change_password=False,
        created_at=datetime.now(UTC),
    )
    session.add(u)
    await session.commit()
    return u


async def _create_regular_user(session) -> User:
    from backend.auth import _hash_password

    u = User(
        id=uuid.uuid4(),
        email="user-int@test.local",
        password_hash=_hash_password("userpass123"),
        display_name="Regular User",
        role="user",
        is_active=True,
        must_change_password=False,
        created_at=datetime.now(UTC),
    )
    session.add(u)
    await session.commit()
    return u


def _login_body(email: str = "admin-int@test.local") -> dict:
    return {"email": email, "password": "admin123"}


# ── Companies API ─────────────────────────────────────────────────────────────


class TestCompaniesAPI:
    async def test_list_companies_empty(self, client: AsyncClient):
        resp = await client.get("/api/companies")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_companies_with_data(self, client: AsyncClient, session):
        await _seed_company(session)
        resp = await client.get("/api/companies")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Corp"

    async def test_get_company_not_found(self, client: AsyncClient):
        resp = await client.get(f"/api/companies/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_get_company_full(self, client: AsyncClient, session):
        company = await _seed_company(session)
        await _seed_employee(session, company.id)

        resp = await client.get(f"/api/companies/{company.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Corp"
        assert len(data["employees"]) == 1
        assert data["employees"][0]["first_name"] == "Jane"

    async def test_create_profile(self, client: AsyncClient):
        resp = await client.post(
            "/api/companies/profiles",
            json={"name": "My Template", "industry": "Finance"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "My Template"
        assert data["industry"] == "Finance"

    async def test_list_profiles(self, client: AsyncClient, session):
        profile = CompanyProfile(
            id=uuid.uuid4(),
            name="Template A",
            industry="Healthcare",
        )
        session.add(profile)
        await session.commit()

        resp = await client.get("/api/companies/profiles")
        data = resp.json()
        assert len(data) >= 1
        names = [p["name"] for p in data]
        assert "Template A" in names

    async def test_get_profile(self, client: AsyncClient, session):
        profile = CompanyProfile(
            id=uuid.uuid4(),
            name="Template B",
            industry="Energy",
        )
        session.add(profile)
        await session.commit()

        resp = await client.get(f"/api/companies/profiles/{profile.id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Template B"

    async def test_get_profile_not_found(self, client: AsyncClient):
        resp = await client.get(f"/api/companies/profiles/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_delete_profile(self, client: AsyncClient, session):
        profile = CompanyProfile(
            id=uuid.uuid4(),
            name="To Delete",
            industry="Retail",
        )
        session.add(profile)
        await session.commit()

        resp = await client.delete(f"/api/companies/profiles/{profile.id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    async def test_delete_profile_not_found(self, client: AsyncClient):
        resp = await client.delete(f"/api/companies/profiles/{uuid.uuid4()}")
        assert resp.status_code == 404


# ── Events API ────────────────────────────────────────────────────────────────


class TestEventsAPI:
    async def test_ingest_single_event(self, client: AsyncClient):
        resp = await client.post(
            "/api/events",
            json={
                "events": [
                    {
                        "source_ip": "10.0.0.5",
                        "event_type": "ssh_login",
                        "command": "whoami",
                        "session_id": "sess-001",
                        "severity": "high",
                    }
                ]
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["ingested"] == 1
        assert len(data["ids"]) == 1

    async def test_ingest_batch(self, client: AsyncClient):
        resp = await client.post(
            "/api/events",
            json={
                "events": [
                    {"source_ip": "10.0.0.1", "event_type": "ssh_login"},
                    {"source_ip": "10.0.0.2", "event_type": "command", "command": "cat /etc/passwd"},
                ]
            },
        )
        assert resp.status_code == 201
        assert resp.json()["ingested"] == 2

    async def test_ingest_empty_batch(self, client: AsyncClient):
        resp = await client.post("/api/events", json={"events": []})
        assert resp.status_code == 400

    async def test_ingest_with_mitre(self, client: AsyncClient):
        resp = await client.post(
            "/api/events",
            json={
                "events": [
                    {
                        "source_ip": "10.0.0.3",
                        "event_type": "command",
                        "command": "powershell -enc ...",
                        "mitre_technique_id": "T1059.001",
                        "mitre_tactic": "Execution",
                        "severity": "critical",
                    }
                ]
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["ingested"] == 1

    async def test_ingest_persists_to_db(self, client: AsyncClient, session):
        await client.post(
            "/api/events",
            json={
                "events": [
                    {
                        "source_ip": "10.0.0.99",
                        "event_type": "ssh_login",
                        "session_id": "sess-persist",
                    }
                ]
            },
        )
        from sqlalchemy import select

        result = await session.execute(
            select(AttackerEvent).where(AttackerEvent.session_id == "sess-persist")
        )
        event = result.scalar_one_or_none()
        assert event is not None
        assert event.source_ip == "10.0.0.99"
        assert event.session_id == "sess-persist"


# ── Sessions API ──────────────────────────────────────────────────────────────


class TestSessionsAPI:
    async def test_list_sessions_empty(self, client: AsyncClient):
        resp = await client.get("/api/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_sessions_with_events(self, client: AsyncClient, session):
        sid = "sess-int-001"
        await _seed_event(session, session_id=sid, source_ip="10.0.0.1")
        await _seed_event(session, session_id=sid, source_ip="10.0.0.1", command="ls")

        resp = await client.get("/api/sessions")
        data = resp.json()
        assert len(data) >= 1
        matching = [s for s in data if s["session_id"] == sid]
        assert len(matching) == 1
        assert matching[0]["commands_executed"] == 1

    async def test_list_sessions_with_min_risk(self, client: AsyncClient, session):
        low_sid = "sess-low"
        high_sid = "sess-high"
        await _seed_event(session, session_id=low_sid, severity="low")
        await _seed_event(session, session_id=high_sid, severity="high")

        resp = await client.get("/api/sessions?min_risk=4")
        data = resp.json()
        sids = [s["session_id"] for s in data]
        assert high_sid in sids
        assert low_sid not in sids

    async def test_list_sessions_pagination(self, client: AsyncClient, session):
        for i in range(5):
            sid = f"sess-pag-{i}"
            await _seed_event(session, session_id=sid, severity="medium")

        resp = await client.get("/api/sessions?limit=2")
        data = resp.json()
        assert len(data) <= 2


# ── Threats API ───────────────────────────────────────────────────────────────


class TestThreatsAPI:
    async def test_list_threats_empty(self, client: AsyncClient):
        resp = await client.get("/api/threats")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_threats_with_data(self, client: AsyncClient, session):
        await _seed_event(
            session,
            mitre_technique_id="T1059",
            mitre_tactic="Execution",
            severity="high",
        )

        resp = await client.get("/api/threats")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["technique"] == "T1059"

    async def test_filter_by_severity(self, client: AsyncClient, session):
        await _seed_event(session, severity="low")
        await _seed_event(session, severity="critical")

        resp = await client.get("/api/threats?severity=critical")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["severity"] == "critical"

    async def test_filter_by_tactic(self, client: AsyncClient, session):
        await _seed_event(session, mitre_tactic="Execution")
        await _seed_event(session, mitre_tactic="Persistence")

        resp = await client.get("/api/threats?tactic=Execution")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["tactic"] == "Execution"

    async def test_filter_by_severity_and_tactic(self, client: AsyncClient, session):
        await _seed_event(session, severity="high", mitre_tactic="Execution")
        await _seed_event(session, severity="low", mitre_tactic="Execution")

        resp = await client.get("/api/threats?severity=low&tactic=Execution")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["severity"] == "low"

    async def test_list_threats_limits(self, client: AsyncClient, session):
        for i in range(5):
            await _seed_event(session, severity="medium")

        resp = await client.get("/api/threats?limit=2")
        data = resp.json()
        assert len(data) == 2


# ── Admin API ─────────────────────────────────────────────────────────────────


class TestAdminAPI:
    async def _admin_token(self, client, session) -> str:
        await _create_admin_user(session)
        resp = await client.post("/api/auth/login", json=_login_body())
        assert resp.status_code == 200
        return resp.json()["access_token"]

    async def _auth_header(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    async def test_list_users_requires_admin(self, client: AsyncClient, session):
        await _create_regular_user(session)
        resp = await client.post("/api/auth/login", json={"email": "user-int@test.local", "password": "userpass123"})
        assert resp.status_code == 200
        token = resp.json()["access_token"]

        resp = await client.get("/api/admin/users", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    async def test_list_users(self, client: AsyncClient, session):
        token = await self._admin_token(client, session)
        resp = await client.get("/api/admin/users", headers=await self._auth_header(token))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        emails = [u["email"] for u in data]
        assert "admin-int@test.local" in emails

    async def test_create_user(self, client: AsyncClient, session):
        token = await self._admin_token(client, session)
        resp = await client.post(
            "/api/admin/users",
            headers=await self._auth_header(token),
            json={
                "email": "new-team@test.local",
                "password": "strongpass123",
                "display_name": "New User",
                "role": "user",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "new-team@test.local"

    async def test_create_duplicate_user(self, client: AsyncClient, session):
        token = await self._admin_token(client, session)
        await _create_regular_user(session)
        resp = await client.post(
            "/api/admin/users",
            headers=await self._auth_header(token),
            json={
                "email": "user-int@test.local",
                "password": "strongpass123",
                "display_name": "Duplicate",
                "role": "user",
            },
        )
        assert resp.status_code == 409

    async def test_get_user(self, client: AsyncClient, session):
        token = await self._admin_token(client, session)
        target = await _create_regular_user(session)

        resp = await client.get(
            f"/api/admin/users/{target.id}",
            headers=await self._auth_header(token),
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "user-int@test.local"

    async def test_update_user(self, client: AsyncClient, session):
        token = await self._admin_token(client, session)
        target = await _create_regular_user(session)

        resp = await client.put(
            f"/api/admin/users/{target.id}",
            headers=await self._auth_header(token),
            json={"display_name": "Updated Name", "role": "admin"},
        )
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Updated Name"
        assert resp.json()["role"] == "admin"

    async def test_cannot_deactivate_self(self, client: AsyncClient, session):
        token = await self._admin_token(client, session)
        admin_user = None
        async for db in get_session():
            result = await db.execute(
                __import__("sqlalchemy").select(User).where(User.email == "admin-int@test.local")
            )
            admin_user = result.scalar_one()

        resp = await client.put(
            f"/api/admin/users/{admin_user.id}",
            headers=await self._auth_header(token),
            json={"is_active": False},
        )
        assert resp.status_code == 400

    async def test_delete_user(self, client: AsyncClient, session):
        token = await self._admin_token(client, session)
        target = await _create_regular_user(session)

        resp = await client.delete(
            f"/api/admin/users/{target.id}",
            headers=await self._auth_header(token),
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    async def test_cannot_delete_self(self, client: AsyncClient, session):
        token = await self._admin_token(client, session)
        admin_user = None
        async for db in get_session():
            result = await db.execute(
                __import__("sqlalchemy").select(User).where(User.email == "admin-int@test.local")
            )
            admin_user = result.scalar_one()

        resp = await client.delete(
            f"/api/admin/users/{admin_user.id}",
            headers=await self._auth_header(token),
        )
        assert resp.status_code == 400

    async def test_reset_password(self, client: AsyncClient, session):
        token = await self._admin_token(client, session)
        target = await _create_regular_user(session)

        resp = await client.post(
            f"/api/admin/users/{target.id}/reset-password",
            headers=await self._auth_header(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "temporary_password" in data
        assert len(data["temporary_password"]) >= 12


# ── Stats API ──────────────────────────────────────────────────────────────────


class TestStatsAPI:
    async def test_stats_mitre_coverage_capped(self, client: AsyncClient, session):
        """MITRE coverage should never exceed 100% even with extra tactics."""
        from datetime import UTC, datetime

        for i in range(20):
            await _seed_event(
                session,
                mitre_technique_id=f"T999{i}",
                mitre_tactic=f"extra-tactic-{i}",
                severity="medium",
            )
        resp = await client.get("/api/stats?range=all")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mitre_coverage_pct"] <= 100
        assert data["mitre_tactics_mapped"] <= 14

    async def test_stats_mitre_normalized_tactics(self, client: AsyncClient, session):
        """Tactics with different case/formats should be deduplicated."""
        variants = ["Execution", "execution", "EXECUTION", "execution "]
        for v in variants:
            await _seed_event(
                session,
                mitre_technique_id="T1204",
                mitre_tactic=v,
                severity="low",
            )
        resp = await client.get("/api/stats?range=all")
        data = resp.json()
        assert data["mitre_tactics_mapped"] == 1

    async def test_stats_mitre_hyphen_normalized(self, client: AsyncClient, session):
        """Tactics with spaces/hyphens should be deduplicated."""
        await _seed_event(
            session,
            mitre_technique_id="T1059",
            mitre_tactic="defense-evasion",
            severity="medium",
        )
        await _seed_event(
            session,
            mitre_technique_id="T1078",
            mitre_tactic="Defense Evasion",
            severity="medium",
        )
        resp = await client.get("/api/stats?range=all")
        data = resp.json()
        assert data["mitre_tactics_mapped"] == 1

    async def test_stats_empty(self, client: AsyncClient):
        resp = await client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["threat_events_total"] == 0
        assert data["mitre_coverage_pct"] == 0

    async def test_stats_with_data(self, client: AsyncClient, session):
        await _seed_event(session, severity="high", mitre_tactic="Execution")
        resp = await client.get("/api/stats?range=all")
        data = resp.json()
        assert data["threat_events_total"] >= 1
        assert data["mitre_tactics_mapped"] >= 1


# ── Deploy API (mocked) ───────────────────────────────────────────────────────


class TestDeployAPI:
    async def _admin_token(self, client, session) -> str:
        await _create_admin_user(session)
        resp = await client.post("/api/auth/login", json=_login_body())
        assert resp.status_code == 200
        return resp.json()["access_token"]

    async def _auth_header(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    @patch("backend.api.deploy.deploy_company")
    @patch("backend.api.deploy.get_deployment_status")
    async def test_deploy_company(
        self,
        mock_status: AsyncMock,
        mock_deploy: AsyncMock,
        client: AsyncClient,
        session,
    ):
        company = await _seed_company(session)
        mock_status.return_value = {"active": False}
        mock_deploy.return_value = {"deployed": True, "company_id": str(company.id)}

        token = await self._admin_token(client, session)
        resp = await client.post(
            f"/api/deploy/{company.id}",
            headers=await self._auth_header(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["deployed"] is True

    @patch("backend.api.deploy.undeploy_company")
    async def test_undeploy(
        self,
        mock_undeploy: AsyncMock,
        client: AsyncClient,
        session,
    ):
        mock_undeploy.return_value = {"undeployed": True, "previous": "Test Corp"}

        token = await self._admin_token(client, session)
        resp = await client.post(
            "/api/deploy/undeploy",
            headers=await self._auth_header(token),
        )
        assert resp.status_code == 200
        assert resp.json()["undeployed"] is True

    @patch("backend.api.deploy.get_deployment_status")
    async def test_deploy_status(
        self,
        mock_status: AsyncMock,
        client: AsyncClient,
        session,
    ):
        mock_status.return_value = {"active": True, "company_id": str(uuid.uuid4())}

        token = await self._admin_token(client, session)
        resp = await client.get(
            "/api/deploy/status",
            headers=await self._auth_header(token),
        )
        assert resp.status_code == 200
        assert resp.json()["active"] is True

    @patch("backend.api.deploy.get_deployment_status")
    async def test_deploy_unauthorized(
        self,
        mock_status: AsyncMock,
        client: AsyncClient,
        session,
    ):
        await _create_regular_user(session)
        resp = await client.post("/api/auth/login", json={"email": "user-int@test.local", "password": "userpass123"})
        assert resp.status_code == 200
        token = resp.json()["access_token"]

        resp = await client.post(
            f"/api/deploy/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
