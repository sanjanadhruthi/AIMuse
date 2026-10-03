"""Accounts and likes: signup, login, logout, ❤️ — and that guests still work."""

import pytest

import app as aimuse
from src.accounts import User, db


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
    from src.accounts import database_url
    monkeypatch.setenv("DATABASE_URL", given)
    assert database_url() == "postgresql+psycopg2://u:p@host/db?sslmode=require"


def test_no_database_url_means_local_sqlite(monkeypatch):
    from src.accounts import database_url
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert database_url().startswith("sqlite:///")


# ------------------------------------------------ phones get fresh files

def test_static_urls_carry_a_version_so_phones_refetch():
    with aimuse.app.test_request_context():
        url = aimuse.url_for("static", filename="style.css")
    assert "?v=" in url


# ------------------------------------------------ the popup is on the page

def test_home_page_has_the_account_button_and_popup(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="account-toggle"' in html
    assert 'id="auth-dialog"' in html
    assert "account.js?v=" in html


# ------------------------------------------------ likes ❤️

def login(client, username="xiaoxiao"):
    client.post("/auth/signup", json={"username": username, "password": "moonlight123"})


SONG = {"videoId": "dQw4w9WgXcQ", "title": "Husn", "artist": "Anuv Jain",
        "mood": "sad", "language": "hindi"}


def test_guests_cannot_like(client):
    assert client.post("/likes", json=SONG).status_code == 401
    assert client.get("/likes").status_code == 401


def test_like_list_unlike(client):
    login(client)
    assert client.post("/likes", json=SONG).status_code == 201

    liked = client.get("/likes").get_json()["likes"]
    assert [(s["videoId"], s["mood"], s["language"]) for s in liked] == [("dQw4w9WgXcQ", "sad", "hindi")]

    assert client.delete("/likes/dQw4w9WgXcQ").status_code == 200
    assert client.get("/likes").get_json()["likes"] == []


def test_liking_twice_keeps_one_row(client):
    login(client)
    client.post("/likes", json=SONG)
    assert client.post("/likes", json=SONG).status_code == 200
    assert len(client.get("/likes").get_json()["likes"]) == 1


@pytest.mark.parametrize("bad_id", ["", "short", "../../etc", "a" * 12, "<script>abc"])
def test_bad_video_ids_are_rejected(client, bad_id):
    login(client)
    assert client.post("/likes", json={**SONG, "videoId": bad_id}).status_code == 400


def test_unknown_mood_and_language_are_cleaned(client):
    login(client)
    client.post("/likes", json={**SONG, "mood": "evil", "language": "klingon"})
    like = client.get("/likes").get_json()["likes"][0]
    assert like["mood"] == "neutral" and like["language"] == ""


def test_likes_are_private(client):
    login(client, "xiaoxiao")
    client.post("/likes", json=SONG)
    client.post("/auth/logout")
    login(client, "someone_else")
    assert client.get("/likes").get_json()["likes"] == []