"""Configuration parsing tests."""

from app.config import Settings


def test_debug_accepts_release_alias():
    settings = Settings(debug="release")

    assert settings.debug is False


def test_debug_accepts_dev_alias():
    settings = Settings(debug="dev")

    assert settings.debug is True


def test_cors_origins_accept_comma_separated_values():
    settings = Settings(
        cors_origins="http://localhost:3000, http://localhost:5173"
    )

    assert settings.cors_origins == [
        "http://localhost:3000",
        "http://localhost:5173",
    ]


def test_cors_origins_accept_comma_separated_env(monkeypatch):
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:5174,http://127.0.0.1:5174",
    )

    settings = Settings()

    assert settings.cors_origins == [
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ]
