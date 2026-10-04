"""Плашка «в работе у K из N» мультикомандной RFA — общая для «Целевых задач»
и строк сценария (см. app/services/multi_team_progress.py)."""

from typing import List, Optional

from pydantic import BaseModel

from app.services.multi_team_progress import RowProgress, TakeStatus


class ScenarioMarkOut(BaseModel):
    """Утверждённый сценарий, в который команда включила эпик."""

    id: str
    name: str
    quarter_label: str


class TeamTakeOut(BaseModel):
    team: str
    status: TakeStatus
    scenarios: List[ScenarioMarkOut] = []


class MultiTeamProgressOut(BaseModel):
    """K из N команд RFA уже взяли работу; статус своей команды строки."""

    taken: int
    total: int
    own_team: Optional[str] = None
    own_status: Optional[TakeStatus] = None
    teams: List[TeamTakeOut]

    @classmethod
    def from_row(cls, row: Optional[RowProgress]) -> Optional["MultiTeamProgressOut"]:
        if row is None:
            return None
        return cls(
            taken=row.rfa.taken,
            total=row.rfa.total,
            own_team=row.own_team,
            own_status=row.own_status,
            teams=[
                TeamTakeOut(
                    team=t.team,
                    status=t.status,
                    scenarios=[
                        ScenarioMarkOut(id=s.id, name=s.name, quarter_label=s.label)
                        for s in t.scenarios
                    ],
                )
                for t in row.rfa.teams
            ],
        )
