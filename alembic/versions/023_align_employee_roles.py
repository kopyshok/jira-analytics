"""Align Employee.role values with new frontend enum (analyst|dev|qa|other).

Revision ID: 023_align_employee_roles
Revises: 022_backlog_planning_chain
Create Date: 2026-04-20

Batch 4a перевёл UI на enum {analyst, dev, qa, other}. В БД встречаются старые
значения {programmer, consultant, tester, project_manager}. PATCH /employees/{id}
валидирует role через EMPLOYEE_ROLES — после деплоя без миграции UI ловит 422
"Unknown role".

Мэппинг upgrade:
    programmer       → dev
    tester           → qa
    consultant       → other
    project_manager  → other
    analyst          → analyst (без изменений)
    NULL             → NULL   (без изменений)
    любые неизвестные строки → other (защитная нормализация)

Downgrade — частично lossy: other нельзя однозначно разложить обратно.
Оставляем other как есть (см. комментарий ниже), обратимо мэппим только
dev→programmer и qa→tester.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "023_align_employee_roles"
down_revision: Union[str, None] = "022_backlog_planning_chain"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Прямые мэппинги. Idempotent: повторный прогон оставит всё как есть,
    # т.к. после первого апгрейда строк с role='programmer'/'tester'/...
    # просто не останется.
    op.execute("UPDATE employees SET role = 'dev'   WHERE role = 'programmer'")
    op.execute("UPDATE employees SET role = 'qa'    WHERE role = 'tester'")
    op.execute("UPDATE employees SET role = 'other' WHERE role IN ('consultant', 'project_manager')")

    # Защитная нормализация: если в БД оказалось неожиданное значение
    # (например, ручной UPDATE с dev-машины) — сводим к 'other', чтобы
    # не ломать PATCH-валидатор.
    op.execute(
        "UPDATE employees "
        "SET role = 'other' "
        "WHERE role IS NOT NULL "
        "AND role NOT IN ('analyst', 'dev', 'qa', 'other')"
    )


def downgrade() -> None:
    # Обратимая часть.
    op.execute("UPDATE employees SET role = 'programmer' WHERE role = 'dev'")
    op.execute("UPDATE employees SET role = 'tester'     WHERE role = 'qa'")
    # 'other' остаётся как есть: lossy downgrade — нельзя вернуть
    # исходное consultant/project_manager. Оставляем значение в БД,
    # старая валидация на EMPLOYEE_ROLES={programmer,consultant,tester,
    # analyst,project_manager} его не примет, но данные не теряются.
