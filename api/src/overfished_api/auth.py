"""
Auth0 JWT validation for the BFF. When AUTH0_BYPASS=1 (e.g. pytest), routes stay open.
"""

import os
from collections.abc import Sequence

from fastapi import Depends
from fastapi_plugin import Auth0FastAPI

_bypass: bool | None = None
_auth0: Auth0FastAPI | None = None


def auth0_bypass() -> bool:
    global _bypass
    if _bypass is None:
        v = os.getenv("AUTH0_BYPASS", "0").lower()
        _bypass = v in ("1", "true", "yes", "on")
    return _bypass


def get_auth0() -> Auth0FastAPI:
    if auth0_bypass():
        msg = "Auth0 is not initialized when AUTH0_BYPASS=1"
        raise RuntimeError(msg)
    global _auth0
    if _auth0 is None:
        # Vite/SPA vars often live in a single monorepo .env without a server prefix
        domain = (os.environ.get("AUTH0_DOMAIN") or os.environ.get("VITE_AUTH0_DOMAIN") or "").strip()
        audience = (os.environ.get("AUTH0_AUDIENCE") or os.environ.get("VITE_AUTH0_AUDIENCE") or "").strip()
        if not domain or not audience:
            err = "Set AUTH0_DOMAIN and AUTH0_AUDIENCE, or set AUTH0_BYPASS=1"
            raise RuntimeError(err)
        # SPAs use opaque Bearer access tokens, not DPoP proofs; leaving DPoP
        # enabled can break verify_request in some auth0-api-python builds.
        _auth0 = Auth0FastAPI(domain=domain, audience=audience, dpop_enabled=False, dpop_required=False)
    return _auth0


def protected_route_dependencies():
    if auth0_bypass():
        return []
    auth0 = get_auth0()
    return [Depends(auth0.require_auth())]


def cors_allowed_origins() -> Sequence[str] | None:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "")
    if not raw.strip():
        return None
    return [o.strip() for o in raw.split(",") if o.strip()]
