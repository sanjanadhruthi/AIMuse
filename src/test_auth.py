"""Accounts: signup, login, logout — and that guests still work."""

import pytest

import app as aimuse
from src.db import User, db


@pytest.fixture
def client():
    with aimuse.app.app_context():
        db.drop_all()
        db.create_all()
    return aimuse.app.test_client()


def signup(client, username="xiaoxiao", password="moonlight123"):
    return client.post("/auth/signup", json={"username": username, "password": password})


def test_signup_logs_you_in(client):
    response = signup(client)
    assert response.status_code == 201
    assert client.get("/auth/me").get_json()["username"] == "xiaoxiao"


def test_password_is_never_stored_as_plain_text(client):
    signup(client)
    with aimuse.app.app_context():
        user = User.query.filter_by(username="xiaoxiao").one()
        assert "moonlight123" not in user.password_hash


def test_username_is_case_insensitive(client):
    signup(client, username="XiaoXiao")
    assert signup(client, username="xiaoxiao").status_code == 409


@pytest.mark.parametrize("username", ["ab", "has space", "<script>", "a" * 31])
def test_bad_usernames_are_rejected(client, username):
    assert signup(client, username=username).status_code == 400


def test_short_password_is_rejected(client):
    assert signup(client, password="short").status_code == 400


def test_login_logout_cycle(client):
    signup(client)
    client.post("/auth/logout")
    assert client.get("/auth/me").get_json()["logged_in"] is False

    response = client.post("/auth/login", json={"username": "xiaoxiao", "password": "moonlight123"})
    assert response.status_code == 200
    assert client.get("/auth/me").get_json()["logged_in"] is True


def test_wrong_password_and_unknown_user_look_the_same(client):
    signup(client)
    client.post("/auth/logout")
    wrong = client.post("/auth/login", json={"username": "xiaoxiao", "password": "nope-nope-nope"})
    ghost = client.post("/auth/login", json={"username": "nobody", "password": "nope-nope-nope"})
    assert wrong.status_code == ghost.status_code == 401
    assert wrong.get_json()["error"] == ghost.get_json()["error"]


def test_guests_can_still_use_aimuse(client):
    response = client.post("/analyze", json={"text": "aaj bahut khush hoon"})
    assert response.status_code == 200
    assert response.get_json()["emotion"] == "happy"


# ------------------------------------------------ database address

@pytest.mark.parametrize("given", [
    "postgresql://u:p@host/db?sslmode=require",
    "postgres://u:p@host/db?sslmode=require",
])
def test_postgres_urls_use_the_installed_driver(monkeypatch, given):
    from src.db import database_url
    monkeypatch.setenv("DATABASE_URL", given)
    assert database_url() == "postgresql+psycopg2://u:p@host/db?sslmode=require"


def test_no_database_url_means_local_sqlite(monkeypatch):
    from src.db import database_url
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert database_url().startswith("sqlite:///")