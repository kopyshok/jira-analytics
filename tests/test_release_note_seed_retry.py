"""Наполнение ленты при старте переживает недоступную на первой секунде БД."""
from app.services import release_note_seed


def test_retry_succeeds_after_transient_failure(monkeypatch):
    calls = {"seed": 0, "sleep": 0}

    class FakeSeeder:
        def __init__(self, db, source_dir=None):
            self.db = db

        def seed(self):
            calls["seed"] += 1
            if calls["seed"] == 1:
                raise RuntimeError("база ещё поднимается")
            return {"created": 1}

    monkeypatch.setattr(release_note_seed, "ReleaseNoteSeeder", FakeSeeder)

    class FakeSession:
        def close(self):
            pass

    stats = release_note_seed.seed_with_retry(
        FakeSession, attempts=3, delay_seconds=0, sleep=lambda _: calls.__setitem__("sleep", calls["sleep"] + 1)
    )
    assert stats == {"created": 1}
    assert calls["seed"] == 2
    assert calls["sleep"] == 1


def test_retry_gives_up_and_returns_none(monkeypatch):
    class AlwaysFails:
        def __init__(self, db, source_dir=None):
            pass

        def seed(self):
            raise RuntimeError("нет соединения")

    monkeypatch.setattr(release_note_seed, "ReleaseNoteSeeder", AlwaysFails)

    class FakeSession:
        def close(self):
            pass

    assert release_note_seed.seed_with_retry(
        FakeSession, attempts=2, delay_seconds=0, sleep=lambda _: None
    ) is None
