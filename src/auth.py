"""
AIMuse — accounts (signup / login / logout)
===========================================

A small JSON API, because the frontend talks to Flask with fetch():

  POST /auth/signup   {"username", "password"}  -> logged in
  POST /auth/login    {"username", "password"}  -> logged in
  POST /auth/logout
  GET  /auth/me       -> {"logged_in": true, "username": ...} or false

Logging in is OPTIONAL. Guests can still use all of AIMuse; an
account only adds likes and "AIMuse learns you". (An interviewer
opening your link should never hit a login wall.)

Passwords are hashed with werkzeug (scrypt + a random salt per
user). The login cookie is signed with SECRET_KEY.
"""

import os
import re
import secrets

from flask import Blueprint, jsonify, request
from flask_login import LoginManager, current_user, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from src.db import User, db, init_db


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