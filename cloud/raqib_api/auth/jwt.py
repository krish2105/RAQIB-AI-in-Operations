"""Verify Supabase Auth JWTs server-side. HS256 with the project secret when configured, else the JWKS endpoint
(asymmetric keys), cached for an hour. Nothing here trusts a claim it did not verify."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from ..config import settings

log = logging.getLogger(__name__)
_JWKS: dict[str, Any] = {"keys": None, "at": 0.0, "url": None}
ALGS = ["RS256", "ES256", "HS256"]


class AuthError(Exception):
    def __init__(self, message: str, status: int = 401) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Claims:
    sub: str
    email: str
    raw: dict[str, Any]


def _jwks(url: str) -> list[dict[str, Any]]:
    now = time.time()
    if _JWKS["keys"] is None or _JWKS["url"] != url or now - _JWKS["at"] > 3600:
        r = httpx.get(url, timeout=5.0)
        r.raise_for_status()
        _JWKS.update(keys=r.json().get("keys", []), at=now, url=url)
    return _JWKS["keys"]


def verify(token: str, *, secret: str | None = None, jwks_url: str | None = None, now: float | None = None) -> Claims:
    secret = secret if secret is not None else settings.supabase_jwt_secret
    jwks_url = jwks_url or (f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json" if settings.supabase_url else None)
    try:
        header = jwt.get_unverified_header(token)
        if secret and header.get("alg", "HS256") == "HS256":
            payload = jwt.decode(token, secret, algorithms=["HS256"], audience="authenticated", options={"require": ["exp", "sub"]})
        elif jwks_url:
            kid = header.get("kid")
            key = next((k for k in _jwks(jwks_url) if k.get("kid") == kid), None)
            if key is None:
                raise AuthError("unknown signing key")
            payload = jwt.decode(token, jwt.PyJWK(key).key, algorithms=[key.get("alg", header.get("alg", "RS256"))], audience="authenticated",
                                 options={"require": ["exp", "sub"]})
        else:
            raise AuthError("auth is not configured (SUPABASE_URL or SUPABASE_JWT_SECRET)", 503)
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("token expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthError(f"invalid token: {exc}") from exc
    except httpx.HTTPError as exc:
        raise AuthError("could not fetch signing keys", 503) from exc
    return Claims(sub=str(payload["sub"]), email=str(payload.get("email", "")), raw=payload)


def mint_dev_token(sub: str, email: str, secret: str, ttl_s: int = 3600, **extra: Any) -> str:
    """Test helper only: an HS256 token shaped like Supabase's."""
    now = int(time.time())
    return jwt.encode({"sub": sub, "email": email, "aud": "authenticated", "role": "authenticated", "iat": now, "exp": now + ttl_s, **extra}, secret, algorithm="HS256")
