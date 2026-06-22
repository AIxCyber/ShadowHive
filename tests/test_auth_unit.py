"""Unit tests for auth primitives — no DB needed."""

from datetime import timedelta

import pytest

from backend.auth import (
    _base64url_decode,
    _base64url_encode,
    _hash_password,
    _verify_password,
    create_access_token,
    create_refresh_token,
    create_token,
    decode_token,
    is_account_locked,
)
from backend.models.user import User


class TestPasswordHashing:
    def test_hash_and_verify(self):
        pw = "my-secure-password-123!"
        hashed = _hash_password(pw)
        assert hashed != pw
        assert "$" in hashed
        assert _verify_password(pw, hashed)

    def test_wrong_password_fails(self):
        hashed = _hash_password("correct")
        assert not _verify_password("wrong", hashed)

    def test_empty_password(self):
        hashed = _hash_password("")
        assert _verify_password("", hashed)
        assert not _verify_password("x", hashed)

    def test_malformed_stored_hash(self):
        assert not _verify_password("test", "not-a-valid-hash")
        assert not _verify_password("test", "")
        assert not _verify_password("test", "only-one$part")

    def test_different_salts(self):
        h1 = _hash_password("same")
        h2 = _hash_password("same")
        assert h1 != h2


class TestBase64Url:
    def test_roundtrip(self):
        data = b"hello world\xff\x00"
        encoded = _base64url_encode(data)
        decoded = _base64url_decode(encoded)
        assert decoded == data

    def test_no_padding_in_output(self):
        encoded = _base64url_encode(b"test")
        assert "=" not in encoded

    def test_empty(self):
        assert _base64url_decode(_base64url_encode(b"")) == b""


class TestJWT:
    def test_create_and_decode(self):
        token = create_token({"sub": "user-1"}, timedelta(hours=1))
        payload = decode_token(token)
        assert payload["sub"] == "user-1"

    def test_expired_token(self):
        token = create_token({"sub": "user-1"}, timedelta(hours=-1))
        with pytest.raises(ValueError, match="Token expired"):
            decode_token(token)

    def test_invalid_signature(self):
        token = create_token({"sub": "user-1"}, timedelta(hours=1))
        parts = token.split(".")
        tampered = f"{parts[0]}.{parts[1]}.invalidsignature"
        with pytest.raises(ValueError, match="Invalid token signature"):
            decode_token(tampered)

    def test_malformed_token(self):
        with pytest.raises(ValueError, match="Invalid token format"):
            decode_token("not-a-token")
        with pytest.raises(ValueError, match="Invalid token format"):
            decode_token("too.many.parts.here")

    def test_access_token_has_correct_type(self):
        token = create_access_token("user-1", "admin")
        payload = decode_token(token)
        assert payload["type"] == "access"
        assert payload["role"] == "admin"
        assert payload["sub"] == "user-1"

    def test_refresh_token(self):
        token = create_refresh_token("user-1")
        payload = decode_token(token)
        assert payload["type"] == "refresh"
        assert payload["sub"] == "user-1"


class TestAccountLockout:
    def test_not_locked_by_default(self):
        user = User()
        assert not is_account_locked(user)

    def test_no_lockout_below_threshold(self):
        user = User()
        assert not is_account_locked(user)
