"""Authentication (OIDC single sign-on and/or API keys), two roles, and
per-client rate limiting.

Single sign-on - per-user identities, the recommended production mode:
    OIDC_ISSUER          e.g. https://login.microsoftonline.com/<tenant>/v2.0
    OIDC_AUDIENCE        required with OIDC_ISSUER (the API's client id / app URI)
    OIDC_JWKS_URL        optional; discovered from the issuer when unset
    OIDC_ROLE_CLAIM      claim holding roles (default "roles"; dotted paths such as realm_access.roles work)
    OIDC_CLINICIAN_ROLE  default "clarity-clinician";  OIDC_ADMIN_ROLE default "clarity-admin"

API keys - service accounts and simple deployments:
    API_KEYS             comma-separated clinician keys (analyze, upload, chat, feedback, FHIR, own cases)
    ADMIN_API_KEYS       comma-separated admin keys (all of the above + audit log, metrics, all cases)

When nothing is configured, auth is disabled (local development) and /health
says so. Credentials travel as ``Authorization: Bearer <token-or-key>`` (keys may
also use ``X-API-Key``). Keys are only ever logged as a SHA-256 fingerprint; SSO
users are audited by their stable ``sub`` claim."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
import urllib.request
from collections import deque
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request

log = logging.getLogger("clinical.security")


@dataclass(frozen=True)
class Principal:
    actor: str              # "anonymous", "key:<fingerprint>" or "user:<sub>"
    role: str               # "clinician" | "admin"
    name: str | None = None  # display name for SSO users


def _keys(var: str) -> list[str]:
    return [k.strip() for k in os.getenv(var, "").split(",") if k.strip()]


def oidc_enabled() -> bool:
    return bool(os.getenv("OIDC_ISSUER"))


def auth_enabled() -> bool:
    return bool(_keys("API_KEYS") or _keys("ADMIN_API_KEYS") or oidc_enabled())


def auth_mode() -> str:
    modes = (["oidc"] if oidc_enabled() else []) + (["api-key"] if _keys("API_KEYS") or _keys("ADMIN_API_KEYS") else [])
    return "+".join(modes) or "disabled"


# ---------------------------------------------------------------- OIDC
_jwks: dict[str, jwt.PyJWKClient] = {}
_discovered: dict[str, str] = {}
ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "ES256", "ES384"]   # never HS* or "none"


def _jwks_url() -> str:
    if os.getenv("OIDC_JWKS_URL"):
        return os.environ["OIDC_JWKS_URL"]
    issuer = os.environ["OIDC_ISSUER"].rstrip("/")
    if issuer not in _discovered:
        with urllib.request.urlopen(f"{issuer}/.well-known/openid-configuration", timeout=5) as r:  # noqa: S310 - configured issuer
            _discovered[issuer] = json.loads(r.read())["jwks_uri"]
    return _discovered[issuer]


def _signing_key(token: str) -> Any:
    url = _jwks_url()
    client = _jwks.setdefault(url, jwt.PyJWKClient(url, cache_keys=True, lifespan=3600, timeout=5))
    return client.get_signing_key_from_jwt(token).key


def _claim(claims: dict[str, Any], path: str) -> Any:
    for part in path.split("."):
        claims = claims.get(part, {}) if isinstance(claims, dict) else {}
    return claims or []


def verify_token(token: str) -> Principal:
    try:
        claims = jwt.decode(token, _signing_key(token), algorithms=ALGORITHMS, audience=os.getenv("OIDC_AUDIENCE"),
                            issuer=os.environ["OIDC_ISSUER"], leeway=30, options={"require": ["exp", "iss", "sub", "aud"]})
    except Exception as exc:
        log.info("Token rejected (%s)", type(exc).__name__)
        raise HTTPException(status_code=401, detail="Invalid or expired access token.", headers={"WWW-Authenticate": 'Bearer error="invalid_token"'}) from exc
    roles = _claim(claims, os.getenv("OIDC_ROLE_CLAIM", "roles"))
    roles = {roles} if isinstance(roles, str) else set(roles)
    if os.getenv("OIDC_ADMIN_ROLE", "clarity-admin") in roles:
        role = "admin"
    elif os.getenv("OIDC_CLINICIAN_ROLE", "clarity-clinician") in roles:
        role = "clinician"
    else:
        raise HTTPException(status_code=403, detail="Your account has no Clarity role. Ask an administrator for clinician access.")
    return Principal(f"user:{claims['sub']}", role, claims.get("name") or claims.get("preferred_username") or claims.get("email"))


def fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def _presented_key(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return request.headers.get("x-api-key") or None


def _matches(key: str, candidates: list[str]) -> bool:
    # compare against every candidate so timing does not reveal which/how many keys exist
    return any([hmac.compare_digest(key.encode(), c.encode()) for c in candidates])


def authenticate(request: Request) -> Principal:
    if not auth_enabled():
        principal = Principal("anonymous", "admin")
    else:
        key = _presented_key(request)
        if not key:
            raise HTTPException(status_code=401, detail="Missing credentials. Sign in, or send 'Authorization: Bearer <token-or-key>'.",
                                headers={"WWW-Authenticate": "Bearer"})
        if oidc_enabled() and key.count(".") == 2:
            principal = verify_token(key)
        elif _matches(key, _keys("ADMIN_API_KEYS")):
            principal = Principal(f"key:{fingerprint(key)}", "admin")
        elif _matches(key, _keys("API_KEYS")):
            principal = Principal(f"key:{fingerprint(key)}", "clinician")
        else:
            raise HTTPException(status_code=401, detail="Invalid credentials.", headers={"WWW-Authenticate": "Bearer"})
    request.state.principal = principal
    return principal


def require_admin(principal: Principal = Depends(authenticate)) -> Principal:
    if principal.role != "admin":
        raise HTTPException(status_code=403, detail="Admin API key required.")
    return principal


# ---------------------------------------------------------------- rate limiting
class RateLimiter:
    """Sliding one-minute window per client. In-memory, so per-process: put a
    gateway limiter in front when running several replicas."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, client: str, limit: int) -> int | None:
        """Record a hit; return seconds to wait if over the limit, else None."""
        now = time.monotonic()
        with self._lock:
            q = self._hits.setdefault(client, deque())
            while q and now - q[0] >= 60:
                q.popleft()
            if len(q) >= limit:
                return max(1, int(60 - (now - q[0])) + 1)
            q.append(now)
            if len(self._hits) > 10_000:   # bound memory: drop clients idle for a full window
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] >= 60]:
                    del self._hits[k]
            return None


LIMITER = RateLimiter()


def client_ip(request: Request) -> str:
    """Client address for rate limiting. Behind N trusted proxies (TRUSTED_PROXY_HOPS), take the address the outermost
    trusted proxy appended to X-Forwarded-For - counted from the right, so a client cannot spoof it by sending its own header."""
    hops = int(os.getenv("TRUSTED_PROXY_HOPS", "0"))
    if hops > 0:
        chain = [x.strip() for x in request.headers.get("x-forwarded-for", "").split(",") if x.strip()]
        if len(chain) >= hops:
            return chain[-hops]
    return request.client.host if request.client else "-"


def rate_limit(request: Request, principal: Principal = Depends(authenticate)) -> Principal:
    limit = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    if limit > 0:
        client = principal.actor if principal.actor != "anonymous" else f"ip:{client_ip(request)}"
        wait = LIMITER.check(client, limit)
        if wait is not None:
            raise HTTPException(status_code=429, detail=f"Rate limit of {limit} requests/minute exceeded.", headers={"Retry-After": str(wait)})
    return principal
