"""Authentication and first-run account setup endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from ..auth.audit import get_audit_log
from ..auth.sessions import SESSION_COOKIE_NAME, get_session_store
from ..auth.users import get_user_store
from ..schemas.models import AuthCredentials, AuthSetupRequest, SignupRequest

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _request_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _session_response(token: str, session: dict, user: dict, response: Response) -> dict:
    response.set_cookie(
        SESSION_COOKIE_NAME, token, httponly=True, samesite="lax", path="/"
    )
    return {"session": session, "user": user}


@router.get("/setup")
def setup_status():
    """Return whether the first administrator still needs to be created."""
    ready = not get_user_store().has_any_users()
    return {"setup_required": ready}


@router.post("/setup", status_code=status.HTTP_201_CREATED)
def setup(payload: AuthSetupRequest, request: Request):
    users = get_user_store()
    try:
        user = users.create_first_admin(
            payload.username, payload.password, display_name=payload.display_name
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    get_audit_log().record(
        "auth.setup", user_id=user["user_id"], resource="auth/setup", ip=_request_ip(request)
    )
    return user


def _login(payload: AuthCredentials, request: Request, response: Response):
    users = get_user_store()
    user = users.verify_credentials(payload.username, payload.password)
    if user is None:
        get_audit_log().record(
            "auth.login.failed", resource="auth/login", detail={"username": payload.username}, ip=_request_ip(request)
        )
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="User account is inactive")

    user = users.record_login(user["user_id"])
    token, session = get_session_store().create_session(
        user["user_id"], ip=_request_ip(request), user_agent=request.headers.get("user-agent")
    )
    get_audit_log().record(
        "auth.login", user_id=user["user_id"], resource="auth/login", ip=_request_ip(request)
    )
    return _session_response(token, session, user, response)


@router.get("/login")
def login_get(username: str, password: str, request: Request, response: Response):
    return _login(AuthCredentials(username=username, password=password), request, response)


@router.post("/login")
def login(payload: AuthCredentials, request: Request, response: Response):
    return _login(payload, request, response)


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, request: Request):
    try:
        user = get_user_store().create_user(
            payload.username,
            payload.password,
            display_name=payload.display_name,
            role=payload.role,
        )
    except ValueError as exc:
        code = 409 if "already exists" in str(exc) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    get_audit_log().record(
        "user.create", user_id=user["user_id"], resource="auth/signup", ip=_request_ip(request)
    )
    return user


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    resolved = get_session_store().resolve_session(token) if token else None
    if token:
        get_session_store().revoke_token(token)
    get_audit_log().record(
        "auth.logout",
        user_id=resolved["user"]["user_id"] if resolved else None,
        resource="auth/logout",
        ip=_request_ip(request),
    )
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"logged_out": True}
