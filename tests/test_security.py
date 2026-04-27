import pytest
from jose import JWTError
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_hash_and_verify():
    hashed = hash_password("mysecret")
    assert hashed != "mysecret"
    assert verify_password("mysecret", hashed)
    assert not verify_password("wrong", hashed)


def test_create_and_decode_token():
    payload = {"sub": "user-123", "role": "manager", "default_team": "Team A"}
    token = create_access_token(payload, expires_hours=1)
    decoded = decode_access_token(token)
    assert decoded["sub"] == "user-123"
    assert decoded["role"] == "manager"
    assert decoded["default_team"] == "Team A"


def test_decode_invalid_token_raises():
    with pytest.raises(JWTError):
        decode_access_token("not.a.valid.token")
