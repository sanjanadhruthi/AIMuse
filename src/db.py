"""
AIMuse — database
=================

Where accounts, likes and mood history live.

  * On Render: a free hosted Postgres (Neon). Its address comes from
    the DATABASE_URL environment variable, so nothing secret is in
    the code. Render's own disk is wiped on every restart, which is
    why this can NOT be a local file there.
  * On your laptop without DATABASE_URL: a local SQLite file
    (instance/aimuse_local.db), so you can work offline.
  * In tests: an in-memory database (set in conftest.py).

There is no migration tool, so all three tables are designed now,
even though likes and history are used in later phases.
"""

import os
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin


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