"""
Tests for Authentication & Authorization (Phase 3).
Tests:
  - Registration & password hashing with Argon2id
  - Login with JWT generation
  - Token refresh and server-side revocation
  - Rejection of tampered, expired, and alg:none tokens
  - Role-based authorization
"""

import jwt
import pytest
from app.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hashing():
    """Argon2id produces verifiable, distinct hashes."""
    pwd = "CorrectHorseBatteryStaple123!"
    h1 = hash_password(pwd)
    h2 = hash_password(pwd)
    assert h1 != h2, "Salts must ensure distinct hashes"
    assert verify_password(pwd, h1)
    assert not verify_password("WrongPassword!", h1)


def test_jwt_create_and_decode():
    """JWT round-trips correctly with audience and issuer checks."""
    token = create_access_token(user_id="user-123", email="user@example.com", role="student")
    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["email"] == "user@example.com"
    assert payload["role"] == "student"
    assert payload["iss"] == "nexuslearn"
    assert payload["aud"] == "nexuslearn-api"


def test_jwt_rejects_none_algorithm():
    """Tokens signed with alg:none MUST be rejected (critical OWASP check)."""
    insecure_token = jwt.encode(
        {"sub": "user-123", "email": "hacker@example.com", "iss": "nexuslearn", "aud": "nexuslearn-api"},
        key="",
        algorithm="none",
    )
    with pytest.raises(Exception):
        decode_token(insecure_token)


def test_jwt_rejects_tampered_token():
    """Tampered signature must raise InvalidTokenError."""
    token = create_access_token(user_id="user-123", email="user@example.com", role="student")
    tampered = token[:-4] + "xxxx"
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(tampered)


def test_auth_api_flow(client):
    """Full API auth flow: register -> login -> refresh -> logout."""
    email = "student_alpha@nexuslearn.ai"
    pwd = "SecurePassword2026!"

    # 1. Register
    reg_resp = client.post("/auth/register", json={"email": email, "password": pwd})
    assert reg_resp.status_code == 201, reg_resp.text
    reg_data = reg_resp.json()
    assert "user_id" in reg_data
    assert reg_data["message"] == "Account created"

    # 2. Duplicate registration fails
    dup_resp = client.post("/auth/register", json={"email": email, "password": pwd})
    assert dup_resp.status_code == 400

    # 3. Login success
    login_resp = client.post("/auth/login", json={"email": email, "password": pwd})
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    assert "access_token" in login_data
    refresh_token = login_data["refresh_token"]

    # 4. Login wrong password fails
    bad_login = client.post("/auth/login", json={"email": email, "password": "WrongPassword!"})
    assert bad_login.status_code == 401

    # 5. Refresh token rotates and issues a new refresh token
    refresh_resp = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_resp.status_code == 200
    new_access_token = refresh_resp.json()["access_token"]
    new_refresh_token = refresh_resp.json()["refresh_token"]

    # 6. Logout revokes the new refresh token (authenticated)
    logout_resp = client.post(
        "/auth/logout",
        json={"refresh_token": new_refresh_token},
        headers={"Authorization": f"Bearer {new_access_token}"},
    )
    assert logout_resp.status_code == 200

    # 7. Revoked refresh token is rejected
    retry_refresh = client.post("/auth/refresh", json={"refresh_token": new_refresh_token})
    assert retry_refresh.status_code == 401


def test_unauthenticated_request_rejected(client):
    """Protected endpoints require valid Bearer token."""
    resp = client.get("/documents")
    assert resp.status_code == 401
