from fastapi.testclient import TestClient

from job_finder.api import create_app
from job_finder.settings import AppSettings


def auth_client(tmp_path) -> TestClient:
    settings = AppSettings(
        companies_path=tmp_path / "companies.json",
        output_directory=tmp_path / "output",
        resumes_directory=tmp_path / "resumes",
        auth_enabled=True,
    )
    settings.companies_path.write_text(
        '[{"id":"acme","name":"Acme","website_url":"https://acme.example"}]',
        encoding="utf-8",
    )
    return TestClient(create_app(settings))


def test_registration_claims_local_data_and_uses_http_only_session(tmp_path) -> None:
    client = auth_client(tmp_path)

    assert client.get("/api/health").status_code == 200
    assert client.get("/api/companies").status_code == 401
    registered = client.post("/api/auth/register", json={
        "email": "David@Example.com",
        "password": "correct horse battery staple",
        "display_name": "David",
    })

    assert registered.status_code == 201
    assert registered.json()["email"] == "david@example.com"
    assert registered.json()["id"] == "local"
    cookie = registered.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert [item["id"] for item in client.get("/api/companies").json()] == ["acme"]
    assert client.get("/api/auth/me").json()["display_name"] == "David"

    restarted = TestClient(create_app(client.app.state.settings))
    restarted.cookies.set("job_finder_session", client.cookies.get("job_finder_session"))
    assert restarted.get("/api/auth/me").json()["email"] == "david@example.com"

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={
        "email": "david@example.com", "password": "wrong password",
    }).status_code == 401
    assert client.post("/api/auth/login", json={
        "email": "david@example.com", "password": "correct horse battery staple",
    }).status_code == 200


def test_users_only_see_their_own_companies(tmp_path) -> None:
    first = auth_client(tmp_path)
    first.post("/api/auth/register", json={
        "email": "owner@example.com",
        "password": "owner password 123",
        "display_name": "Owner",
    })
    first.post("/api/auth/logout")

    second = TestClient(first.app)
    registered = second.post("/api/auth/register", json={
        "email": "second@example.com",
        "password": "second password 123",
        "display_name": "Second",
    })

    assert registered.status_code == 201
    assert registered.json()["id"] != "local"
    assert second.get("/api/companies").json() == []
    assert second.post("/api/auth/logout").status_code == 204
    assert second.post("/api/auth/login", json={
        "email": "owner@example.com",
        "password": "owner password 123",
    }).status_code == 200
    assert [item["id"] for item in second.get("/api/companies").json()] == ["acme"]
