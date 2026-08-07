"""kpi: профиль оценки применяется к списку ролей, профиля по умолчанию больше нет

Было: у профиля одна роль плюс признак «профиль по умолчанию», который
подхватывал всех, у кого своей роли в профилях нет — из-за него в ведомость
попадали программисты и тестировщики.

Стало: отдельная таблица связи «профиль — роль», роль уникальна глобально.
Сотрудник, чья роль не привязана ни к одному профилю, в отчёт не попадает.

Данные переносятся: каждая непустая ``role_code`` становится строкой новой
таблицы. Профиль, отмеченный «по умолчанию» и не привязанный ни к одной роли,
после миграции не оценивает никого — это осознанное решение заказчика, а не
потеря данных.

Обратимость: ``downgrade`` возвращает колонки и кладёт в ``role_code`` первую
по алфавиту роль профиля; остальные роли и признак «по умолчанию»
восстановить неоткуда.

Revision ID: k13a_kpi_profile_roles
Revises: k12a_kpi_person_is_author
"""
import uuid
from datetime import datetime
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "k13a_kpi_profile_roles"
down_revision: Union[str, None] = "k12a_kpi_person_is_author"
branch_labels = None
depends_on = None

# Код роли «Руководитель проектов» в реестре ролей сервиса.
ROLE_PROJECT_MANAGER = "RP"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "kpi_profile_roles" not in inspector.get_table_names():
        op.create_table(
            "kpi_profile_roles",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("profile_id", sa.String(length=36), nullable=False),
            sa.Column("role_code", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["profile_id"], ["kpi_profiles.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_kpi_profile_roles_profile_id", "kpi_profile_roles", ["profile_id"])
        op.create_index(
            "ix_kpi_profile_roles_role_code", "kpi_profile_roles", ["role_code"], unique=True,
        )

    columns = {c["name"] for c in inspector.get_columns("kpi_profiles")}
    if "role_code" in columns:
        rows = list(bind.execute(sa.text(
            "SELECT id, role_code FROM kpi_profiles WHERE role_code IS NOT NULL AND role_code <> ''"
        )).fetchall())
        # Профиль «по умолчанию» раньше оценивал в том числе руководителей
        # проектов (спека 2026-07-30, раздел 5). Теперь такого признака нет,
        # поэтому роль привязывается явно — иначе руководители проектов молча
        # выпали бы из ведомости при обновлении.
        if "is_default" in columns:
            default_id = bind.execute(sa.text(
                "SELECT id FROM kpi_profiles WHERE is_default = true LIMIT 1"
            )).scalar()
            if default_id:
                rows.append((default_id, ROLE_PROJECT_MANAGER))
        # Одна роль могла быть указана у двух профилей — в новой схеме она
        # уникальна, поэтому берётся первый профиль, остальные пропускаются.
        # Таблица могла быть создана раньше (create_all + сид на старте
        # приложения) и уже содержать роли — иначе перенос падает на
        # уникальности role_code.
        seen: set[str] = {
            r[0] for r in bind.execute(
                sa.text("SELECT role_code FROM kpi_profile_roles")
            ).fetchall()
        }
        now = datetime.utcnow()
        for profile_id, role_code in rows:
            if role_code in seen:
                continue
            seen.add(role_code)
            bind.execute(
                sa.text(
                    "INSERT INTO kpi_profile_roles "
                    "(id, profile_id, role_code, created_at, updated_at) "
                    "VALUES (:id, :pid, :role, :now, :now)"
                ),
                {"id": str(uuid.uuid4()), "pid": profile_id, "role": role_code, "now": now},
            )

    # Чистая база: профиль «Аналитик» завела миграция k07a, но без ролей —
    # таблицы тогда ещё не было. Заводим их здесь, иначе после установки с нуля
    # профиль никого не оценивает. Коды ролей продублированы намеренно: миграция
    # не должна зависеть от константы в коде, которая может измениться.
    analyst_id = bind.execute(sa.text(
        "SELECT id FROM kpi_profiles WHERE code = 'analyst' LIMIT 1"
    )).scalar()
    if analyst_id:
        taken: set[str] = {
            r[0] for r in bind.execute(
                sa.text("SELECT role_code FROM kpi_profile_roles")
            ).fetchall()
        }
        now = datetime.utcnow()
        for role_code in ("analyst", ROLE_PROJECT_MANAGER):
            if role_code in taken:
                continue
            bind.execute(
                sa.text(
                    "INSERT INTO kpi_profile_roles "
                    "(id, profile_id, role_code, created_at, updated_at) "
                    "VALUES (:id, :pid, :role, :now, :now)"
                ),
                {"id": str(uuid.uuid4()), "pid": analyst_id, "role": role_code, "now": now},
            )

    # Индекс по удаляемой колонке снимается отдельно: batch-режим SQLite
    # пересоздаёт таблицу и пытается восстановить все её индексы, включая
    # индекс по колонке, которой в новой таблице уже нет.
    indexes = {i["name"] for i in inspector.get_indexes("kpi_profiles")}
    if "ix_kpi_profiles_role_code" in indexes:
        op.drop_index("ix_kpi_profiles_role_code", table_name="kpi_profiles")

    with op.batch_alter_table("kpi_profiles") as batch:
        if "role_code" in columns:
            batch.drop_column("role_code")
        if "is_default" in columns:
            batch.drop_column("is_default")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("kpi_profiles")}

    with op.batch_alter_table("kpi_profiles") as batch:
        if "role_code" not in columns:
            batch.add_column(sa.Column("role_code", sa.String(length=64), nullable=True))
        if "is_default" not in columns:
            batch.add_column(
                sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            )

    if "kpi_profile_roles" in inspector.get_table_names():
        rows = bind.execute(sa.text(
            "SELECT profile_id, role_code FROM kpi_profile_roles ORDER BY profile_id, role_code"
        )).fetchall()
        restored: set[str] = set()
        for profile_id, role_code in rows:
            if profile_id in restored:
                continue
            restored.add(profile_id)
            bind.execute(
                sa.text("UPDATE kpi_profiles SET role_code = :role WHERE id = :pid"),
                {"role": role_code, "pid": profile_id},
            )
        op.drop_table("kpi_profile_roles")
