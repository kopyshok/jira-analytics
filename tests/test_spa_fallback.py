from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import SPAStaticFiles


def _make_client(tmp_path) -> TestClient:
    static_dir = tmp_path / "static"
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<html><body>SPA shell</body></html>", encoding="utf-8")
    (assets_dir / "app.js").write_text("console.log('ok')", encoding="utf-8")

    app = FastAPI()
    app.mount("/", SPAStaticFiles(directory=static_dir, html=True), name="spa")
    return TestClient(app)


def test_spa_route_returns_index_html(tmp_path):
    client = _make_client(tmp_path)

    response = client.get("/login")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "SPA shell" in response.text


def test_missing_asset_stays_404(tmp_path):
    client = _make_client(tmp_path)

    response = client.get("/assets/missing.js")

    assert response.status_code == 404


def test_spa_route_with_dot_returns_index_html(tmp_path):
    client = _make_client(tmp_path)

    response = client.get("/users/john.smith")

    assert response.status_code == 200
    assert "SPA shell" in response.text


def test_missing_api_route_with_json_accept_stays_404(tmp_path):
    client = _make_client(tmp_path)

    response = client.get("/api/v1/missing", headers={"accept": "application/json"})

    assert response.status_code == 404
