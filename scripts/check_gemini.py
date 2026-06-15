"""Проверка доступа к Gemini: внешний IP (страна) + тестовый запрос к API.

Запуск:  py -3.10 scripts\check_gemini.py

Читает ключ/модель Gemini из локальной базы, делает один запрос «hi».
Ничего не пишет и не меняет.
"""
import socket
import sqlite3

import httpx

DB = "data/jira_analytics.db"


def _setting(cur, key: str) -> str | None:
    row = cur.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def main() -> None:
    cur = sqlite3.connect(DB)
    key = _setting(cur, "llm_gemini_api_key")
    model = _setting(cur, "llm_gemini_model") or "gemini-2.0-flash"
    if not key:
        print("Ключ Gemini в базе не найден (Настройки -> ИИ).")
        return

    cl = httpx.Client(timeout=20)

    try:
        country = cl.get("https://ipinfo.io/json").json().get("country")
    except Exception as e:  # noqa: BLE001
        country = f"(не определить: {e})"
    print(f"Внешний IP -> страна: {country}   (нужно NL)")

    try:
        ip = socket.gethostbyname("generativelanguage.googleapis.com")
        print(f"googleapis резолвится в: {ip}")
    except Exception as e:  # noqa: BLE001
        print(f"DNS googleapis: ошибка {e}")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={key}"
    )
    body = {"contents": [{"parts": [{"text": "hi"}]}]}
    try:
        r = cl.post(url, json=body)
        head = r.text[:120].replace("\n", " ")
        print(f"Gemini ответ: {r.status_code}   (нужно 200)")
        if r.status_code != 200:
            print(f"  детали: {head}")
        else:
            print("  OK — Gemini доступен.")
    except Exception as e:  # noqa: BLE001
        print(f"Gemini запрос: ошибка {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
