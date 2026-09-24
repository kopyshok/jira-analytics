"""Имя скачиваемого файла с русскими буквами не роняет выгрузку."""

from fastapi.responses import Response

from app.api.endpoints.exports import _attachment_headers


def test_cyrillic_filename_builds_response():
    headers = _attachment_headers("scenario_Q4_2026_утвержденный-план.xlsx")
    # Заголовки уходят в latin-1 — раньше здесь падал UnicodeEncodeError → 500.
    Response(content=b"x", headers=headers)
    value = headers["Content-Disposition"]
    value.encode("latin-1")
    assert "filename*=UTF-8''scenario_Q4_2026_" in value
    assert "%D1%83" in value  # «у» сохранено для браузера
