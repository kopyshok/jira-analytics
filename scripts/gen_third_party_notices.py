"""Собирает THIRD-PARTY-NOTICES.md из requirements.txt и frontend/package-lock.json.

Запуск: py -3.10 scripts/gen_third_party_notices.py
Перегенерировать при каждом изменении зависимостей (перед релизом).

ponytail: лицензии берём из метаданных пакетов, тексты лицензий не копируем —
для разрешительных лицензий достаточно указать компонент, версию и лицензию,
полный текст доступен в пакете. Если юрист попросит полные тексты — дописать сюда.
"""

from __future__ import annotations

import json
import re
from importlib.metadata import PackageNotFoundError, metadata, version
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Пакеты только для тестов/разработки — в поставку не попадают.
PY_DEV_ONLY = {"pytest", "pytest-asyncio", "respx"}

# Пакеты, не указывающие лицензию в метаданных, — берём из их файла LICENSE.
PY_LICENSE_OVERRIDES = {"torch": "BSD-3-Clause"}


def python_packages() -> list[tuple[str, str, str]]:
    """(имя, версия, лицензия) для рантайм-зависимостей backend."""
    rows = []
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        name = re.split(r"[<>=!\[;]", line, 1)[0].strip()
        if name.lower() in PY_DEV_ONLY:
            continue
        if name in PY_LICENSE_OVERRIDES:
            rows.append((name, version(name), PY_LICENSE_OVERRIDES[name]))
            continue
        try:
            md = metadata(name)
            lic = md.get("License-Expression") or md.get("License") or ""
            if not lic or len(lic) > 40:  # некоторые пакеты кладут в License весь текст
                lic = next(
                    (
                        c.split("::")[-1].strip()
                        for c in md.get_all("Classifier") or []
                        if c.startswith("License ::")
                    ),
                    "см. метаданные пакета",
                )
            rows.append((name, version(name), lic))
        except PackageNotFoundError:
            rows.append((name, "—", "пакет не установлен локально"))
    return sorted(rows)


def npm_packages() -> list[tuple[str, str, str]]:
    """(имя, версия, лицензия) для frontend-зависимостей, попадающих в сборку."""
    lock = json.loads((ROOT / "frontend/package-lock.json").read_text(encoding="utf-8"))
    rows = {}
    for path, info in (lock.get("packages") or {}).items():
        if not path.startswith("node_modules/") or info.get("dev"):
            continue
        lic = info.get("license")
        if not lic:
            continue
        name = path.rsplit("node_modules/", 1)[-1]
        rows[name] = (name, info.get("version", "—"), lic if isinstance(lic, str) else "/".join(lic))
    return sorted(rows.values())


def table(rows: list[tuple[str, str, str]]) -> str:
    head = "| Компонент | Версия | Лицензия |\n|---|---|---|\n"
    return head + "\n".join(f"| `{n}` | {v} | {lic} |" for n, v, lic in rows)


def main() -> None:
    py, npm = python_packages(), npm_packages()
    out = f"""# Компоненты третьих лиц

Продукт «Jira Analytics» использует перечисленные ниже компоненты с открытым
исходным кодом. Они распространяются на условиях собственных лицензий и остаются
собственностью своих правообладателей. Настоящий перечень приводится во
исполнение требований этих лицензий об указании авторства.

Лицензия самого продукта — см. файл [LICENSE](LICENSE).

Файл генерируется автоматически: `py -3.10 scripts/gen_third_party_notices.py`.
Инструменты разработки и тестирования в перечень не включены — в поставку они не входят.

## Серверная часть (Python), {len(py)} компонентов

{table(py)}

Языковая модель `intfloat/multilingual-e5-base`, загружаемая при работе тематического
анализа, распространяется под лицензией MIT.

## Клиентская часть (JavaScript/TypeScript), {len(npm)} компонентов

{table(npm)}
"""
    (ROOT / "THIRD-PARTY-NOTICES.md").write_text(out, encoding="utf-8")
    print(f"THIRD-PARTY-NOTICES.md: {len(py)} python + {len(npm)} npm")


if __name__ == "__main__":
    main()
