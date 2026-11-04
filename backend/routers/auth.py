"""Authentication and first-run account setup endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from ..auth.audit import get_audit_log
from ..auth.sessions import SESSION_COOKIE_NAME, get_session_store
from ..auth.users import get_user_store
from ..schemas.models import AuthCredentials, AuthSetupRequest, SignupRequest

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _require_admin(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    resolved = get_session_store().resolve_session(token) if token else None
    if not resolved or resolved["user"].get("role") != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return resolved["user"]


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
    if user.get("approval_status") == "pending":
        raise HTTPException(status_code=403, detail="Your account is awaiting administrator approval")
    if user.get("approval_status") == "rejected":
        raise HTTPException(status_code=403, detail="Your account request was rejected by an administrator")
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
    users = get_user_store()
    # Bootstrap the very first account as the administrator. The atomic
    # create_first_admin transaction also handles two simultaneous first
    # signups safely; only the winner becomes the bootstrap admin.
    if not users.has_any_users():
        try:
            user = users.create_first_admin(
                payload.username, payload.password, display_name=payload.display_name
            )
            get_audit_log().record(
                "auth.bootstrap_signup", user_id=user["user_id"], resource="auth/signup", ip=_request_ip(request)
            )
            return user
        except ValueError as exc:
            if "already" not in str(exc).lower() and "completed" not in str(exc).lower():
                code = 409 if "username" in str(exc).lower() else 400
                raise HTTPException(status_code=code, detail=str(exc)) from exc

    requested_role = payload.role if payload.role in ("operator", "viewer") else "operator"
    try:
        user = users.create_user(
            payload.username,
            payload.password,
            display_name=payload.display_name,
            role=requested_role,
            is_active=False,
            approval_status="pending",
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


@router.get("/users")
def list_users(request: Request):
    _require_admin(request)
    return {"users": get_user_store().list_users()}


@router.patch("/users/{user_id}")
def update_user(user_id: str, payload: dict, request: Request):
    actor = _require_admin(request)
    users = get_user_store()
    target = users.get_user(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    role = payload.get("role")
    if role == "user":
        role = "viewer"
    if role == "viewer" and target["role"] == "admin" and users.count_active_admins() <= 1:
        raise HTTPException(status_code=400, detail="At least one active administrator is required")
    try:
        updated = users.update_user(
            user_id,
            username=payload.get("username"),
            display_name=payload.get("display_name"),
            role=role,
            is_active=payload.get("is_active"),
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        get_audit_log().record("user.update", user_id=actor["user_id"], resource=f"users/{user_id}", detail=payload, ip=_request_ip(request))
    except Exception:
        pass
    return updated


@router.patch("/users/{user_id}/approval")
def update_user_approval(user_id: str, payload: dict, request: Request):
    actor = _require_admin(request)
    approval = payload.get("status")
    if approval not in ("accepted", "rejected"):
        raise HTTPException(status_code=400, detail="Approval status must be accepted or rejected")
    users = get_user_store()
    target = users.get_user(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    role = payload.get("role") or target["role"]
    if role == "user":
        role = "viewer"
    try:
        updated = users.update_user(
            user_id,
            role=role,
            is_active=approval == "accepted",
            approval_status=approval,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    get_audit_log().record(
        f"user.{approval}", user_id=actor["user_id"], resource=f"users/{user_id}",
        detail={"role": role}, ip=_request_ip(request),
    )
    return updated


@router.patch("/users/{user_id}/password")
def update_user_password(user_id: str, payload: dict, request: Request):
    actor = _require_admin(request)
    password = payload.get("password")
    if not isinstance(password, str):
        raise HTTPException(status_code=400, detail="Password is required")
    users = get_user_store()
    if users.get_user(user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        users.set_password(user_id, password)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    get_audit_log().record(
        "user.password_reset", user_id=actor["user_id"], resource=f"users/{user_id}",
        ip=_request_ip(request),
    )
    return {"user_id": user_id, "password_updated": True}


@router.delete("/users/{user_id}")
def delete_user(user_id: str, request: Request):
    actor = _require_admin(request)
    if actor["user_id"] == user_id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    users = get_user_store()
    target = users.get_user(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target["role"] == "admin" and users.count_active_admins() <= 1:
        raise HTTPException(status_code=400, detail="At least one active administrator is required")
    users.delete_user(user_id)
    try:
        get_audit_log().record("user.delete", user_id=actor["user_id"], resource=f"users/{user_id}", ip=_request_ip(request))
    except Exception:
        pass
    return {"user_id": user_id, "deleted": True}
