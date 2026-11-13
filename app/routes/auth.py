import re
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import AfterValidator, BaseModel, Field

from app.deps import SESSION_COOKIE, CurrentUser, Db, SettingsDep, session_token
from app.ratelimit import client_ip
from app.settings import Settings
from core.spaces import AlreadyExistsError
from core.storage.users import SqliteUserRepository, User

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _email(value: str) -> str:
    value = value.strip().lower()
    if not EMAIL.match(value) or len(value) > 254:
        raise ValueError("not a valid email address")
    return value


class Credentials(BaseModel):
    email: Annotated[str, AfterValidator(_email)]
    password: str = Field(min_length=8, max_length=200)


class SignedIn(BaseModel):
    user: User
    token: str  # also set as an HttpOnly cookie; API clients can send it as a Bearer token instead


def _sign_in(response: Response, repo: SqliteUserRepository, user: User, settings: Settings) -> SignedIn:
    lifetime = timedelta(days=settings.session_days)
    token = repo.start_session(user.id, lifetime)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(lifetime.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=settings.secure_cookies,
        path="/",
    )
    return SignedIn(user=user, token=token)


def _limit_sign_in(request: Request, email: str, settings: Settings) -> None:
    limiter = request.app.state.rate_limiter
    window = 15 * 60
    limiter.check("login-email", email, settings.login_attempts_per_15_min, window)
    limiter.check("login-ip", client_ip(request, settings.trust_proxy), settings.login_attempts_per_15_min * 3, window)


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: Credentials, request: Request, response: Response, conn: Db, settings: SettingsDep) -> SignedIn:
    if not settings.allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "sign-ups are closed on this server")
    _limit_sign_in(request, body.email, settings)
    repo = SqliteUserRepository(conn)
    try:
        user = repo.create(body.email, body.password)
    except AlreadyExistsError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "an account with this email already exists") from exc
    return _sign_in(response, repo, user, settings)


@router.post("/login")
def login(body: Credentials, request: Request, response: Response, conn: Db, settings: SettingsDep) -> SignedIn:
    _limit_sign_in(request, body.email, settings)
    repo = SqliteUserRepository(conn)
    user = repo.authenticate(body.email, body.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong email or password")
    return _sign_in(response, repo, user, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, conn: Db) -> None:
    token = session_token(request)
    if token:
        SqliteUserRepository(conn).end_session(token)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me")
def me(user: CurrentUser) -> User:
    return user
