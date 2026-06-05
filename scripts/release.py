"""Полуавтоматический релиз: анализ Conventional Commits → предложение версии → подтверждение.

Использование:
    python scripts/release.py              # интерактив: предложит версию и спросит подтверждение
    python scripts/release.py --yes        # без вопросов, использовать автопредложение
    python scripts/release.py --version vX.Y.Z   # вручную задать версию

Логика выбора bump:
    - есть `feat!:`/`fix!:`/`BREAKING CHANGE` в теле коммита   → major
    - есть `feat(...)`/`feat:`                                  → minor
    - есть `fix(...)`/`fix:`                                    → patch
    - только chore/docs/refactor                                → patch (по умолчанию)

Первый релиз (нет предыдущего тэга): по умолчанию `v1.0.0`.

После подтверждения вызывает `make release VERSION=...`, который:
    - бампит `app/config.py` и `frontend/package.json`
    - делает commit `chore(release): vX.Y.Z`
    - ставит annotated tag `vX.Y.Z`
    - НЕ пушит (push отдельной командой)
"""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Windows: console cp1251 ломает вывод кириллических commit-subject. Принудительно UTF-8.
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def run(cmd: list[str], *, check: bool = True, capture: bool = True) -> str:
    """Запустить команду, вернуть stdout (или пустую строку при ошибке если не check).

    encoding=utf-8 + errors=replace — иначе на Windows валится cp1251 при кириллице.
    """
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and result.returncode != 0:
        sys.stderr.write(result.stderr or "")
        raise SystemExit(result.returncode)
    return (result.stdout or "").strip()


def last_tag() -> str | None:
    """Последний SemVer-тэг в истории, либо None если их нет."""
    out = run(
        ["git", "describe", "--tags", "--abbrev=0", "--match", "v*.*.*"],
        check=False,
    )
    return out or None


def commits_since(tag: str | None) -> list[str]:
    """Subject-строки коммитов с момента tag (или вся история если tag=None)."""
    rng = f"{tag}..HEAD" if tag else "HEAD"
    out = run(["git", "log", "--pretty=format:%s", rng], check=False)
    return [line for line in out.splitlines() if line.strip()]


BREAKING_RE = re.compile(r"^[a-z]+(\([^)]+\))?!:")
FEAT_RE = re.compile(r"^feat(\([^)]+\))?:")
FIX_RE = re.compile(r"^fix(\([^)]+\))?:")


def classify(commits: list[str]) -> tuple[str, dict[str, int]]:
    """Определить тип bump + посчитать категории коммитов."""
    counts = {"breaking": 0, "feat": 0, "fix": 0, "other": 0}
    for c in commits:
        if BREAKING_RE.match(c) or "BREAKING CHANGE" in c:
            counts["breaking"] += 1
        elif FEAT_RE.match(c):
            counts["feat"] += 1
        elif FIX_RE.match(c):
            counts["fix"] += 1
        else:
            counts["other"] += 1
    if counts["breaking"]:
        return "major", counts
    if counts["feat"]:
        return "minor", counts
    return "patch", counts


def bump_version(version: str, kind: str) -> str:
    """SemVer bump. version='1.2.3', kind='major'|'minor'|'patch'."""
    parts = version.lstrip("v").split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise SystemExit(f"Невалидная предыдущая версия: {version!r}")
    major, minor, patch = map(int, parts)
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def ensure_clean_tree() -> None:
    """Дальше работаем только с чистым working tree."""
    dirty = run(["git", "status", "--porcelain"], check=False)
    if dirty:
        sys.stderr.write(
            "Рабочее дерево не чистое:\n" + dirty + "\nЗакоммить или отложи.\n"
        )
        raise SystemExit(1)


def ensure_docker_build() -> None:
    """Прогнать полную docker сборку. Ловит TS-ошибки и build-фейлы ДО тэга.

    Раньше: TS-ошибка в фронте проскочила CI (incremental cache) → упала на проде.
    Теперь: каждый релиз гоняет `docker build` локально как пред-тэговый гейт.
    Пропустить можно `--skip-docker-build` для исключительных случаев.
    """
    print("\n[release] docker build (pre-tag gate)...")
    result = subprocess.run(
        ["docker", "build", "--build-arg", "VITE_API_BASE_URL=/api/v1",
         "-t", "jira-analytics:pre-release-check", "."],
        cwd=REPO_ROOT,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(
            "\n[release] docker build УПАЛ. Тэг не создан.\n"
            "Исправь ошибку и перезапусти. "
            "Чтобы пропустить (на свой риск) — --skip-docker-build.\n"
        )
        raise SystemExit(result.returncode)
    print("[release] docker build OK.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Semi-automatic release tagger")
    parser.add_argument(
        "--yes", action="store_true", help="подтвердить автопредложение без вопроса"
    )
    parser.add_argument(
        "--version",
        help="явная версия (с префиксом v или без), пропускает анализ",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="показать предложение, ничего не менять",
    )
    parser.add_argument(
        "--skip-docker-build",
        action="store_true",
        help="пропустить пред-тэговую docker сборку (на свой риск)",
    )
    parser.add_argument(
        "--skip-notes-check",
        action="store_true",
        help="разрешить релиз без файла release_notes/<version>.json (на свой риск)",
    )
    args = parser.parse_args()

    ensure_clean_tree()

    prev = last_tag()
    commits = commits_since(prev)

    if prev:
        prev_ver = prev.lstrip("v")
        kind, counts = classify(commits)
        proposed = bump_version(prev_ver, kind)
        print(f"Предыдущий релиз: {prev}")
        print(f"Коммитов с тех пор: {len(commits)}")
        print(
            f"  ломающих: {counts['breaking']}, "
            f"feat: {counts['feat']}, "
            f"fix: {counts['fix']}, "
            f"прочих: {counts['other']}"
        )
        print(f"Тип bump: {kind}")
    else:
        proposed = "1.0.0"
        kind = "initial"
        print("Предыдущих релиз-тэгов нет.")
        print(f"Коммитов в истории: {len(commits)}")
        print("Тип: первый релиз")

    print(f"Предложение: v{proposed}")

    print("\nПоследние коммиты:")
    for c in commits[:15]:
        print(f"  {c}")
    if len(commits) > 15:
        print(f"  ... ещё {len(commits) - 15}")

    if args.dry_run:
        print("\n[--dry-run] остановка без изменений.")
        return

    if args.version:
        target = args.version if args.version.startswith("v") else f"v{args.version}"
    elif args.yes:
        target = f"v{proposed}"
    else:
        ans = input(
            f"\nВыпустить v{proposed}? [Enter=да / n=отмена / vX.Y.Z=другая]: "
        ).strip()
        if ans == "" or ans.lower() in ("y", "yes", "д", "да"):
            target = f"v{proposed}"
        elif ans.lower() in ("n", "no", "н", "нет"):
            print("Отменено.")
            return
        elif re.match(r"^v?\d+\.\d+\.\d+$", ans):
            target = ans if ans.startswith("v") else f"v{ans}"
        else:
            print(f"Не понял ответ: {ans!r}. Отменено.")
            return

    # Пред-проверка: release notes должны быть либо в drafts.json (привяжем),
    # либо уже в файле release_notes/<target>.json (ретро/повторный релиз).
    drafts_file = REPO_ROOT / "release_notes" / "drafts.json"
    target_notes = REPO_ROOT / "release_notes" / f"{target}.json"
    if (
        not drafts_file.exists()
        and not target_notes.exists()
        and not args.skip_notes_check
    ):
        sys.stderr.write(
            f"\n[release] Нет release-notes для {target}.\n"
            f"  Ожидался файл: {target_notes.relative_to(REPO_ROOT)} "
            "(или черновики release_notes/drafts.json).\n"
            "  Добавь через: py -3.10 scripts/release_note.py add ...\n"
            "  Или пропусти проверку: --skip-notes-check.\n"
        )
        raise SystemExit(1)

    if not args.skip_docker_build:
        ensure_docker_build()

    # После docker-build (если упал — bind не делаем, дерево чистое).
    if drafts_file.exists():
        print(f"\nПривязка черновиков release notes к {target}...")
        bind = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "release_note.py"),
             "bind", "--version", target],
            cwd=REPO_ROOT, check=False,
        )
        if bind.returncode != 0:
            sys.stderr.write(
                "Не удалось привязать черновики. Запусти вручную: "
                f"py -3.10 scripts/release_note.py bind --version {target}\n"
            )
            raise SystemExit(bind.returncode)

    # Stage release_notes — Makefile проверяет только unstaged.
    subprocess.run(
        ["git", "add", "release_notes"], cwd=REPO_ROOT, check=False,
    )

    print(f"\nЗапуск: make release VERSION={target}")
    result = subprocess.run(
        ["make", "release", f"VERSION={target}"], cwd=REPO_ROOT, check=False
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    print(
        "\nГотово. После push релиз-заметки попадут на прод автоматически "
        "(сидер на старте контейнера прочитает release_notes/*.json)."
    )


if __name__ == "__main__":
    main()
