import base64
import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request


SESSION_COOKIE = "autotorrent_session"
SESSION_TTL_SECONDS = 8 * 60 * 60
PASSWORD_HASH_ENV = "AUTOTORRENT_PASSWORD_HASH"
SESSION_SECRET_ENV = "AUTOTORRENT_SESSION_SECRET"
_login_attempts: dict[str, deque[float]] = defaultdict(deque)
_attempts_lock = Lock()


def _setting(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be configured")
    return value


def _password_matches(password: str) -> bool:
    encoded = _setting(PASSWORD_HASH_ENV)
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded.split("$", 3)
        iterations = int(iterations_text)
        decode = lambda value: base64.urlsafe_b64decode(
            value.encode() + b"=" * (-len(value) % 4)
        )
        salt = decode(salt_text)
        expected = decode(digest_text)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            f"{PASSWORD_HASH_ENV} must use pbkdf2_sha256$iterations$salt$digest format"
        ) from exc
    if algorithm != "pbkdf2_sha256" or iterations < 100_000:
        raise RuntimeError(f"{PASSWORD_HASH_ENV} uses an unsupported password hash")
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _sign(payload: str) -> str:
    secret = _setting(SESSION_SECRET_ENV).encode()
    digest = hmac.new(secret, payload.encode(), hashlib.sha256).digest()
    return f"{payload}.{base64.urlsafe_b64encode(digest).decode().rstrip('=')}"


def _valid_session(value: str | None) -> bool:
    if not value or "." not in value:
        return False
    payload, signature = value.rsplit(".", 1)
    if not hmac.compare_digest(_sign(payload).rsplit(".", 1)[1], signature):
        return False
    try:
        issued = int(payload)
    except ValueError:
        return False
    return 0 < time.time() - issued < SESSION_TTL_SECONDS


def new_session() -> str:
    return _sign(str(int(time.time())))


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def login_allowed(request: Request) -> bool:
    now = time.time()
    key = _client_key(request)
    with _attempts_lock:
        attempts = _login_attempts[key]
        while attempts and now - attempts[0] > 900:
            attempts.popleft()
        return len(attempts) < 10


def record_login_attempt(request: Request) -> None:
    with _attempts_lock:
        _login_attempts[_client_key(request)].append(time.time())


def is_authenticated(request: Request) -> bool:
    return _valid_session(request.cookies.get(SESSION_COOKIE))


def same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return False
    return origin == f"{request.url.scheme}://{request.headers.get('host', '')}"


def password_matches(password: str) -> bool:
    return _password_matches(password)
