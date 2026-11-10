"""Admin-token checks and the deployment proof for a Google editor API.

Management routes verify the short-lived admin token the env server mints for
this backend (``X-DTAP-Admin-Token``) with the vendored reference verifier
(``dtap_admin.py``): the token must be for this backend's audience and the
request's tenant, and carry the route's scope. A missing token is 401,
anything else 403. User routes never read the header.

This API holds no admin credential of its own and never calls another
backend's management routes: seeded accounts are mirrored locally (by email,
bound to their google-idp identity on first login); setup creates the accounts
themselves at google-idp. ``GOOGLE_IDP_URL`` is required only to fetch the
IdP's public signing keys.

The backend refuses to start without ``DTAP_ADMIN_PUBLIC_KEY``,
``DTAP_ADMIN_AUDIENCE``, ``DTAP_BACKEND_PROOF_KEY`` (checked when
``dtap_admin`` is imported) and ``GOOGLE_IDP_URL``.
"""

from __future__ import annotations

import os
from typing import Any

import dtap_admin
from fastapi import Depends, HTTPException, Query, Request

ADMIN_HEADER = dtap_admin.HEADER
DEPLOYMENT_PROOF_PATH = dtap_admin.PROOF_PATH


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required; start this backend through `dtap env up`")
    return value


GOOGLE_IDP_URL = _required_env("GOOGLE_IDP_URL").rstrip("/")


def deployment_proof(nonce: str | None = Query(None)) -> dict:
    """Answer the env server's ownership challenge: ``{"proof", "audience"}``.

    The env server calls it before sending any admin token, so a stranger's
    service on a reused port is never sent one. Unauthenticated, no tenant, no
    side effects.
    """
    try:
        return dtap_admin.prove(nonce)
    except dtap_admin.InvalidNonce as error:
        raise HTTPException(status_code=400, detail=error.code) from error


def verify_admin(request: Request, tenant: str, scopes: tuple[str, ...]) -> str:
    """Verify the request's admin token for ``tenant`` and any of ``scopes``; return the tenant."""
    token = request.headers.get(ADMIN_HEADER)
    refused: dtap_admin.AdminAuthError | None = None
    for scope in scopes:
        try:
            return dtap_admin.verify(token, tenant, scope)["tenant"]
        except dtap_admin.InsufficientScope as error:
            refused = error
        except dtap_admin.AdminAuthError as error:
            raise HTTPException(status_code=error.status, detail=error.code) from error
    raise HTTPException(status_code=refused.status, detail=refused.code) from refused


def admin(*scopes: str):
    """Dependency for a management route on the X-Tenant-ID tenant; returns the verified tenant."""
    if not scopes:
        raise ValueError("an admin route needs at least one scope")

    def check(request: Request) -> str:
        return verify_admin(request, (request.headers.get("X-Tenant-ID") or "").strip(), scopes)

    return Depends(check)


def admin_path_tenant(*scopes: str):
    """Dependency for a management route naming its tenant in the path (``{tenant_id}``)."""
    if not scopes:
        raise ValueError("an admin route needs at least one scope")

    def check(request: Request) -> str:
        return verify_admin(request, request.path_params.get("tenant_id", ""), scopes)

    return Depends(check)


def check_body_tenant(body: dict[str, Any], tenant: str) -> None:
    """A body `tenant_id`, when present, must name the verified tenant."""
    claimed = body.get("tenant_id")
    if claimed not in (None, "") and str(claimed).strip() != tenant:
        raise HTTPException(status_code=400, detail="tenant_id does not match X-Tenant-ID")
