from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.api.deps import CurrentPrincipal, CurrentSession, ReadDB
from app.core.config import get_settings
from app.core.errors import NotAuthenticated
from app.modules.identity.commands import Login, Logout
from app.modules.identity.queries import list_api_tokens, user_summary
from app.modules.workspaces.queries import visible_workspaces
from app.platform.commands import Origin, bus
from app.platform.permissions import Actor, ActorKind

router = APIRouter(prefix="/auth", tags=["auth"])

ANONYMOUS = Actor(kind=ActorKind.USER, user_id=None, display="Anonymous")


class LoginBody(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response) -> dict[str, Any]:
    settings = get_settings()
    res = bus.execute(
        Login(
            email=body.email,
            password=body.password,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        ),
        actor=ANONYMOUS,
        origin=Origin.UI,
    ).result
    if not res.get("ok"):
        raise NotAuthenticated("email or password is incorrect", code="bad_credentials")
    response.set_cookie(
        settings.session_cookie_name,
        res["token"],
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"csrf": res["csrf"]}


@router.post("/logout")
def logout(request: Request, response: Response, info: CurrentSession) -> dict[str, bool]:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name, "")
    bus.execute(Logout(token=token), actor=info.actor, origin=Origin.UI)
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"ok": True}


@router.get("/me")
def me(info: CurrentSession, s: ReadDB) -> dict[str, Any]:
    """Current user, CSRF token and the workspaces (with permissions) they can open."""
    actor = info.actor
    return {
        "user": user_summary(info.user)
        | {"locale": info.user.locale, "preferences": info.user.preferences or {}},
        "csrf": info.csrf_token,
        "is_superadmin": actor.is_superadmin,
        "workspaces": [
            {
                "id": str(w.id),
                "key": w.key,
                "name": w.name,
                "item_label": w.item_label,
                "permissions": sorted(actor.permissions_in(w.id)),
            }
            for w in visible_workspaces(s, actor)
        ],
    }


@router.get("/whoami")
def whoami(p: CurrentPrincipal, s: ReadDB) -> dict[str, Any]:
    """Who the caller is, for cookie sessions and API tokens alike (scripts use
    this to check a token works)."""
    actor = p.actor
    return {
        "user_id": str(actor.user_id) if actor.user_id else None,
        "display": actor.display,
        "via": p.via,
        "read_only": p.read_only,
        "is_superadmin": actor.is_superadmin,
        "workspaces": [
            {"id": str(w.id), "key": w.key, "permissions": sorted(actor.permissions_in(w.id))}
            for w in visible_workspaces(s, actor)
        ],
    }


@router.get("/api-tokens")
def api_tokens(info: CurrentSession, s: ReadDB) -> list[dict[str, Any]]:
    """The caller's own API tokens (never the token values)."""
    return list_api_tokens(s, info.user.id)
