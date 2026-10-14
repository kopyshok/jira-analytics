"""Состояние переезда на Jira Data Center и единая проверка «синк разрешён».

Пока база не переведена на идентификаторы новой Jira (``pending``), любой
пишущий синк перезаписал бы чужие строки: id задач, ворклогов и людей в новой
Jira пересекаются со старыми id других записей. Поэтому все пишущие пути синка
проходят через :func:`ensure_sync_allowed` (конструктор ``SyncService`` и
явная проверка в начале пишущих эндпоинтов).
"""

from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting

MIGRATION_STATE_KEY = "jira_migration_state"
STATE_PENDING = "pending"
STATE_DONE = "done"
# Префикс id, оставшихся от облачной Jira (задачи, ворклоги, люди без пары в новой).
# Такие строки синк не узнаёт и не удаляет: из Jira они больше не придут.
CLOUD_PREFIX = "cloud:"
SYNC_BLOCKED_MESSAGE = "Синхронизация остановлена до завершения переезда на новую Jira"


class SyncBlockedError(Exception):
    """Синк запрещён до завершения переезда. HTTP-ответ — 409 (см. ``app.main``)."""

    def __init__(self) -> None:
        super().__init__(SYNC_BLOCKED_MESSAGE)


def get_migration_state(db: Session) -> str:
    """``pending`` или ``done``. Нет записи (база из ``create_all``) — ``done``.

    Закрыто по умолчанию: любое значение, кроме ровно ``done``, — ``pending``.
    """
    value = (
        db.query(AppSetting.value)
        .filter(AppSetting.key == MIGRATION_STATE_KEY)
        .scalar()
    )
    return STATE_DONE if value is None or value == STATE_DONE else STATE_PENDING


def is_sync_blocked(db: Session) -> bool:
    """Синк с Jira запрещён до завершения переезда."""
    return get_migration_state(db) == STATE_PENDING


def ensure_sync_allowed(db: Session) -> None:
    """Поднять :class:`SyncBlockedError`, если переезд не завершён."""
    if is_sync_blocked(db):
        raise SyncBlockedError()


def set_migration_state(db: Session, state: str) -> None:
    """Записать состояние переезда.

    **Не коммитит**: применение переезда ставит ``done`` в той же транзакции,
    что и перепривязку данных, — откат возвращает и состояние.
    """
    if state not in (STATE_PENDING, STATE_DONE):
        raise ValueError(f"Неизвестное состояние переезда: {state!r}")
    row = db.query(AppSetting).filter(AppSetting.key == MIGRATION_STATE_KEY).first()
    if row is None:
        db.add(AppSetting(key=MIGRATION_STATE_KEY, value=state))
    else:
        row.value = state
    db.flush()
