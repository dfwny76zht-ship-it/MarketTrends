import hashlib
import secrets
import threading
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from . import config
from .db import pool

COOKIE = "mt_session"
SESSION_DAYS = 30
MAX_FAILS = 5
LOCK_SECONDS = 15 * 60

hasher = PasswordHasher()
_DUMMY_HASH = hasher.hash(secrets.token_hex(16))
_fails: dict[str, dict] = {}
_fails_lock = threading.Lock()

router = APIRouter(prefix="/api")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def _is_locked(ip: str) -> bool:
    with _fails_lock:
        entry = _fails.get(ip)
        return bool(entry and entry["until"] > time.time())


def _record_fail(ip: str) -> None:
    with _fails_lock:
        entry = _fails.setdefault(ip, {"count": 0, "until": 0.0})
        entry["count"] += 1
        if entry["count"] >= MAX_FAILS:
            entry["count"] = 0
            entry["until"] = time.time() + LOCK_SECONDS


def current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Not logged in")
    with pool.connection() as conn:
        user = conn.execute(
            "SELECT u.id, u.username FROM sessions s JOIN users u ON u.id = s.user_id"
            " WHERE s.token_hash = %s AND s.expires_at > now()",
            (_token_hash(token),),
        ).fetchone()
    if not user:
        raise HTTPException(401, "Not logged in")
    return user


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response):
    ip = _client_ip(request)
    if _is_locked(ip):
        raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
    with pool.connection() as conn:
        user = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = %s",
            (body.username.strip(),),
        ).fetchone()
        ok = False
        try:
            ok = hasher.verify(user["password_hash"] if user else _DUMMY_HASH, body.password)
        except (VerificationError, InvalidHashError):
            ok = False
        if not (ok and user):
            _record_fail(ip)
            raise HTTPException(401, "Wrong username or password.")
        with _fails_lock:
            _fails.pop(ip, None)
        token = secrets.token_urlsafe(32)
        conn.execute("DELETE FROM sessions WHERE expires_at < now()")
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at)"
            " VALUES (%s, %s, now() + make_interval(days => %s))",
            (_token_hash(token), user["id"], SESSION_DAYS),
        )
    response.set_cookie(
        COOKIE,
        token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite="strict",
        path="/",
    )
    return {"username": user["username"]}


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        with pool.connection() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = %s", (_token_hash(token),))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    user = current_user(request)
    return {"username": user["username"]}
