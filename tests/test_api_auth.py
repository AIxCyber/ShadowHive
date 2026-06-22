"""Integration tests for auth endpoints."""


async def test_register(client):
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": "new@test.local",
            "password": "password123",
            "display_name": "New User",
            "full_name": "New User",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "user_id" in data


async def test_register_duplicate_email(client):
    await client.post(
        "/api/auth/register",
        json={
            "email": "dup@test.local",
            "password": "password123",
            "display_name": "Dup",
            "full_name": "Dup",
        },
    )
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": "dup@test.local",
            "password": "password123",
            "display_name": "Dup",
            "full_name": "Dup",
        },
    )
    assert resp.status_code == 409


async def test_login_success(client):
    await client.post(
        "/api/auth/register",
        json={
            "email": "login@test.local",
            "password": "mypassword",
            "display_name": "Login User",
            "full_name": "Login User",
        },
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "login@test.local", "password": "mypassword"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


async def test_login_wrong_password(client):
    await client.post(
        "/api/auth/register",
        json={
            "email": "wrongpw@test.local",
            "password": "correct",
            "display_name": "Wrong PW",
            "full_name": "Wrong PW",
        },
    )
    resp = await client.post(
        "/api/auth/login",
        json={"email": "wrongpw@test.local", "password": "wrong"},
    )
    assert resp.status_code == 401


async def test_login_nonexistent_user(client):
    resp = await client.post(
        "/api/auth/login",
        json={"email": "nobody@test.local", "password": "anything"},
    )
    assert resp.status_code == 401


async def test_me_endpoint(client, admin_token, admin_headers):
    resp = await client.get("/api/auth/me", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "admin@test.local"


async def test_me_unauthorized(client):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


async def test_change_password(client, admin_token, admin_headers):
    resp = await client.post(
        "/api/auth/change-password",
        headers=admin_headers,
        json={"current_password": "admin123", "new_password": "newadmin123"},
    )
    assert resp.status_code == 200

    resp = await client.post(
        "/api/auth/login",
        json={"email": "admin@test.local", "password": "newadmin123"},
    )
    assert resp.status_code == 200


async def test_refresh_token(client):
    await client.post(
        "/api/auth/register",
        json={
            "email": "refresh@test.local",
            "password": "password",
            "display_name": "Refresh",
            "full_name": "Refresh",
        },
    )
    login_resp = await client.post(
        "/api/auth/login",
        json={"email": "refresh@test.local", "password": "password"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    resp = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()
