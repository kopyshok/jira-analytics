"""Авто-определение команды сотрудника по ворклогам.

Мода берётся по суммарным часам на задачах с заданным `issue.team`,
в окне последних `lookback_days` дней. Возвращает None, если у сотрудника
нет worklog'ов с ненулевым team за окно.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Category, Employee, EmployeeTeam, Issue, Worklog
from app.services import team_membership as tm


# Коды категорий, исключаемые из скана: «Архив прочих задач» + «Инициативы».
# Остальные — «Активный стек» ∪ «Архив квартальных задач».
EXCLUDED_CATEGORY_CODES: set[str] = {"archive", "initiatives_rfa"}


@dataclass
class AutoDetectSummary:
    assigned: int
    skipped: int
    details: list[dict]


class EmployeeTeamService:
    def __init__(self, db: Session):
        self.db = db

    def _target_category_codes(self) -> set[str]:
        all_codes = {c.code for c in self.db.query(Category).all()}
        return all_codes - EXCLUDED_CATEGORY_CODES

    def auto_detect_team(
        self, employee_id: str, *, lookback_days: Optional[int] = None
    ) -> Optional[str]:
        target_codes = self._target_category_codes()
        q = (
            self.db.query(
                Issue.team.label("team"),
                func.coalesce(func.sum(Worklog.time_spent_seconds), 0).label("seconds"),
            )
            .join(Worklog, Worklog.issue_id == Issue.id)
            .filter(
                Worklog.employee_id == employee_id,
                Issue.team.isnot(None),
                Issue.team != "",
                Issue.category.in_(target_codes),
            )
        )
        if lookback_days is not None:
            cutoff = datetime.utcnow() - timedelta(days=lookback_days)
            q = q.filter(Worklog.started_at >= cutoff)
        rows = (
            q.group_by(Issue.team)
            .order_by(func.sum(Worklog.time_spent_seconds).desc())
            .all()
        )
        if not rows:
            return None
        return rows[0].team

    def auto_detect_all_missing(self) -> AutoDetectSummary:
        """Массово проставить primary team для сотрудников без membership.

        «Missing» = `employee_teams` для сотрудника пуст (а не `Employee.team IS NULL`):
        legacy-колонка — derived source, единственный источник истины — M:N-таблица.
        Назначение идёт через `add_team`, чтобы сохранить single-primary invariant
        и синхронно обновить `Employee.team`.
        """
        assigned = 0
        skipped = 0
        details: list[dict] = []
        employees = (
            self.db.query(Employee)
            .filter(Employee.is_active == True)  # noqa: E712
            .all()
        )
        for emp in employees:
            has_any = (
                self.db.query(EmployeeTeam)
                .filter(
                    EmployeeTeam.employee_id == emp.id,
                    EmployeeTeam.left_at.is_(None),
                )
                .count()
            ) > 0
            if has_any:
                skipped += 1
                continue
            team = self.auto_detect_team(emp.id)
            if team is None:
                skipped += 1
                continue
            # `add_team` коммитит сам, делает первый team primary автоматически,
            # и обновляет `Employee.team` через `_recompute_legacy_team`.
            self.add_team(emp.id, team)
            assigned += 1
            details.append({"employee_id": emp.id, "team": team})
        return AutoDetectSummary(assigned=assigned, skipped=skipped, details=details)

    def _recompute_legacy_team(self, employee_id: str) -> None:
        """Обновить ``Employee.team`` = основная команда НА СЕГОДНЯ (или None).

        Derived-колонка для backward-compat с кодом, который ещё читает
        ``Employee.team`` напрямую. Вызывается из всех мутаций.
        """
        team = tm.primary_team_on(self.db, employee_id, date.today())
        emp = self.db.query(Employee).filter(Employee.id == employee_id).one()
        emp.team = team

    def _assert_no_overlap(
        self,
        employee_id: str,
        team: str,
        joined_at: Optional[date],
        left_at: Optional[date],
        *,
        exclude_id: Optional[str] = None,
    ) -> None:
        """Периоды одной пары сотрудник/команда не должны пересекаться."""
        if joined_at and left_at and left_at < joined_at:
            raise ValueError("Дата выбытия раньше даты вступления")
        rows = (
            self.db.query(EmployeeTeam)
            .filter(
                EmployeeTeam.employee_id == employee_id,
                EmployeeTeam.team == team,
            )
            .all()
        )
        lo = joined_at or date.min
        hi = left_at or date.max
        for r in rows:
            if exclude_id and r.id == exclude_id:
                continue
            r_lo = r.joined_at or date.min
            r_hi = r.left_at or date.max
            if lo < r_hi and r_lo < hi:
                raise ValueError(
                    f"Период пересекается с существующим участием в команде {team!r}"
                )

    def _assert_single_primary(
        self,
        employee_id: str,
        team: str,
        joined_at: Optional[date],
        left_at: Optional[date],
        *,
        exclude_id: Optional[str] = None,
    ) -> None:
        """На любую дату у сотрудника не более одной основной команды."""
        rows = (
            self.db.query(EmployeeTeam)
            .filter(
                EmployeeTeam.employee_id == employee_id,
                EmployeeTeam.is_primary == True,  # noqa: E712
            )
            .all()
        )
        lo = joined_at or date.min
        hi = left_at or date.max
        for r in rows:
            if exclude_id and r.id == exclude_id:
                continue
            if r.team == team:
                continue
            r_lo = r.joined_at or date.min
            r_hi = r.left_at or date.max
            if lo < r_hi and r_lo < hi:
                raise ValueError(
                    f"На эти даты основной уже назначена команда {r.team!r}"
                )

    def list_teams(self, employee_id: str) -> list[EmployeeTeam]:
        """Все периоды участия: открытые первыми, затем по дате входа убыв."""
        return (
            self.db.query(EmployeeTeam)
            .filter(EmployeeTeam.employee_id == employee_id)
            .order_by(
                EmployeeTeam.left_at.is_(None).desc(),
                EmployeeTeam.is_primary.desc(),
                EmployeeTeam.team,
            )
            .all()
        )

    def add_team(
        self,
        employee_id: str,
        team: str,
        *,
        is_primary: bool = False,
        joined_at: Optional[date] = None,
        allow_primary_overlap: bool = True,
    ) -> EmployeeTeam:
        """Добавить период участия в команде.

        Если у сотрудника ещё нет ни одного участия — период становится
        основным автоматически. Если открытый период в этой команде уже есть,
        возвращается он (идемпотентность для авто-определения команды).

        ``allow_primary_overlap=False`` включает строгую проверку «одна
        основная на дату»; по умолчанию основная просто перевешивается
        на новый период — так ведёт себя UI выбора основной команды.
        """
        open_existing = (
            self.db.query(EmployeeTeam)
            .filter(
                EmployeeTeam.employee_id == employee_id,
                EmployeeTeam.team == team,
                EmployeeTeam.left_at.is_(None),
            )
            .first()
        )
        if open_existing is not None:
            if is_primary and not open_existing.is_primary:
                self.set_primary(employee_id, team)
                self.db.refresh(open_existing)
            return open_existing

        self._assert_no_overlap(employee_id, team, joined_at, None)

        has_any = (
            self.db.query(EmployeeTeam)
            .filter(EmployeeTeam.employee_id == employee_id)
            .count()
        ) > 0
        make_primary = is_primary or not has_any
        if make_primary:
            if allow_primary_overlap:
                # Перевешиваем основную: снимаем признак у открытых периодов.
                self.db.query(EmployeeTeam).filter(
                    EmployeeTeam.employee_id == employee_id,
                    EmployeeTeam.is_primary == True,  # noqa: E712
                    EmployeeTeam.left_at.is_(None),
                ).update({EmployeeTeam.is_primary: False}, synchronize_session="fetch")
            else:
                self._assert_single_primary(employee_id, team, joined_at, None)

        row = EmployeeTeam(
            employee_id=employee_id,
            team=team,
            is_primary=make_primary,
            joined_at=joined_at,
        )
        self.db.add(row)
        self.db.flush()
        self._recompute_legacy_team(employee_id)
        self.db.commit()
        self.db.refresh(row)
        return row

    def remove_team(self, employee_id: str, team: str) -> None:
        """Удалить открытый период участия. Закрытые периоды — история, не трогаем.

        Для «человек ушёл» правильный путь — ``set_left_at`` / ``transfer``;
        удаление означает «участия не было вовсе» (ошибка ввода).
        """
        row = (
            self.db.query(EmployeeTeam)
            .filter(
                EmployeeTeam.employee_id == employee_id,
                EmployeeTeam.team == team,
                EmployeeTeam.left_at.is_(None),
            )
            .first()
        )
        if row is None:
            return
        was_primary = row.is_primary
        self.db.delete(row)
        self.db.flush()
        if was_primary:
            # Промоутим любой оставшийся открытый (сортировка по team — детерминизм).
            leftover = (
                self.db.query(EmployeeTeam)
                .filter(
                    EmployeeTeam.employee_id == employee_id,
                    EmployeeTeam.left_at.is_(None),
                )
                .order_by(EmployeeTeam.team)
                .first()
            )
            if leftover is not None:
                leftover.is_primary = True
                self.db.flush()
        self._recompute_legacy_team(employee_id)
        self.db.commit()

    def set_primary(self, employee_id: str, team: str) -> None:
        target = (
            self.db.query(EmployeeTeam)
            .filter(
                EmployeeTeam.employee_id == employee_id,
                EmployeeTeam.team == team,
                EmployeeTeam.left_at.is_(None),
            )
            .first()
        )
        if target is None:
            raise ValueError(f"Employee {employee_id} not in team {team!r}")
        self.db.query(EmployeeTeam).filter(
            EmployeeTeam.employee_id == employee_id,
            EmployeeTeam.left_at.is_(None),
        ).update({EmployeeTeam.is_primary: False}, synchronize_session="fetch")
        target.is_primary = True
        self.db.flush()
        self._recompute_legacy_team(employee_id)
        self.db.commit()

    def set_joined_at(self, employee_id: str, team: str, joined_at: date | None) -> EmployeeTeam:
        """Установить дату вступления сотрудника в команду (последний период)."""
        row = (
            self.db.query(EmployeeTeam)
            .filter_by(employee_id=employee_id, team=team)
            .order_by(EmployeeTeam.joined_at.desc().nullslast())
            .first()
        )
        if row is None:
            raise ValueError(f"Membership {employee_id}/{team} not found")
        if joined_at and row.left_at and row.left_at < joined_at:
            raise ValueError("Дата выбытия раньше даты вступления")
        self._assert_no_overlap(
            employee_id, team, joined_at, row.left_at, exclude_id=row.id
        )
        row.joined_at = joined_at
        self.db.flush()
        self._recompute_legacy_team(employee_id)
        self.db.commit()
        self.db.refresh(row)
        return row

    def set_left_at(
        self, employee_id: str, team: str, left_at: date | None
    ) -> EmployeeTeam:
        """Установить дату выбытия из команды (первый день вне команды).

        Правит последний по времени период указанной команды.
        """
        row = (
            self.db.query(EmployeeTeam)
            .filter(
                EmployeeTeam.employee_id == employee_id,
                EmployeeTeam.team == team,
            )
            .order_by(EmployeeTeam.joined_at.desc().nullslast())
            .first()
        )
        if row is None:
            raise ValueError(f"Membership {employee_id}/{team} not found")
        if left_at and row.joined_at and left_at < row.joined_at:
            raise ValueError("Дата выбытия раньше даты вступления")
        self._assert_no_overlap(
            employee_id, team, row.joined_at, left_at, exclude_id=row.id
        )
        row.left_at = left_at
        self.db.flush()
        self._recompute_legacy_team(employee_id)
        self.db.commit()
        self.db.refresh(row)
        return row

    def transfer(
        self, employee_id: str, *, from_team: str, to_team: str, on: date
    ) -> EmployeeTeam:
        """Перевести сотрудника в другую команду одним шагом.

        Закрывает открытый период в ``from_team`` датой ``on``, открывает
        период в ``to_team`` с той же даты. Признак основной переносится,
        если старое участие было основным. Без дыр и нахлёстов.
        """
        old = (
            self.db.query(EmployeeTeam)
            .filter(
                EmployeeTeam.employee_id == employee_id,
                EmployeeTeam.team == from_team,
                EmployeeTeam.left_at.is_(None),
            )
            .first()
        )
        if old is None:
            raise ValueError(f"Открытое участие в команде {from_team!r} не найдено")
        if old.joined_at and on < old.joined_at:
            raise ValueError("Дата перевода раньше даты вступления")

        was_primary = old.is_primary
        old.left_at = on
        old.is_primary = False
        self.db.flush()

        self._assert_no_overlap(employee_id, to_team, on, None)
        new = EmployeeTeam(
            employee_id=employee_id,
            team=to_team,
            is_primary=was_primary,
            joined_at=on,
        )
        self.db.add(new)
        self.db.flush()
        self._recompute_legacy_team(employee_id)
        self.db.commit()
        self.db.refresh(new)
        return new

    def replace_teams(
        self,
        employee_id: str,
        teams: list[str],
        primary: Optional[str] = None,
    ) -> list[EmployeeTeam]:
        """Заменить набор ТЕКУЩИХ команд. Закрытые периоды — история, не трогаются.

        Если primary указан и входит в teams — делает его основным, иначе
        первую команду списка. Пустой список закрывает всё текущее участие.
        """
        self.db.query(EmployeeTeam).filter(
            EmployeeTeam.employee_id == employee_id,
            EmployeeTeam.left_at.is_(None),
        ).delete(synchronize_session=False)
        self.db.flush()
        chosen_primary = primary if primary in teams else (teams[0] if teams else None)
        for t in teams:
            self.db.add(EmployeeTeam(
                employee_id=employee_id,
                team=t,
                is_primary=(t == chosen_primary),
            ))
        self.db.flush()
        self._recompute_legacy_team(employee_id)
        self.db.commit()
        return self.list_teams(employee_id)
