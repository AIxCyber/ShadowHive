"""Smoke tests — verify test infrastructure works."""


def test_imports():
    from backend.auth import _hash_password
    from backend.services.mitre_mapper import rule_based_match
    from backend.utils.config import Config

    assert callable(_hash_password)
    assert callable(rule_based_match)
    assert isinstance(Config.get("auth.enabled"), bool)


async def test_root_endpoint(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "ShadowHive"


async def test_health_endpoint(client):
    resp = await client.get("/api/companies/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
