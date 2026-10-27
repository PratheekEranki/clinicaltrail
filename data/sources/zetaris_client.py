"""Zetaris REST client — correct auth flow for the hackathon platform bundle.

The platform exposes two ports:
  :3000  UI + API proxy  (public, JWT-authenticated)
  :8888  Raw API         (published but requires internal-format auth)

The UI proxy is the supported path. Auth flow:
  1. POST http://localhost:3000/api/auth/login  → JWT token + orgId
  2. POST http://localhost:3000/api/proxy/query/sql/start
         Authorization: Bearer <token>
         X-Org-ID: <orgId>
         body: {"select": "<sql>", "pageLimit": <n>}

This module caches the token in-process (it's valid for the duration of the
hackathon run) and is imported by all three data source files.
"""
import json
import logging
import os
import threading
import urllib.request

log = logging.getLogger(__name__)

_BASE_URL = os.getenv("ZETARIS_BASE_URL", "http://localhost:3000")
_USERNAME = os.getenv("ZETARIS_USERNAME", "admin@zetaris.com")
_PASSWORD = os.getenv("ZETARIS_PASSWORD", "Zetaris1@")

_lock = threading.Lock()
_token: str | None = None
_org_id: str | None = None


def _login() -> tuple[str, str]:
    """Login and return (jwt_token, org_id). Caches result."""
    global _token, _org_id
    with _lock:
        if _token and _org_id:
            return _token, _org_id
        url = f"{_BASE_URL}/api/auth/login"
        payload = json.dumps({"username": _USERNAME, "password": _PASSWORD}).encode()
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
        # Response shape: {"idToken": "...", "orgId": 1, ...}
        # The Zetaris platform bundle returns "idToken"; also check legacy aliases.
        _token = (body.get("idToken") or body.get("token")
                  or body.get("accessToken") or body.get("jwt") or "")
        _org_id = str(body.get("orgId", body.get("org_id", "1")))
        if not _token:
            raise RuntimeError(f"Zetaris login returned no token: {body}")
        log.debug("Zetaris login OK, orgId=%s", _org_id)
        return _token, _org_id


def query(sql: str, page_limit: int = 50, timeout: int = 60) -> list[dict]:
    """Execute Lightning SQL and return rows as list of dicts.

    Args:
        sql: Lightning SQL statement.
        page_limit: Maximum rows to return per page.
        timeout: HTTP timeout seconds.

    Returns:
        List of row dicts, column-named.
    """
    token, org_id = _login()
    url = f"{_BASE_URL}/api/proxy/query/sql/start"
    payload = json.dumps({"select": sql, "pageLimit": page_limit}).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "X-Org-ID": org_id,
            "X-Request-ID": _request_id(),
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode())

    # Response shape varies; handle both column+data and direct list forms.
    if isinstance(body, list):
        return body
    cols = body.get("columns", [])
    rows = body.get("data", body.get("rows", []))
    if cols and rows:
        return [dict(zip(cols, row)) for row in rows]
    # Some versions return {"result": [{col: val}, ...]}
    result = body.get("result", body.get("results", []))
    if isinstance(result, list):
        return result
    return []


def _request_id() -> str:
    import uuid
    return str(uuid.uuid4())
