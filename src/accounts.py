"""
AIMuse — accounts: database, login / signup, likes
==================================================

Everything that needs a user account lives in this one file:

  1. DATABASE   tables for users, likes and mood history
  2. ACCOUNTS   POST /auth/signup  /auth/login  /auth/logout,  GET /auth/me
  3. LIKES      GET /likes,  POST /likes,  DELETE /likes/<videoId>

Where the data lives:
  * On Render: a free hosted Postgres (Neon), from the DATABASE_URL
    environment variable. Render's own disk is wiped on every
    restart, so it can NOT be a local file there.
  * On your laptop without DATABASE_URL: instance/aimuse_local.db
  * In tests: an in-memory database (conftest.py)

Logging in is OPTIONAL — guests can use all of AIMuse; an account
adds likes and "AIMuse learns you". app.py only calls init_auth(app).
"""

import os
import re
import secrets
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_login import (
    LoginManager, UserMixin, current_user, login_required, login_user, logout_user
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


# =========================================================
# 1. DATABASE
# =========================================================

db = SQLAlchemy()


def _now():
    return datetime.now(timezone.utc)


def database_url():
    """DATABASE_URL, cleaned up for SQLAlchemy, or a local SQLite file."""

    url = os.environ.get("DATABASE_URL", "").strip()

    if not url:
        return "sqlite:///aimuse_local.db"

    # Name the driver explicitly. A bare "postgresql://" lets
    # SQLAlchemy pick one, and SQLAlchemy 2.1 picks "psycopg" (v3),
    # but requirements.txt installs psycopg2. "postgres://" is the
    # old spelling some hosts still hand out.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg2://" + url[len(prefix):]

    return url


class User(UserMixin, db.Model):

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    # stored lower-case, so "XiaoXiao" and "xiaoxiao" are one account
    username = db.Column(db.String(30), unique=True, nullable=False, index=True)

    # never the password itself — only a salted scrypt hash
    password_hash = db.Column(db.String(255), nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False)

    likes = db.relationship("Like", backref="user", lazy="dynamic",
                            cascade="all, delete-orphan")

    moods = db.relationship("MoodEntry", backref="user", lazy="dynamic",
                            cascade="all, delete-orphan")


class Like(db.Model):
    """A song a user hearted. (Phase 3)"""

    __tablename__ = "likes"

    __table_args__ = (
        db.UniqueConstraint("user_id", "video_id", name="one_like_per_song"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    video_id = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(200), nullable=False, default="")
    artist = db.Column(db.String(200), nullable=False, default="")

    # the mood / language of the playlist it was liked from —
    # this is what "learning" will count later
    mood = db.Column(db.String(20), nullable=False, default="neutral")
    language = db.Column(db.String(20), nullable=False, default="")

    created_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False)


class MoodEntry(db.Model):
    """One playlist request: which mood, which mode, which language. (Phase 4)"""

    __tablename__ = "mood_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    emotion = db.Column(db.String(20), nullable=False)
    mode = db.Column(db.String(10), nullable=False, default="match")
    language = db.Column(db.String(20), nullable=False, default="")

    created_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False)


def init_db(app):

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url()

    # Free Postgres hosts close idle connections; pre_ping checks a
    # connection before using it instead of crashing on a dead one.
    app.config.setdefault("SQLALCHEMY_ENGINE_OPTIONS", {"pool_pre_ping": True})

    db.init_app(app)

    with app.app_context():
        db.create_all()


# =========================================================
# 2. ACCOUNTS  (signup / login / logout)
# =========================================================

auth = Blueprint("auth", __name__, url_prefix="/auth")

login_manager = LoginManager()

USERNAME_RULE = re.compile(r"^[a-z0-9_]{3,30}$")
MIN_PASSWORD = 8
MAX_PASSWORD = 128

# Same message for "no such user" and "wrong password", so nobody
# can use the login form to find out which usernames exist.
BAD_LOGIN = "Wrong username or password."


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@login_manager.unauthorized_handler
def unauthorized():
    return jsonify({"success": False, "error": "Please log in first."}), 401


def _credentials():
    """(username, password) from the JSON body, cleaned."""

    data = request.get_json(silent=True) or {}

    username = str(data.get("username", "")).strip().lower()
    password = str(data.get("password", ""))

    return username, password


def _fail(message, status=400):
    return jsonify({"success": False, "error": message}), status


def _me():
    return {"success": True, "logged_in": True, "username": current_user.username}


@auth.post("/signup")
def signup():

    username, password = _credentials()

    if not USERNAME_RULE.match(username):
        return _fail("Username: 3–30 characters, only letters, numbers and _.")

    if not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        return _fail(f"Password must be at least {MIN_PASSWORD} characters.")

    if User.query.filter_by(username=username).first():
        return _fail("That username is taken.", 409)

    user = User(username=username, password_hash=generate_password_hash(password))

    db.session.add(user)
    db.session.commit()

    login_user(user, remember=True)

    return jsonify(_me()), 201


@auth.post("/login")
def login():

    username, password = _credentials()

    user = User.query.filter_by(username=username).first()

    if not user or not check_password_hash(user.password_hash, password):
        return _fail(BAD_LOGIN, 401)

    login_user(user, remember=True)

    return jsonify(_me())


@auth.post("/logout")
def logout():

    logout_user()

    return jsonify({"success": True, "logged_in": False})


@auth.get("/me")
def me():

    if current_user.is_authenticated:
        return jsonify(_me())

    return jsonify({"success": True, "logged_in": False})


# =========================================================
# 3. LIKES ❤️
# =========================================================

likes = Blueprint("likes", __name__, url_prefix="/likes")

# YouTube video ids are always 11 of these characters.
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

MOODS = {"happy", "sad", "calm", "angry", "romantic", "energetic", "neutral"}

LANGUAGES = {"telugu", "hindi", "english", ""}


def _clean(value, limit):
    return str(value or "").strip()[:limit]


def _as_dict(like):
    return {
        "videoId": like.video_id,
        "title": like.title,
        "artist": like.artist,
        "mood": like.mood,
        "language": like.language,
        "likedAt": like.created_at.isoformat() if like.created_at else None,
    }


@likes.get("")
@login_required
def list_likes():

    rows = (current_user.likes
            .order_by(Like.created_at.desc(), Like.id.desc())
            .limit(500)
            .all())

    return jsonify({"success": True, "likes": [_as_dict(row) for row in rows]})


@likes.post("")
@login_required
def add_like():

    data = request.get_json(silent=True) or {}

    video_id = _clean(data.get("videoId"), 20)

    if not VIDEO_ID.match(video_id):
        return jsonify({"success": False, "error": "Not a valid song."}), 400

    existing = current_user.likes.filter_by(video_id=video_id).first()

    if existing:                       # liking twice is fine, not an error
        return jsonify({"success": True, "like": _as_dict(existing)})

    mood = _clean(data.get("mood"), 20).lower()
    language = _clean(data.get("language"), 20).lower()

    like = Like(
        user_id=current_user.id,
        video_id=video_id,
        title=_clean(data.get("title"), 200) or "Untitled",
        artist=_clean(data.get("artist"), 200),
        mood=mood if mood in MOODS else "neutral",
        language=language if language in LANGUAGES else "",
    )

    db.session.add(like)
    db.session.commit()

    return jsonify({"success": True, "like": _as_dict(like)}), 201


@likes.delete("/<video_id>")
@login_required
def remove_like(video_id):

    like = current_user.likes.filter_by(video_id=video_id).first()

    if like:
        db.session.delete(like)
        db.session.commit()

    return jsonify({"success": True})


# =========================================================
# SETUP — app.py calls this once
# =========================================================

def init_auth(app):
    """Call once from app.py, right after `app = Flask(...)`."""

    secret = os.environ.get("SECRET_KEY")

    if not secret:
        # Fine on your laptop (you just get logged out on restart).
        # On Render, ALWAYS set SECRET_KEY, or everyone is logged out
        # every time the server wakes up.
        print("WARNING: SECRET_KEY not set — using a temporary one.")
        secret = secrets.token_hex(32)

    app.config["SECRET_KEY"] = secret

    on_render = bool(os.environ.get("RENDER"))

    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,       # JavaScript can't read the cookie
        SESSION_COOKIE_SAMESITE="Lax",      # other sites can't send it for you
        SESSION_COOKIE_SECURE=on_render,    # https only on the live site
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_SECURE=on_render,
    )

    init_db(app)

    login_manager.init_app(app)

    app.register_blueprint(auth)

    app.register_blueprint(likes)