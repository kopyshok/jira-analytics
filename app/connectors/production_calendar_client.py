"""Клиент производственного календаря РФ (xmlcalendar.ru).

Тянет JSON по году, парсит маркеры дней в плоский список ``CalendarDayRaw``.

Формат источника (наблюдаемый на /data/ru/<year>/calendar.json):

    {
      "year": 2026,
      "months": [
        {"month": 1, "days": "1,2,3,4,5,6,7,8,9+,10,11,17,18,24,25,31"},
        ...
      ],
      "transitions": [{"from": "01.03", "to": "01.09"}, ...]
    }

Все перечисленные в ``days`` числа — «особые» дни относительно обычной рабочей
недели. Обычные будни и субботы/воскресенья без переноса в ответе отсутствуют —
календарь их достраивает на стороне потребителя (см. ``ProductionCalendarService``).

Семантика суффиксов:

* без суффикса — нерабочий праздничный день (``kind="holiday"``);
* ``+`` — перенесённый выходной (``kind="weekend"``), нерабочий;
* ``*`` — сокращённый предпраздничный рабочий день (``kind="preholiday"``,
  ``is_workday=True``);
* ``'`` — исторический маркер сокращённого дня, интерпретируется как
  ``preholiday`` для обратной совместимости.

Парсер терпим к двум верхнеуровневым схемам:

* плоская (реальная на xmlcalendar.ru) — ``{"year": Y, "months": [...]}``;
* обёрнутая (приведена в плане/архивных источниках) — ``{"years": [{"year": Y, "months": [...]}, ...]}``.
"""

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

import httpx


XMLCALENDAR_URL = "https://xmlcalendar.ru/data/ru/{year}/calendar.json"


@dataclass
class CalendarDayRaw:
    """Один особый день, возвращённый источником."""

    date: date
    is_workday: bool
    kind: str  # "holiday" | "weekend" | "preholiday"
    note: Optional[str] = None


class ProductionCalendarClient:
    """HTTP-клиент к xmlcalendar.ru."""

    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout

    async def fetch_year(self, year: int) -> list[CalendarDayRaw]:
        """Запросить календарь на указанный год и вернуть распарсенный список."""
        url = XMLCALENDAR_URL.format(year=year)
        async with httpx.AsyncClient(timeout=self._timeout) as http:
            resp = await http.get(url)
            resp.raise_for_status()
            payload = resp.json()
        return list(self._parse(year, payload))

    @staticmethod
    def _parse(year: int, payload: dict) -> Iterable[CalendarDayRaw]:
        """Развернуть payload в плоский список ``CalendarDayRaw``.

        Метод статический — удобно дергать из тестов без поднятия http-клиента.
        """
        block = ProductionCalendarClient._select_year_block(year, payload)
        if block is None:
            return []
        out: list[CalendarDayRaw] = []
        for month_block in block.get("months", []):
            try:
                month = int(month_block["month"])
            except (KeyError, TypeError, ValueError):
                continue
            for token in str(month_block.get("days", "")).split(","):
                token = token.strip()
                if not token:
                    continue
                if token.endswith("*"):
                    day_str = token[:-1]
                    kind, is_wd = "preholiday", True
                elif token.endswith("'"):
                    day_str = token[:-1]
                    kind, is_wd = "preholiday", True
                elif token.endswith("+"):
                    day_str = token[:-1]
                    kind, is_wd = "weekend", False
                else:
                    day_str = token
                    kind, is_wd = "holiday", False
                try:
                    day = int(day_str)
                except ValueError:
                    continue  # пропускаем мусорные токены
                d = date(year, month, day)
                # xmlcalendar не отличает обычные Сб/Вс от праздников —
                # уточняем: выпавший на выходной «holiday» считаем weekend.
                if kind == "holiday" and d.weekday() >= 5:
                    kind = "weekend"
                out.append(CalendarDayRaw(date=d, is_workday=is_wd, kind=kind))
        return out

    @staticmethod
    def _select_year_block(year: int, payload: dict) -> Optional[dict]:
        """Выбрать блок нужного года из любой из поддерживаемых схем."""
        if not isinstance(payload, dict):
            return None
        # Плоская схема: сам payload — блок года.
        if "months" in payload and int(payload.get("year", year)) == year:
            return payload
        # Обёрнутая схема: {"years": [...]}
        years = payload.get("years")
        if isinstance(years, list):
            for y in years:
                if isinstance(y, dict) and int(y.get("year", 0)) == year:
                    return y
        return None
