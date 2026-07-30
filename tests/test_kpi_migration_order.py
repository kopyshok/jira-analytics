"""BLOCKER 3 ревью Фазы 4: порядок миграций KPI на чистой базе.

`seed_defaults()` (миграция `k07a_kpi_seed_defaults`) создаёт профиль через
ORM-модель `KpiProfile`, у которой объявлена колонка `is_default`. Колонку
добавляет миграция `k08a_kpi_profile_is_default` — она обязана применяться
РАНЬШЕ сида, иначе на чистой базе `alembic upgrade head` падает с
«no such column: kpi_profiles.is_default» (файлы называются по номеру
в имени, а не по порядку выполнения — порядок задаёт цепочка down_revision).
"""
from alembic.config import Config
from alembic.script import ScriptDirectory


def _revision_order() -> list[str]:
    """Порядок применения миграций от base к head, как его видит Alembic."""
    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    return [rev.revision for rev in script.walk_revisions(base="base", head="head")][::-1]


def test_profile_is_default_column_precedes_seed():
    order = _revision_order()
    assert order.index("k08a_kpi_profile_is_default") < order.index("k07a_kpi_seed_defaults")
