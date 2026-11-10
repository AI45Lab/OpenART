"""
Google Docs ENV API - FastAPI backend with PostgreSQL storage.
Independent environment for Google Docs sandbox.
"""

import base64
import json
import os
import secrets
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from jose import jwt as jose_jwt

try:
    import psycopg  # type: ignore
except Exception:
    psycopg = None

app = FastAPI(title="Google Docs ENV API")

MAX_ATTACHMENT_BYTES = int(os.getenv("MAX_ATTACHMENT_BYTES", str(50 * 1024 * 1024)))
MAX_TOTAL_UPLOAD_BYTES = int(os.getenv("MAX_TOTAL_UPLOAD_BYTES", str(500 * 1024 * 1024)))
_active_connection: ContextVar[Any] = ContextVar("googledocs_connection", default=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _log(msg: str) -> None:
    try:
        print(msg, flush=True)
    except Exception:
        pass


# ─── DB helpers ──────────────────────────────────────────────────────────────


def _pg_conn_params() -> Dict[str, Any]:
    return {
        "host": os.getenv("GOOGLEDOCS_PG_HOST", "127.0.0.1"),
        "port": int(os.getenv("GOOGLEDOCS_PG_PORT", "5474")),
        "dbname": os.getenv("GOOGLEDOCS_PG_DB", "googledocs_sandbox"),
        "user": os.getenv("GOOGLEDOCS_PG_USER", "sandbox"),
        "password": os.getenv("GOOGLEDOCS_PG_PASSWORD", "sandbox"),
        "autocommit": True,
    }


def _connect():
    if psycopg is None:
        raise RuntimeError("psycopg is required")
    return psycopg.connect(**_pg_conn_params())


@contextmanager
def _db_session():
    conn = _active_connection.get()
    if conn is not None:
        yield conn
    else:
        with _connect() as conn:
            yield conn


@contextmanager
def _transaction():
    """Reuse one connection so a failed multi-step operation leaves no writes."""
    with _db_session() as conn:
        with conn.transaction():
            token = _active_connection.set(conn)
            try:
                yield conn
            finally:
                _active_connection.reset(token)


def _query(sql: str, params: Optional[Tuple] = None) -> List[Dict[str, Any]]:
    with _db_session() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            if cur.description is None:
                return []
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]


def _exec(sql: str, params: Tuple = ()) -> int:
    with _db_session() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


# ─── Auth helpers ────────────────────────────────────────────────────────────
# This env is a pure resource server. It never sees passwords; user routes
# verify google-idp's RS256 JWTs (JWKS) and take the tenant from the token's
# claim. Management routes require a short-lived admin token for this backend (editor_admin).
# A judge reads an account's documents without its password: a read-as request
# (X-DTAP-Read-As with a read-scoped admin token, dtap_admin.read_as) is served
# as that account's existing mirror on the GET routes (GET /tools/call runs the
# read-only tools, GET /images/{id}); it creates and binds nothing.

import time as _time

import httpx as _httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dtap_admin
from editor_admin import (
    DEPLOYMENT_PROOF_PATH,
    GOOGLE_IDP_URL,
    admin,
    admin_path_tenant,
    check_body_tenant,
    deployment_proof,
)

# Deployment proof first: the env server checks it before sending the admin token.
app.get(DEPLOYMENT_PROOF_PATH)(deployment_proof)

OAUTH_ISSUER = os.getenv("OAUTH_ISSUER", "google-idp")
MY_AUDIENCE = os.getenv("MY_AUDIENCE", "gdocs-api")

_jwks_cache: Optional[List[Dict[str, Any]]] = None
_jwks_cached_at: float = 0.0
_JWKS_TTL = 300  # seconds


def _fetch_jwks() -> List[Dict[str, Any]]:
    global _jwks_cache, _jwks_cached_at
    if _jwks_cache and _time.time() - _jwks_cached_at < _JWKS_TTL:
        return _jwks_cache
    try:
        r = _httpx.get(f"{GOOGLE_IDP_URL}/.well-known/jwks.json", timeout=5, trust_env=False)
        r.raise_for_status()
        _jwks_cache = r.json().get("keys", [])
        _jwks_cached_at = _time.time()
    except (_httpx.HTTPError, ValueError) as error:
        if not _jwks_cache:
            raise HTTPException(status_code=503, detail="Identity service keys unavailable") from error
    return _jwks_cache


def _check_iss_aud(claims: Dict[str, Any]) -> bool:
    if claims.get("iss") != OAUTH_ISSUER:
        return False
    aud = claims.get("aud", [])
    if isinstance(aud, str):
        aud = [aud]
    return MY_AUDIENCE in aud


def _verify_jwt(token: str) -> Optional[Dict[str, Any]]:
    """Verify an RS256 google-idp token for this API; None if it is not one."""
    for key in _fetch_jwks():
        try:
            claims = jose_jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                options={"verify_aud": False},
            )
        except Exception:
            continue
        if _check_iss_aud(claims) and claims.get("tenant_id") and claims.get("sub"):
            return claims
    return None


def _bearer_claims(request: Request) -> Dict[str, Any]:
    """Claims of the request's Bearer JWT; 401 otherwise. X-Tenant-ID is ignored."""
    auth_header = request.headers.get("authorization", "")
    token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")
    claims = _verify_jwt(token)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid access token")
    return claims


def _read_as_account(request: Request) -> dict[str, Any] | None:
    """The account a judge reads as (X-DTAP-Read-As with a read-scoped admin token), or None.

    Only an existing mirror of the request's tenant is served (404 otherwise).
    """
    try:
        grant = dtap_admin.read_as(request.headers, request.method)
    except dtap_admin.AdminAuthError as error:
        raise HTTPException(status_code=error.status, detail=error.code) from error
    if grant is None:
        return None
    rows = _query(
        "SELECT id, email FROM users_mirror WHERE tenant_id=%s AND lower(email)=lower(%s)",
        (grant["tenant"], grant["email"]),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="read_as_account_not_found")
    return {"id": rows[0]["id"], "email": rows[0]["email"] or "", "tenant_id": grant["tenant"], "scope": ""}


def _caller(request: Request) -> dict[str, Any]:
    """The caller of a user route: the account a judge reads as, else the account whose JWT is sent.

    A JWT's identity is mirrored on first sight (_upsert_user_mirror); read-as never mirrors.
    """
    reader = _read_as_account(request)
    if reader is not None:
        return reader
    claims = _bearer_claims(request)
    tenant_id = claims["tenant_id"]
    uid = _upsert_user_mirror(int(claims["sub"]), tenant_id, claims.get("email"), claims.get("name"))
    return {"id": uid, "email": claims.get("email", ""), "tenant_id": tenant_id, "scope": claims.get("scope", "")}


def _ensure_tenant(tenant_id: str) -> None:
    """Lazy-create a local tenants mirror row for a tenant we haven't seen."""
    _exec("INSERT INTO tenants (id) VALUES (%s) ON CONFLICT (id) DO NOTHING", (tenant_id,))


def _mirror_rows(tenant_id: str, sub: Optional[int], email: str) -> List[Dict[str, Any]]:
    return _query(
        "SELECT id, sub, email FROM users_mirror WHERE tenant_id=%s AND (sub=%s OR lower(email)=%s)",
        (tenant_id, sub, email),
    )


def _upsert_user_mirror(sub: int, tenant_id: str, email: Optional[str], name: Optional[str]) -> int:
    """Local users_mirror.id for a verified IdP identity (user routes).

    Business FKs (documents.owner_id etc.) reference this local id. A row
    seeded for the identity's email before its first login (``sub`` NULL) is
    bound to it now; a row for that email bound to another identity is
    refused (401), never rebound.
    """
    _ensure_tenant(tenant_id)
    email = (email or "").strip().lower()
    rows = _query("SELECT id FROM users_mirror WHERE sub=%s AND tenant_id=%s", (sub, tenant_id))
    if rows:
        return rows[0]["id"]
    if email:
        rows = _query("SELECT id, sub FROM users_mirror WHERE tenant_id=%s AND lower(email)=%s", (tenant_id, email))
        if rows:
            if rows[0]["sub"] is not None:
                raise HTTPException(status_code=401, detail="Account is bound to another identity in this tenant")
            _exec("UPDATE users_mirror SET sub=%s, name=COALESCE(name, %s) WHERE id=%s", (sub, name, rows[0]["id"]))
            return rows[0]["id"]
    with _db_session() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users_mirror (sub, tenant_id, email, name) VALUES (%s, %s, %s, %s) RETURNING id",
                (sub, tenant_id, email or None, name),
            )
            return cur.fetchone()[0]


def _bind_mirror(sub: int, tenant_id: str, email: str, name: Optional[str]) -> int:
    """Mirror an IdP identity for a management caller; never rebind an account.

    A (tenant, email) row bound to another sub, or a (tenant, sub) row carrying
    another email, is a 409: the caller cannot take over an existing account.
    A row seeded for the email before its identity was known is bound to it.
    """
    email = (email or "").strip().lower()
    for row in _mirror_rows(tenant_id, sub, email):
        if row["sub"] is None:
            continue
        if row["sub"] != sub or (row["email"] or "").strip().lower() != email:
            raise HTTPException(status_code=409, detail="Account is already bound to another identity in this tenant")
    return _upsert_user_mirror(sub, tenant_id, email, name)


def _seed_mirror(tenant_id: str, email: str, name: Optional[str], sub: Optional[int] = None) -> int:
    """Local id for an account a seed names, without contacting google-idp.

    With ``sub`` (the IdP id setup got when it created the account) the row is
    bound now; without it an existing row is reused, else a row keyed by email
    is created and bound to the identity on its first login.
    """
    email = (email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Seed account has an empty email")
    if sub is not None:
        return _bind_mirror(sub, tenant_id, email, name)
    _ensure_tenant(tenant_id)
    rows = _query("SELECT id FROM users_mirror WHERE tenant_id=%s AND lower(email)=%s", (tenant_id, email))
    if rows:
        return rows[0]["id"]
    with _db_session() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users_mirror (sub, tenant_id, email, name) VALUES (NULL, %s, %s, %s) RETURNING id",
                (tenant_id, email, name),
            )
            return cur.fetchone()[0]


# Preserve explicit fixture IDs while storing each tenant's graph separately.
_PUBLIC_TABLES = {
    "document_comments",
    "document_shares",
    "images",
    "documents",
    "folders",
    "document_versions",
    "suggestions",
}
_PUBLIC_ARG_KINDS = {
    "document_id": "documents",
    "folder_id": "folders",
    "comment_id": "document_comments",
    "version_id": "document_versions",
    "share_id": "document_shares",
    "image_id": "images",
    "suggestion_id": "suggestions",
}


def _seed_public_id(kind: str, value: str, tenant_id: str) -> str:
    import hashlib

    if kind not in _PUBLIC_TABLES or not isinstance(value, str):
        raise HTTPException(status_code=400, detail="Invalid fixture ID")
    mapped = _query(
        "SELECT internal_id FROM public_ids WHERE tenant_id=%s AND kind=%s AND public_id=%s", (tenant_id, kind, value)
    )
    if mapped:
        return mapped[0]["internal_id"]
    existing = _query(f"SELECT id FROM {kind} WHERE id=%s AND tenant_id=%s", (value, tenant_id))
    internal = (
        value if existing else "seed_" + kind + "_" + hashlib.sha256(tenant_id.encode()).hexdigest() + ":" + value
    )
    _exec(
        "INSERT INTO public_ids(tenant_id,kind,public_id,internal_id) VALUES(%s,%s,%s,%s) ON CONFLICT(tenant_id,kind,public_id) DO NOTHING",
        (tenant_id, kind, value, internal),
    )
    return _query(
        "SELECT internal_id FROM public_ids WHERE tenant_id=%s AND kind=%s AND public_id=%s", (tenant_id, kind, value)
    )[0]["internal_id"]


def _resolve_public_id(kind: str, value, tenant_id: str):
    if not isinstance(value, str):
        return value
    rows = _query(
        "SELECT internal_id FROM public_ids WHERE tenant_id=%s AND kind=%s AND public_id=%s", (tenant_id, kind, value)
    )
    return rows[0]["internal_id"] if rows else value


def _resolve_public_arguments(arguments, tenant_id: str, tool_name: str):
    result = dict(arguments)
    for key, kind in _PUBLIC_ARG_KINDS.items():
        if key in result:
            result[key] = _resolve_public_id(kind, result[key], tenant_id)
    if "parent_id" in result:
        kind = "folders" if "folder" in tool_name else "document_comments"
        result["parent_id"] = _resolve_public_id(kind, result["parent_id"], tenant_id)
    return result


def _public_result(value, tenant_id: str, public_fields: bool = False):
    rows = _query("SELECT internal_id,public_id FROM public_ids WHERE tenant_id=%s", (tenant_id,))
    mapping = {row["internal_id"]: row["public_id"] for row in rows}

    def visit(item, key=None):
        if isinstance(item, dict):
            return {k: visit(v, k) for k, v in item.items() if not (public_fields and k == "tenant_id")}
        if isinstance(item, list):
            return [visit(v, key) for v in item]
        if isinstance(item, str) and (key == "id" or key == "default_sheet_id" or (key and key.endswith("_id"))):
            return mapping.get(item, item)
        if isinstance(item, str) and key == "ref":
            for internal, public in mapping.items():
                item = item.replace(internal, public)
        return item

    return visit(value)


def _require_user(args: Dict[str, Any]) -> Tuple[int, str]:
    uid = args.get("_user_id")
    email = args.get("_user_email", "")
    if not uid:
        raise HTTPException(status_code=401, detail="Missing user context")
    return uid, email


def _user_tenant_id(args: Dict[str, Any]) -> str:
    if args.get("_user_tenant_id"):
        return args["_user_tenant_id"]
    rows = _query("SELECT tenant_id FROM users_mirror WHERE id=%s", (args.get("_user_id"),))
    if not rows:
        raise HTTPException(status_code=401, detail="Missing user context")
    return rows[0]["tenant_id"]


def _can_access_document(user_id: int, doc_id: str, min_permission: str = "viewer") -> bool:
    """Check if user can access document with at least min_permission."""
    doc = _query(
        "SELECT owner_id FROM documents WHERE id=%s AND trashed=FALSE AND tenant_id=(SELECT tenant_id FROM users_mirror WHERE id=%s)",
        (doc_id, user_id),
    )
    if not doc:
        return False
    if doc[0]["owner_id"] == user_id:
        return True

    permission_levels = {"viewer": 0, "commenter": 1, "editor": 2, "owner": 3}
    min_level = permission_levels.get(min_permission, 0)

    shares = _query("SELECT permission FROM document_shares WHERE document_id=%s AND user_id=%s", (doc_id, user_id))
    if shares:
        user_level = permission_levels.get(shares[0]["permission"], 0)
        return user_level >= min_level

    link_shares = _query(
        "SELECT link_permission FROM document_shares WHERE document_id=%s AND link_sharing=TRUE", (doc_id,)
    )
    if link_shares:
        link_level = permission_levels.get(link_shares[0]["link_permission"], 0)
        return link_level >= min_level

    return False


def _is_document_owner(user_id: int, doc_id: str) -> bool:
    """Check if a user is the owner of the document."""
    doc = _query(
        "SELECT owner_id FROM documents WHERE id=%s AND trashed=FALSE AND tenant_id=(SELECT tenant_id FROM users_mirror WHERE id=%s)",
        (doc_id, user_id),
    )
    if not doc:
        return False
    return doc[0]["owner_id"] == user_id


# ═════════════════════════════════════════════════════════════════════════════
# Document Tools
# ═════════════════════════════════════════════════════════════════════════════


def tool_create_document(args: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new document, owned by the authenticated caller.

    * ``share_with``: an email to also share the new doc with (inserts a
      ``document_shares`` row granting ``share_permission``, default "viewer",
      so the doc surfaces in that user's "shared with me" view). Sharing your
      own document is a normal capability; ownership is always the caller.
    """
    uid, _ = _require_user(args)
    tenant_id = _user_tenant_id(args)
    title = args.get("title", "Untitled document")
    content = args.get("content", "")
    content_html = args.get("content_html", "")
    folder_id = args.get("folder_id")

    # Resolve who owns the new document. Default: the authenticated caller.
    owner_id = uid

    doc_id = _gen_id("doc")
    now = _now()

    _exec(
        "INSERT INTO documents (id, tenant_id, owner_id, title, content, content_html, last_edited_by, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (doc_id, tenant_id, owner_id, title, content, content_html, owner_id, now, now),
    )

    if folder_id:
        _exec("INSERT INTO document_folders (document_id, folder_id) VALUES (%s, %s)", (doc_id, folder_id))

    _exec(
        "INSERT INTO recent_documents (user_id, document_id, accessed_at) VALUES (%s, %s, %s) "
        "ON CONFLICT (user_id, document_id) DO UPDATE SET accessed_at=%s",
        (uid, doc_id, now, now),
    )

    # Optionally share the new document on creation (Docs lets you create-and-share
    # in one step). `share_with` is an email, the literal "self", or a list of emails;
    # `share_permission` is viewer/commenter/editor. Honoring it here is what makes
    # create-then-share flows actually grant the target access — e.g. the injection
    # server's inject_shared_document passes share_with, and without this the doc is
    # created but never shared, so the target gets "Access denied".
    share_with = args.get("share_with")
    share_id = None
    if share_with:
        share_permission = args.get("share_permission", "viewer")
        if share_permission not in {"viewer", "commenter", "editor"}:
            raise HTTPException(status_code=400, detail="Invalid share permission")
        emails = share_with if isinstance(share_with, list) else [share_with]
        for entry in emails:
            if not entry:
                continue
            if isinstance(entry, str) and entry.strip().lower() == "self":
                caller = _query("SELECT email FROM users_mirror WHERE id=%s", (uid,))
                share_email = (caller[0]["email"] if caller else "") or ""
                share_uid = uid
            else:
                share_email = str(entry)
                target_user = _query(
                    "SELECT id FROM users_mirror WHERE lower(email)=lower(%s) AND tenant_id=%s",
                    (share_email, tenant_id),
                )
                share_uid = target_user[0]["id"] if target_user else None
            share_id = _gen_id("share")
            _exec(
                "INSERT INTO document_shares (id, document_id, user_id, email, permission) VALUES (%s, %s, %s, %s, %s)",
                (share_id, doc_id, share_uid, share_email, share_permission),
            )
            if share_uid is not None:
                _exec(
                    "INSERT INTO recent_documents (user_id, document_id, accessed_at) VALUES (%s, %s, %s) "
                    "ON CONFLICT (user_id, document_id) DO UPDATE SET accessed_at=%s",
                    (share_uid, doc_id, now, now),
                )

    result = {"id": doc_id, "title": title, "created_at": now, "updated_at": now}
    if share_id is not None:
        result["share_id"] = share_id
    return result


def tool_get_document(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get a document by ID."""
    uid, _ = _require_user(args)
    doc_id = args["document_id"]

    if not _can_access_document(uid, doc_id):
        raise HTTPException(status_code=403, detail="Access denied")

    rows = _query(
        "SELECT d.*, u.name as owner_name, u.email as owner_email "
        "FROM documents d JOIN users_mirror u ON d.owner_id = u.id WHERE d.id=%s",
        (doc_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    # A read through GET /tools/call records nothing (_run_tool's record_access).
    if args.get("_user_record_access", True):
        now = _now()
        _exec(
            "INSERT INTO recent_documents (user_id, document_id, accessed_at) VALUES (%s, %s, %s) "
            "ON CONFLICT (user_id, document_id) DO UPDATE SET accessed_at=%s",
            (uid, doc_id, now, now),
        )

    result = dict(rows[0])
    # Attach the current user's effective permission
    if result.get("owner_id") == uid:
        result["user_permission"] = "owner"
    else:
        share = _query("SELECT permission FROM document_shares WHERE document_id=%s AND user_id=%s", (doc_id, uid))
        if share:
            result["user_permission"] = share[0]["permission"]
        else:
            # Access via link sharing
            link_share = _query(
                "SELECT link_permission FROM document_shares WHERE document_id=%s AND link_sharing=TRUE", (doc_id,)
            )
            result["user_permission"] = link_share[0]["link_permission"] if link_share else "viewer"
    return result


def tool_update_document(args: Dict[str, Any]) -> Dict[str, Any]:
    """Update document content or title.

    * ``document_id`` may be omitted: the target is then resolved generically
      via ``_resolve_document_target`` (target_owner / match / latest), so an
      id isn't required.
    * ``append``: when true, concatenate ``content`` onto the existing body
      instead of replacing it.
    """
    uid, _ = _require_user(args)
    if args.get("document_id"):
        doc_id = args["document_id"]
    else:
        doc_id = _resolve_document_target(args)["id"]
        # Keep tool_get_document (called below) pointed at the resolved doc.
        args["document_id"] = doc_id

    if not _can_access_document(uid, doc_id, "editor"):
        raise HTTPException(status_code=403, detail="Edit access denied")

    append = bool(args.get("append", False))

    updates = []
    params = []

    if "title" in args:
        updates.append("title=%s")
        params.append(args["title"])
    if "content" in args:
        new_content = args["content"]
        if append:
            existing = _query("SELECT content FROM documents WHERE id=%s", (doc_id,))
            prev = (existing[0].get("content") if existing else "") or ""
            new_content = (prev + "\n" + str(args["content"])) if prev else args["content"]
        updates.append("content=%s")
        params.append(new_content)
    if "content_html" in args:
        updates.append("content_html=%s")
        params.append(args["content_html"])
    if "starred" in args:
        updates.append("starred=%s")
        params.append(bool(args["starred"]))

    if not updates:
        return tool_get_document(args)

    now = _now()
    updates.append("updated_at=%s")
    params.append(now)
    updates.append("last_edited_by=%s")
    params.append(uid)
    params.append(doc_id)

    _exec(f"UPDATE documents SET {', '.join(updates)} WHERE id=%s", tuple(params))
    return tool_get_document(args)


def tool_delete_document(args: Dict[str, Any]) -> Dict[str, Any]:
    """Move document to trash or permanently delete."""
    uid, _ = _require_user(args)
    doc_id = args["document_id"]
    permanent = args.get("permanent", False)

    doc = _query("SELECT owner_id, trashed FROM documents WHERE id=%s", (doc_id,))
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    if doc[0]["owner_id"] != uid:
        raise HTTPException(status_code=403, detail="Only owner can delete")

    if permanent:
        _exec("DELETE FROM documents WHERE id=%s", (doc_id,))
        return {"deleted": True, "document_id": doc_id, "permanent": True}
    else:
        now = _now()
        _exec("UPDATE documents SET trashed=TRUE, trashed_at=%s WHERE id=%s", (now, doc_id))
        return {"trashed": True, "document_id": doc_id, "trashed_at": now}


def tool_restore_document(args: Dict[str, Any]) -> Dict[str, Any]:
    """Restore document from trash."""
    uid, _ = _require_user(args)
    doc_id = args["document_id"]

    doc = _query("SELECT owner_id FROM documents WHERE id=%s AND trashed=TRUE", (doc_id,))
    if not doc:
        raise HTTPException(status_code=404, detail=f"Trashed document {doc_id} not found")
    if doc[0]["owner_id"] != uid:
        raise HTTPException(status_code=403, detail="Only owner can restore")

    _exec("UPDATE documents SET trashed=FALSE, trashed_at=NULL WHERE id=%s", (doc_id,))
    return {"restored": True, "document_id": doc_id}


def tool_list_documents(args: Dict[str, Any]) -> Dict[str, Any]:
    """List user's documents."""
    uid, _ = _require_user(args)
    limit = int(args.get("limit", 50))
    offset = int(args.get("offset", 0))
    folder_id = args.get("folder_id")
    starred = args.get("starred")
    trashed = args.get("trashed", False)
    search = args.get("search")

    sql = """
        SELECT DISTINCT d.id, d.title, d.starred, d.trashed, d.created_at, d.updated_at,
               u.name as owner_name, u.email as owner_email
        FROM documents d
        JOIN users_mirror u ON d.owner_id = u.id
        LEFT JOIN document_shares ds ON d.id = ds.document_id
        WHERE (d.owner_id = %s OR ds.user_id = %s) AND d.trashed = %s
    """
    params: list = [uid, uid, trashed]

    if folder_id:
        sql += " AND EXISTS (SELECT 1 FROM document_folders df WHERE df.document_id = d.id AND df.folder_id = %s)"
        params.append(folder_id)
    if starred is not None:
        sql += " AND d.starred = %s"
        params.append(starred)
    if search:
        sql += " AND (d.title ILIKE %s OR d.content ILIKE %s)"
        params.extend([f"%{search}%", f"%{search}%"])

    sql += " ORDER BY d.updated_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    rows = _query(sql, tuple(params))
    return {"documents": rows, "count": len(rows)}


def tool_search_documents(args: Dict[str, Any]) -> Dict[str, Any]:
    """Search documents by title or content."""
    args["search"] = args.get("query", "")
    return tool_list_documents(args)


def tool_get_recent_documents(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get recently accessed documents."""
    uid, _ = _require_user(args)
    limit = int(args.get("limit", 20))

    rows = _query(
        """SELECT d.id, d.title, d.starred, d.updated_at, r.accessed_at,
                  u.name as owner_name
           FROM recent_documents r
           JOIN documents d ON r.document_id = d.id
           JOIN users_mirror u ON d.owner_id = u.id
           WHERE r.user_id = %s AND d.trashed = FALSE
           ORDER BY r.accessed_at DESC LIMIT %s""",
        (uid, limit),
    )
    return {"documents": rows, "count": len(rows)}


# ═════════════════════════════════════════════════════════════════════════════
# Sharing Tools
# ═════════════════════════════════════════════════════════════════════════════


def tool_share_document(args: Dict[str, Any]) -> Dict[str, Any]:
    """Share document with a user. Sharing is restricted to the owner's tenant."""
    uid, _ = _require_user(args)
    doc_id = args["document_id"]
    share_email = args["email"]
    permission = args.get("permission", "viewer")

    if not _is_document_owner(uid, doc_id):
        raise HTTPException(status_code=403, detail="Only owner can manage sharing")

    # Scope the target user lookup to the document's tenant — cross-tenant
    # shares are not allowed in the sandbox.
    doc_rows = _query("SELECT tenant_id FROM documents WHERE id=%s", (doc_id,))
    if not doc_rows:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    doc_tenant_id = doc_rows[0]["tenant_id"]

    target_user = _query(
        "SELECT id FROM users_mirror WHERE email=%s AND tenant_id=%s",
        (share_email, doc_tenant_id),
    )
    if not target_user:
        raise HTTPException(
            status_code=404,
            detail=f"User {share_email} not found in tenant {doc_tenant_id}",
        )
    target_uid = target_user[0]["id"]

    share_id = _gen_id("share")
    _exec(
        "INSERT INTO document_shares (id, document_id, user_id, email, permission) VALUES (%s, %s, %s, %s, %s)",
        (share_id, doc_id, target_uid, share_email, permission),
    )

    return {"share_id": share_id, "document_id": doc_id, "email": share_email, "permission": permission}


def tool_update_share(args: Dict[str, Any]) -> Dict[str, Any]:
    """Update sharing permission."""
    uid, _ = _require_user(args)
    share_id = args["share_id"]
    permission = args["permission"]

    share = _query("SELECT document_id FROM document_shares WHERE id=%s", (share_id,))
    if not share:
        raise HTTPException(status_code=404, detail=f"Share {share_id} not found")

    if not _is_document_owner(uid, share[0]["document_id"]):
        raise HTTPException(status_code=403, detail="Only owner can manage sharing")

    _exec("UPDATE document_shares SET permission=%s WHERE id=%s", (permission, share_id))
    return {"share_id": share_id, "permission": permission}


def tool_remove_share(args: Dict[str, Any]) -> Dict[str, Any]:
    """Remove document share."""
    uid, _ = _require_user(args)
    share_id = args["share_id"]

    share = _query("SELECT document_id FROM document_shares WHERE id=%s", (share_id,))
    if not share:
        raise HTTPException(status_code=404, detail=f"Share {share_id} not found")

    if not _is_document_owner(uid, share[0]["document_id"]):
        raise HTTPException(status_code=403, detail="Only owner can manage sharing")

    _exec("DELETE FROM document_shares WHERE id=%s", (share_id,))
    return {"removed": True, "share_id": share_id}


def tool_get_document_shares(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get all shares for a document."""
    uid, _ = _require_user(args)
    doc_id = args["document_id"]

    if not _can_access_document(uid, doc_id):
        raise HTTPException(status_code=403, detail="Access denied")

    rows = _query(
        """SELECT ds.*, u.name as user_name 
           FROM document_shares ds 
           LEFT JOIN users_mirror u ON ds.user_id = u.id 
           WHERE ds.document_id = %s""",
        (doc_id,),
    )
    return {"shares": rows, "count": len(rows)}


def tool_enable_link_sharing(args: Dict[str, Any]) -> Dict[str, Any]:
    """Enable link sharing for document."""
    uid, _ = _require_user(args)
    doc_id = args["document_id"]
    permission = args.get("permission", "viewer")

    if not _is_document_owner(uid, doc_id):
        raise HTTPException(status_code=403, detail="Only owner can manage sharing")

    existing = _query("SELECT id FROM document_shares WHERE document_id=%s AND link_sharing=TRUE", (doc_id,))
    if existing:
        _exec("UPDATE document_shares SET link_permission=%s WHERE id=%s", (permission, existing[0]["id"]))
        return {"document_id": doc_id, "link_sharing": True, "permission": permission}

    share_id = _gen_id("link")
    _exec(
        "INSERT INTO document_shares (id, document_id, link_sharing, link_permission) VALUES (%s, %s, TRUE, %s)",
        (share_id, doc_id, permission),
    )
    return {"document_id": doc_id, "link_sharing": True, "permission": permission, "share_id": share_id}


def tool_disable_link_sharing(args: Dict[str, Any]) -> Dict[str, Any]:
    """Disable link sharing for document."""
    uid, _ = _require_user(args)
    doc_id = args["document_id"]

    if not _is_document_owner(uid, doc_id):
        raise HTTPException(status_code=403, detail="Only owner can manage sharing")

    _exec("DELETE FROM document_shares WHERE document_id=%s AND link_sharing=TRUE", (doc_id,))
    return {"document_id": doc_id, "link_sharing": False}


# ═════════════════════════════════════════════════════════════════════════════
# Comment Tools
# ═════════════════════════════════════════════════════════════════════════════


def tool_add_comment(args: Dict[str, Any]) -> Dict[str, Any]:
    """Add a comment to document.

      * ``document_id`` may be omitted: the target is resolved generically via
        ``_resolve_document_target`` (target_owner / match / latest).

    The comment is authored by the authenticated caller, who must already have
    commenter access to the document.
    """
    uid, _ = _require_user(args)
    if args.get("document_id"):
        doc_id = args["document_id"]
    else:
        doc_id = _resolve_document_target(args)["id"]
    content = args["content"]
    quoted_text = args.get("quoted_text")
    selection_start = args.get("selection_start")
    selection_end = args.get("selection_end")
    parent_id = args.get("parent_id")

    author_id = uid
    if not _can_access_document(author_id, doc_id, "commenter"):
        raise HTTPException(status_code=403, detail="Cannot comment on document")

    comment_id = _gen_id("comment")
    now = _now()

    _exec(
        """INSERT INTO document_comments
           (id, document_id, user_id, content, quoted_text, selection_start, selection_end, parent_id, created_at, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (comment_id, doc_id, author_id, content, quoted_text, selection_start, selection_end, parent_id, now, now),
    )

    return {"comment_id": comment_id, "document_id": doc_id, "content": content, "created_at": now}


def tool_get_comments(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get comments for a document."""
    uid, _ = _require_user(args)
    doc_id = args["document_id"]
    include_resolved = args.get("include_resolved", False)

    if not _can_access_document(uid, doc_id):
        raise HTTPException(status_code=403, detail="Access denied")

    sql = """SELECT c.*, u.name as author_name, u.email as author_email
             FROM document_comments c
             JOIN users_mirror u ON c.user_id = u.id
             WHERE c.document_id = %s"""
    params: list = [doc_id]

    if not include_resolved:
        sql += " AND c.resolved = FALSE"

    sql += " ORDER BY c.created_at ASC"

    rows = _query(sql, tuple(params))
    return {"comments": rows, "count": len(rows)}


def tool_resolve_comment(args: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve a comment."""
    uid, _ = _require_user(args)
    comment_id = args["comment_id"]

    comment = _query("SELECT document_id FROM document_comments WHERE id=%s", (comment_id,))
    if not comment:
        raise HTTPException(status_code=404, detail=f"Comment {comment_id} not found")

    if not _can_access_document(uid, comment[0]["document_id"], "editor"):
        raise HTTPException(status_code=403, detail="Cannot resolve comment")

    _exec("UPDATE document_comments SET resolved=TRUE, resolved_by=%s WHERE id=%s", (uid, comment_id))
    return {"resolved": True, "comment_id": comment_id}


def tool_delete_comment(args: Dict[str, Any]) -> Dict[str, Any]:
    """Delete a comment."""
    uid, _ = _require_user(args)
    comment_id = args["comment_id"]

    comment = _query("SELECT document_id, user_id FROM document_comments WHERE id=%s", (comment_id,))
    if not comment:
        raise HTTPException(status_code=404, detail=f"Comment {comment_id} not found")

    if comment[0]["user_id"] != uid:
        if not _can_access_document(uid, comment[0]["document_id"], "editor"):
            raise HTTPException(status_code=403, detail="Cannot delete comment")

    _exec("DELETE FROM document_comments WHERE id=%s", (comment_id,))
    return {"deleted": True, "comment_id": comment_id}


# ═════════════════════════════════════════════════════════════════════════════
# Version History Tools
# ═════════════════════════════════════════════════════════════════════════════


def tool_create_version(args: Dict[str, Any]) -> Dict[str, Any]:
    """Create a named version of document."""
    uid, _ = _require_user(args)
    doc_id = args["document_id"]
    version_name = args.get("version_name")

    if not _can_access_document(uid, doc_id, "editor"):
        raise HTTPException(status_code=403, detail="Cannot create version")

    doc = _query("SELECT content, content_html FROM documents WHERE id=%s", (doc_id,))
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    version_id = _gen_id("ver")
    now = _now()

    _exec(
        "INSERT INTO document_versions (id, document_id, version_name, content, content_html, created_by, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (version_id, doc_id, version_name, doc[0]["content"], doc[0]["content_html"], uid, now),
    )

    return {"version_id": version_id, "document_id": doc_id, "version_name": version_name, "created_at": now}


def tool_list_versions(args: Dict[str, Any]) -> Dict[str, Any]:
    """List version history for document."""
    uid, _ = _require_user(args)
    doc_id = args["document_id"]

    if not _can_access_document(uid, doc_id):
        raise HTTPException(status_code=403, detail="Access denied")

    rows = _query(
        """SELECT v.id, v.version_name, v.created_at, u.name as created_by_name
           FROM document_versions v
           JOIN users_mirror u ON v.created_by = u.id
           WHERE v.document_id = %s
           ORDER BY v.created_at DESC""",
        (doc_id,),
    )
    return {"versions": rows, "count": len(rows)}


def tool_restore_version(args: Dict[str, Any]) -> Dict[str, Any]:
    """Restore document to a previous version."""
    uid, _ = _require_user(args)
    requested_doc_id = args.get("document_id")
    version_id = args["version_id"]

    version = _query("SELECT document_id, content, content_html FROM document_versions WHERE id=%s", (version_id,))
    if not version:
        raise HTTPException(status_code=404, detail=f"Version {version_id} not found")

    doc_id = version[0]["document_id"]
    if requested_doc_id and requested_doc_id != doc_id:
        raise HTTPException(status_code=400, detail="document_id does not match version's document")
    if not _can_access_document(uid, doc_id, "editor"):
        raise HTTPException(status_code=403, detail="Cannot restore version")

    now = _now()
    _exec(
        "UPDATE documents SET content=%s, content_html=%s, updated_at=%s, last_edited_by=%s WHERE id=%s",
        (version[0]["content"], version[0]["content_html"], now, uid, doc_id),
    )

    return {"restored": True, "version_id": version_id, "document_id": doc_id}


# ═════════════════════════════════════════════════════════════════════════════
# Folder Tools
# ═════════════════════════════════════════════════════════════════════════════


def tool_create_folder(args: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new folder."""
    uid, _ = _require_user(args)
    tenant_id = _user_tenant_id(args)
    name = args["name"]
    parent_id = args.get("parent_id")
    color = args.get("color")

    folder_id = _gen_id("folder")
    now = _now()

    _exec(
        "INSERT INTO folders (id, tenant_id, owner_id, name, parent_id, color, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (folder_id, tenant_id, uid, name, parent_id, color, now, now),
    )

    return {"id": folder_id, "name": name, "parent_id": parent_id, "created_at": now}


def tool_list_folders(args: Dict[str, Any]) -> Dict[str, Any]:
    """List user's folders."""
    uid, _ = _require_user(args)
    parent_id = args.get("parent_id")

    if parent_id:
        rows = _query(
            "SELECT * FROM folders WHERE owner_id=%s AND parent_id=%s AND trashed=FALSE ORDER BY name", (uid, parent_id)
        )
    else:
        rows = _query(
            "SELECT * FROM folders WHERE owner_id=%s AND parent_id IS NULL AND trashed=FALSE ORDER BY name", (uid,)
        )

    return {"folders": rows, "count": len(rows)}


def tool_move_document_to_folder(args: Dict[str, Any]) -> Dict[str, Any]:
    """Move document to a folder."""
    uid, _ = _require_user(args)
    doc_id = args["document_id"]
    folder_id = args.get("folder_id")

    if not _can_access_document(uid, doc_id, "editor"):
        raise HTTPException(status_code=403, detail="Cannot move document")

    _exec("DELETE FROM document_folders WHERE document_id=%s", (doc_id,))

    if folder_id:
        _exec("INSERT INTO document_folders (document_id, folder_id) VALUES (%s, %s)", (doc_id, folder_id))

    return {"document_id": doc_id, "folder_id": folder_id}


# ═════════════════════════════════════════════════════════════════════════════
# Image Tools
# ═════════════════════════════════════════════════════════════════════════════


def tool_upload_image(args: Dict[str, Any]) -> Dict[str, Any]:
    """Upload an image to document."""
    uid, _ = _require_user(args)
    doc_id = args.get("document_id")
    filename = args["filename"]
    mime_type = args.get("mime_type", "image/png")
    data_base64 = args.get("data")
    url = args.get("url")
    width = args.get("width")
    height = args.get("height")

    if doc_id and not _can_access_document(uid, doc_id, "editor"):
        raise HTTPException(status_code=403, detail="Cannot upload to document")
    if not data_base64 and url and url.startswith("/images/"):
        # A URL-only upload must not create a new metadata alias to another
        # tenant's legacy disk blob, including on a later startup import.
        source = _query(
            "SELECT user_id, document_id FROM images WHERE url=%s AND tenant_id=%s", (url, _user_tenant_id(args))
        )
        if not source:
            raise HTTPException(status_code=404, detail="Image not found")
        if source[0]["user_id"] != uid and (
            not source[0]["document_id"] or not _can_access_document(uid, source[0]["document_id"])
        ):
            raise HTTPException(status_code=403, detail="Access denied")

    image_id = _gen_id("img")
    now = _now()

    data_bytes = base64.b64decode(data_base64) if data_base64 else None
    size_bytes = len(data_bytes) if data_bytes is not None else None
    stored_url = url
    with _transaction():
        if data_bytes is not None:
            if not data_bytes:
                raise HTTPException(status_code=400, detail="Empty body")
            if size_bytes > MAX_ATTACHMENT_BYTES:
                raise HTTPException(
                    status_code=413, detail=f"Blob exceeds per-file limit of {MAX_ATTACHMENT_BYTES} bytes"
                )
            tenant_id = _user_tenant_id(args)
            # Serialize quota checks for this tenant, including concurrent uploads.
            _query("SELECT id FROM tenants WHERE id=%s FOR UPDATE", (tenant_id,))
            used = _query("SELECT COALESCE(SUM(size_bytes), 0) AS size FROM images WHERE tenant_id=%s", (tenant_id,))[
                0
            ]["size"]
            if used + size_bytes > MAX_TOTAL_UPLOAD_BYTES:
                raise HTTPException(status_code=507, detail="Blob storage quota exceeded")
            # Keep the original opaque blob URL separate from the image row ID.
            # Bytes now live with their tenant-owned metadata in PostgreSQL.
            stored_url = f"/images/{secrets.token_hex(16)}"
        _exec(
            """INSERT INTO images (id, document_id, user_id, filename, mime_type, size_bytes, width, height, data, url, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (image_id, doc_id, uid, filename, mime_type, size_bytes, width, height, data_bytes, stored_url, now),
        )

    return {"image_id": image_id, "filename": filename, "url": stored_url or f"/images/{image_id}", "created_at": now}


def tool_list_images(args: Dict[str, Any]) -> Dict[str, Any]:
    """List images in a document."""
    uid, _ = _require_user(args)
    doc_id = args["document_id"]

    if not _can_access_document(uid, doc_id):
        raise HTTPException(status_code=403, detail="Access denied")

    rows = _query(
        "SELECT id, filename, mime_type, size_bytes, width, height, url, created_at FROM images WHERE document_id=%s",
        (doc_id,),
    )
    return {"images": rows, "count": len(rows)}


def tool_delete_image(args: Dict[str, Any]) -> Dict[str, Any]:
    """Delete an image."""
    uid, _ = _require_user(args)
    image_id = args["image_id"]

    img = _query(
        "SELECT document_id, user_id FROM images WHERE id=%s AND tenant_id=%s", (image_id, _user_tenant_id(args))
    )
    if not img:
        raise HTTPException(status_code=404, detail=f"Image {image_id} not found")

    if img[0]["user_id"] != uid:
        if not img[0]["document_id"] or not _can_access_document(uid, img[0]["document_id"], "editor"):
            raise HTTPException(status_code=403, detail="Cannot delete image")

    _exec("DELETE FROM images WHERE id=%s", (image_id,))
    return {"deleted": True, "image_id": image_id}


# ═════════════════════════════════════════════════════════════════════════════
# Suggestion Tools
# ═════════════════════════════════════════════════════════════════════════════


def tool_add_suggestion(args: Dict[str, Any]) -> Dict[str, Any]:
    """Add a suggestion to document."""
    uid, _ = _require_user(args)
    doc_id = args["document_id"]
    suggestion_type = args["suggestion_type"]
    original_text = args.get("original_text")
    suggested_text = args.get("suggested_text")
    selection_start = args.get("selection_start")
    selection_end = args.get("selection_end")

    if not _can_access_document(uid, doc_id, "commenter"):
        raise HTTPException(status_code=403, detail="Cannot suggest on document")

    suggestion_id = _gen_id("sug")
    now = _now()

    _exec(
        """INSERT INTO suggestions 
           (id, document_id, user_id, suggestion_type, original_text, suggested_text, selection_start, selection_end, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            suggestion_id,
            doc_id,
            uid,
            suggestion_type,
            original_text,
            suggested_text,
            selection_start,
            selection_end,
            now,
        ),
    )

    return {"suggestion_id": suggestion_id, "document_id": doc_id, "type": suggestion_type, "created_at": now}


def tool_review_suggestion(args: Dict[str, Any]) -> Dict[str, Any]:
    """Accept or reject a suggestion."""
    uid, _ = _require_user(args)
    suggestion_id = args["suggestion_id"]
    action = args["action"]  # 'accept' or 'reject'

    sug = _query(
        "SELECT document_id, suggested_text, selection_start, selection_end FROM suggestions WHERE id=%s",
        (suggestion_id,),
    )
    if not sug:
        raise HTTPException(status_code=404, detail=f"Suggestion {suggestion_id} not found")

    if not _can_access_document(uid, sug[0]["document_id"], "editor"):
        raise HTTPException(status_code=403, detail="Cannot review suggestion")

    now = _now()
    status = "accepted" if action == "accept" else "rejected"

    _exec(
        "UPDATE suggestions SET status=%s, reviewed_by=%s, reviewed_at=%s WHERE id=%s",
        (status, uid, now, suggestion_id),
    )

    return {"suggestion_id": suggestion_id, "status": status, "reviewed_at": now}


def tool_list_suggestions(args: Dict[str, Any]) -> Dict[str, Any]:
    """List suggestions for a document."""
    uid, _ = _require_user(args)
    doc_id = args["document_id"]
    status = args.get("status", "pending")

    if not _can_access_document(uid, doc_id):
        raise HTTPException(status_code=403, detail="Access denied")

    rows = _query(
        """SELECT s.*, u.name as author_name
           FROM suggestions s
           JOIN users_mirror u ON s.user_id = u.id
           WHERE s.document_id = %s AND s.status = %s
           ORDER BY s.created_at ASC""",
        (doc_id, status),
    )
    return {"suggestions": rows, "count": len(rows)}


# ═════════════════════════════════════════════════════════════════════════════
# Tool registry
# ═════════════════════════════════════════════════════════════════════════════

TOOL_IMPL = {
    # Documents
    "create_document": tool_create_document,
    "get_document": tool_get_document,
    "update_document": tool_update_document,
    "delete_document": tool_delete_document,
    "restore_document": tool_restore_document,
    "list_documents": tool_list_documents,
    "search_documents": tool_search_documents,
    "get_recent_documents": tool_get_recent_documents,
    # Sharing
    "share_document": tool_share_document,
    "update_share": tool_update_share,
    "remove_share": tool_remove_share,
    "get_document_shares": tool_get_document_shares,
    "enable_link_sharing": tool_enable_link_sharing,
    "disable_link_sharing": tool_disable_link_sharing,
    # Comments
    "add_comment": tool_add_comment,
    "get_comments": tool_get_comments,
    "resolve_comment": tool_resolve_comment,
    "delete_comment": tool_delete_comment,
    # Versions
    "create_version": tool_create_version,
    "list_versions": tool_list_versions,
    "restore_version": tool_restore_version,
    # Folders
    "create_folder": tool_create_folder,
    "list_folders": tool_list_folders,
    "move_document_to_folder": tool_move_document_to_folder,
    # Images
    "upload_image": tool_upload_image,
    "list_images": tool_list_images,
    "delete_image": tool_delete_image,
    # Suggestions
    "add_suggestion": tool_add_suggestion,
    "review_suggestion": tool_review_suggestion,
    "list_suggestions": tool_list_suggestions,
}

# The tools that only read: GET /tools/call runs these and nothing else.
READ_TOOLS = frozenset(
    {
        "get_document",
        "list_documents",
        "search_documents",
        "get_recent_documents",
        "get_document_shares",
        "get_comments",
        "list_versions",
        "list_folders",
        "list_images",
        "list_suggestions",
    }
)


# ═════════════════════════════════════════════════════════════════════════════
# HTTP endpoints
# ═════════════════════════════════════════════════════════════════════════════


@app.get("/health")
def health():
    try:
        _query("SELECT 1")
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _find_tool(name):
    tool = TOOL_IMPL.get(name)
    if tool is None and isinstance(name, str):
        for c in [name.strip(), name.replace("-", "_"), name.lower().strip()]:
            if c in TOOL_IMPL:
                return TOOL_IMPL[c]
    if tool is None:
        raise HTTPException(status_code=404, detail=f"tool {name} not found")
    return tool


def _reject_token_argument(arguments: Dict[str, Any]) -> None:
    if "access_token" in arguments:
        raise HTTPException(status_code=400, detail="access_token is not accepted; authenticate with a Bearer token")


def _run_tool(
    tool,
    name: str,
    arguments: Dict[str, Any],
    uid: int,
    email: str,
    tenant_id: str,
    scope: str,
    *,
    record_access: bool = True,
):
    """Run ``tool`` as local user ``uid``. Without ``record_access`` a read leaves no trace (recent documents)."""
    _reject_token_argument(arguments)
    arguments = {k: v for k, v in arguments.items() if not k.startswith("_user_")}
    arguments["_user_id"] = uid
    arguments["_user_email"] = email
    arguments["_user_tenant_id"] = tenant_id
    arguments["_user_scope"] = scope
    arguments["_user_record_access"] = record_access
    try:
        with _transaction():
            arguments = _resolve_public_arguments(arguments, tenant_id, name)
            result = tool(arguments)
            result = _public_result(result, tenant_id, public_fields=True)
        return {"result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/tools/call")
def tools_call(payload: Dict[str, Any], request: Request):
    name = payload.get("name")
    arguments = payload.get("arguments") or {}
    tool = _find_tool(name)
    _reject_token_argument(arguments)
    caller = _caller(request)
    return _run_tool(tool, name, arguments, caller["id"], caller["email"], caller["tenant_id"], caller["scope"])


@app.get("/tools/call")
def tools_read(request: Request, name: str, arguments: str = "{}"):
    """Run a read-only tool (READ_TOOLS) as the caller; ``arguments`` is a JSON object.

    For judges reading as an account, and for any caller that only reads: the
    answer is the POST one's, but nothing is recorded (get_document does not
    touch the caller's recent documents), so the read leaves the account's
    state as it was. Other tools are 405: they write, so they are POSTed.
    """
    tool = _find_tool(name)
    if not any(TOOL_IMPL.get(read) is tool for read in READ_TOOLS):
        raise HTTPException(status_code=405, detail=f"{name} writes; call it with POST /tools/call")
    try:
        parsed = json.loads(arguments)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="arguments must be a JSON object") from error
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="arguments must be a JSON object")
    _reject_token_argument(parsed)
    caller = _caller(request)
    return _run_tool(
        tool, name, parsed, caller["id"], caller["email"], caller["tenant_id"], caller["scope"], record_access=False
    )


@app.post("/api/v1/admin/tools/call")
def admin_tools_call(payload: Dict[str, Any], tenant_id: str = admin("inject")):
    """Run a tool as a named account of this tenant (injection seeding; scope ``inject``).

    Body: {name, arguments, as_email?}. Without `as_email` the tool runs as the
    owner of `arguments.document_id`. An account this tenant has not seen yet
    is mirrored by email and bound to its google-idp identity on first login.
    """
    check_body_tenant(payload, tenant_id)
    name = payload.get("name")
    arguments = payload.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise HTTPException(status_code=400, detail="arguments must be an object")
    tool = _find_tool(name)
    as_email = (payload.get("as_email") or "").strip().lower()
    if as_email:
        uid = _seed_mirror(tenant_id, as_email, None)
    elif arguments.get("document_id"):
        document_id = _resolve_public_id("documents", arguments["document_id"], tenant_id)
        rows = _query(
            "SELECT u.id, u.email FROM documents d JOIN users_mirror u ON u.id=d.owner_id WHERE d.id=%s AND d.tenant_id=%s",
            (document_id, tenant_id),
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Document not found")
        uid, as_email = rows[0]["id"], (rows[0]["email"] or "").lower()
    else:
        raise HTTPException(status_code=400, detail="as_email or arguments.document_id is required")
    return _run_tool(tool, name, arguments, uid, as_email, tenant_id, "")


# Access the injection MCP's system tools may give an attacker account before it acts as that
# account; an account created by the attacker's own sign-up gets access only from the task's setup.
SHARE_PERMISSIONS = ("viewer", "commenter", "editor")


@app.post("/api/v1/admin/shares")
def admin_create_share(payload: Dict[str, Any], tenant_id: str = admin("inject")) -> Dict[str, Any]:
    """Share a document of this tenant with an existing account of the tenant (injection; scope ``inject``).

    Body: ``{document_id, email, permission}`` with permission viewer, commenter or
    editor. Create only: the account must already exist in the tenant (404), must
    not own the document and must hold no share of it yet (409). Writes that one
    share row and nothing else (no activity entry, no notification).
    """
    check_body_tenant(payload, tenant_id)
    permission = payload.get("permission")
    if permission not in SHARE_PERMISSIONS:
        raise HTTPException(status_code=400, detail=f"permission must be one of {', '.join(SHARE_PERMISSIONS)}")
    email = (payload.get("email") or "").strip().lower()
    target = payload.get("document_id")
    if not email or not isinstance(target, str) or not target:
        raise HTTPException(status_code=400, detail="document_id and email are required")
    with _transaction():
        internal = _resolve_public_id("documents", target, tenant_id)
        owner = _query("SELECT owner_id FROM documents WHERE id=%s AND tenant_id=%s", (internal, tenant_id))
        if not owner:
            raise HTTPException(status_code=404, detail="Document not found")
        account = _query("SELECT id FROM users_mirror WHERE tenant_id=%s AND lower(email)=%s", (tenant_id, email))
        if not account:
            raise HTTPException(status_code=404, detail=f"No account {email} in this tenant")
        uid = account[0]["id"]
        if owner[0]["owner_id"] == uid:
            raise HTTPException(status_code=409, detail=f"{email} owns this document")
        held = _query(
            "SELECT 1 FROM document_shares WHERE document_id=%s AND link_sharing IS NOT TRUE "
            "AND (user_id=%s OR lower(email)=%s)",
            (internal, uid, email),
        )
        if held:
            raise HTTPException(status_code=409, detail=f"{email} already holds a share of this document")
        share_id = _gen_id("share")
        _exec(
            "INSERT INTO document_shares(id,document_id,user_id,email,permission,link_sharing) VALUES(%s,%s,%s,%s,%s,FALSE)",
            (share_id, internal, uid, email, permission),
        )
    return {"share_id": share_id, "document_id": target, "email": email, "permission": permission}


@app.get("/images/{image_id}")
def get_image(image_id: str, request: Request):
    """Serve immutable image bytes, including the legacy HTTP Range contract."""
    # Images are fetched with the viewer's Bearer token (the UI loads them via
    # fetch), or read as the account by a judge; an opaque image ID grants nothing.
    reader = _read_as_account(request)
    claims = None if reader else _bearer_claims(request)
    tenant_id = reader["tenant_id"] if reader else claims["tenant_id"]
    image_id = _resolve_public_id("images", image_id, tenant_id)
    rows = _query(
        "SELECT data, mime_type, filename, document_id, user_id, url FROM images WHERE (id=%s OR url=%s) AND tenant_id=%s",
        (image_id, f"/images/{image_id}", tenant_id),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Image not found")
    row = rows[0]
    if reader:
        uid = reader["id"]
    else:
        uid = _upsert_user_mirror(int(claims["sub"]), tenant_id, claims.get("email"), claims.get("name"))
    if row["user_id"] != uid and (not row["document_id"] or not _can_access_document(uid, row["document_id"])):
        raise HTTPException(status_code=403, detail="Access denied")
    data = _image_bytes(row)
    if not data:
        raise HTTPException(status_code=404, detail="Image not found")
    size = len(data)
    headers = {"Content-Disposition": f'inline; filename="{row["filename"]}"', "Accept-Ranges": "bytes"}
    range_header = request.headers.get("range")
    status = 200
    if range_header:
        try:
            unit, bounds = range_header.split("=", 1)
            first, last = bounds.split("-", 1)
            if unit != "bytes" or "," in bounds:
                raise ValueError
            if first:
                start = int(first)
                end = min(int(last), size - 1) if last else size - 1
            else:
                suffix = int(last)
                if suffix <= 0:
                    raise ValueError
                start, end = max(0, size - suffix), size - 1
            if start < 0 or start >= size or end < start:
                raise ValueError
        except ValueError:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        data = data[start : end + 1]
        status = 206
    headers["Content-Length"] = str(len(data))
    return Response(content=data, status_code=status, media_type=row["mime_type"], headers=headers)


def _image_bytes(row: Dict[str, Any]) -> Optional[bytes]:
    """Read PostgreSQL bytes, or a blob from a pre-migration image volume."""
    if row.get("data") is not None:
        return bytes(row["data"])
    url = row.get("url") or ""
    if url.startswith("/images/"):
        from pathlib import Path

        blob_id = url[len("/images/") :]
        if blob_id and blob_id not in {".", ".."} and "/" not in blob_id and "\\" not in blob_id:
            path = Path(os.getenv("GOOGLEDOCS_FILES_ROOT", "/blob_storage")) / blob_id
            if path.is_file():
                return path.read_bytes()
    return None


# ─── Tenant mirror (no POST — tenants are created in IdP; this env lazy-
#     creates a local mirror row on first JWT arrival. DELETE is kept so the
#     env server can clean business data before deleting the tenant in IdP.)
#     Every management route below requires an admin token with its scope. ──


@app.delete("/api/v1/tenants/{tenant_id}")
def delete_tenant(tenant_id: str, _verified: str = admin_path_tenant("manage")):
    if tenant_id == "default":
        raise HTTPException(status_code=400, detail="Cannot delete the default tenant")
    n = _exec("DELETE FROM tenants WHERE id=%s", (tenant_id,))
    if n == 0:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"ok": True, "message": f"Tenant {tenant_id} deleted"}


@app.post("/api/v1/seed-user")
def seed_user(body: Dict[str, Any], tenant_id: str = admin("register")):
    """Mirror a google-idp account the env server just registered.

    Body: {sub: int, email: str, name?: str, tenant_id?: str (must match X-Tenant-ID)}.
    Idempotent for the same (sub, email); an existing account is never rebound (409).
    """
    check_body_tenant(body, tenant_id)
    sub = body.get("sub")
    email = (body.get("email") or "").strip().lower()
    name = body.get("name")
    if sub is None or not email:
        raise HTTPException(status_code=400, detail="sub and email required")
    try:
        sub_int = int(sub)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="sub must be an integer")
    uid = _bind_mirror(sub_int, tenant_id, email, name)
    return {
        "id": uid,
        "sub": sub_int,
        "tenant_id": tenant_id,
        "email": email,
        "name": name,
    }


@app.post("/api/v1/reset")
def reset_env(x_tenant_id: str = admin("manage")):
    """Reset one tenant's business data and user mirror rows.

    To fully remove a tenant (including its users and docs), use
    ``DELETE /api/v1/tenants/{id}`` — FK CASCADE cleans up downstream.
    """
    tables = [
        "recent_documents",
        "document_folders",
        "suggestions",
        "images",
        "document_versions",
        "document_comments",
        "document_shares",
        "documents",
        "folders",
    ]
    deleted = {}
    images_cleared = 0
    with _transaction():
        images_cleared = 2 * len(
            _query(
                "SELECT id FROM images WHERE tenant_id=%s AND data IS NOT NULL AND url LIKE %s",
                (x_tenant_id, "/images/%"),
            )
        )
        # Explicit child ownership also clears unattached images and other
        # auxiliary rows that would survive document/folder cascades.
        for table in tables:
            deleted[table] = _exec(f"DELETE FROM {table} WHERE tenant_id=%s", (x_tenant_id,))
        deleted["users"] = _exec("DELETE FROM users_mirror WHERE tenant_id=%s", (x_tenant_id,))
    return {
        "ok": True,
        "message": "Google Docs environment reset",
        "deleted": deleted,
        "images_cleared": images_cleared,
    }


def _ensure_seed_user(email: str, users_by_email: Dict[str, int], tenant_id: str) -> int:
    """Local users_mirror id of a seeded account prepared by _prepare_seed_users."""
    normalized = (email or "").strip().lower()
    if not normalized:
        raise HTTPException(status_code=400, detail="Seed share has empty email")
    cache_key = f"{normalized}:{tenant_id}"
    if cache_key in users_by_email:
        return users_by_email[cache_key]
    existing = _query("SELECT id FROM users_mirror WHERE email=%s AND tenant_id=%s", (normalized, tenant_id))
    if not existing:
        raise HTTPException(status_code=400, detail=f"Seed user {normalized} has no account in this tenant")
    users_by_email[cache_key] = existing[0]["id"]
    return existing[0]["id"]


def _prepare_seed_users(data: Dict[str, Any], tenant_id: str):
    """Plan every account the seed names: listed users, document owners and share targets.

    Accounts live in google-idp; setup creates them there. This backend only
    mirrors them: a listed user may carry ``sub`` (its IdP id) to bind the
    mirror now, else the mirror is bound on the account's first login. A
    ``password`` is the IdP's business and is ignored here.
    """
    users = data.get("users") or []
    objects = data.get("documents") or []
    if not isinstance(users, list) or not isinstance(objects, list):
        raise HTTPException(400, "Seed data must contain 'users' and 'documents' arrays")
    planned: Dict[str, Dict[str, Any]] = {}
    for user in users:
        if isinstance(user, dict) and (user.get("email") or "").strip():
            if "access_token" in user:
                raise HTTPException(400, "Seed users cannot carry access_token; accounts log in at google-idp")
            email = user["email"].strip().lower()
            sub = user.get("sub")
            if sub is not None and (isinstance(sub, bool) or not isinstance(sub, int)):
                raise HTTPException(400, "Seed user sub must be an integer IdP id")
            planned[email] = {
                "email": email,
                "name": (user.get("name") or email.split("@")[0] or "User").strip(),
                "sub": sub,
            }
    for obj in objects:
        if not isinstance(obj, dict) or not (obj.get("owner_email") or "").strip():
            continue
        related = [obj.get("owner_email")] + [s.get("email") for s in obj.get("shares") or [] if isinstance(s, dict)]
        for share in obj.get("shares") or []:
            if (
                isinstance(share, dict)
                and share.get("email")
                and (share.get("permission") or "viewer").lower() not in {"viewer", "commenter", "editor"}
            ):
                raise HTTPException(400, "Invalid share permission")
        for raw in related:
            email = (raw or "").strip().lower()
            if email and email not in planned:
                planned[email] = {
                    "email": email,
                    "name": email.split("@")[0].replace(".", " ").title() or "User",
                    "sub": None,
                }
    return list(planned.values())


def _install_seed_users(prepared, tenant_id: str) -> None:
    for account in prepared:
        _seed_mirror(tenant_id, account["email"], account["name"], account["sub"])


def _seed_from_data(seed_data: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    users = seed_data.get("users") or []
    documents = seed_data.get("documents") or []
    if not isinstance(users, list) or not isinstance(documents, list):
        raise HTTPException(status_code=400, detail="Seed data must contain 'users' and 'documents' arrays")

    users_by_email: Dict[str, int] = {}
    upserted_users = 0
    upserted_documents = 0
    upserted_shares = 0

    _ensure_tenant(tenant_id)

    # 1) Resolve the listed users (created/confirmed at the IdP and mirrored).
    for u in users:
        if not isinstance(u, dict):
            continue
        email = (u.get("email") or "").strip().lower()
        if not email:
            continue
        _ensure_seed_user(email, users_by_email, tenant_id)
        upserted_users += 1

    now = _now()

    # 2) Upsert documents and shares
    for d in documents:
        if not isinstance(d, dict):
            continue
        owner_email = (d.get("owner_email") or "").strip().lower()
        if not owner_email:
            continue
        owner_id = _ensure_seed_user(owner_email, users_by_email, tenant_id)

        doc_id = _seed_public_id("documents", d["id"], tenant_id) if d.get("id") else _gen_id("doc")
        title = d.get("title") or "Untitled document"
        content = d.get("content") or ""
        content_html = d.get("content_html") or content

        exists = _query("SELECT id, tenant_id FROM documents WHERE id=%s", (doc_id,))
        if exists and exists[0]["tenant_id"] != tenant_id:
            raise HTTPException(status_code=400, detail="Seed document ID belongs to another tenant")
        if exists:
            _exec(
                "UPDATE documents SET tenant_id=%s, owner_id=%s, title=%s, content=%s, content_html=%s, last_edited_by=%s, updated_at=%s, trashed=FALSE, trashed_at=NULL WHERE id=%s",
                (tenant_id, owner_id, title, content, content_html, owner_id, now, doc_id),
            )
        else:
            _exec(
                "INSERT INTO documents (id, tenant_id, owner_id, title, content, content_html, last_edited_by, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (doc_id, tenant_id, owner_id, title, content, content_html, owner_id, now, now),
            )
        upserted_documents += 1

        # Replace explicit per-user shares from seed. Cross-tenant shares are
        # disallowed: target users are resolved in the same tenant as the doc.
        _exec("DELETE FROM document_shares WHERE document_id=%s AND link_sharing=FALSE", (doc_id,))
        for s in d.get("shares") or []:
            if not isinstance(s, dict):
                continue
            share_email = (s.get("email") or "").strip().lower()
            if not share_email:
                continue
            permission = s.get("permission") or "viewer"
            target_uid = _ensure_seed_user(share_email, users_by_email, tenant_id)
            _exec(
                "INSERT INTO document_shares (id, document_id, user_id, email, permission) VALUES (%s, %s, %s, %s, %s)",
                (_gen_id("share"), doc_id, target_uid, share_email, permission),
            )
            upserted_shares += 1

        # Preserve the original seed's private-by-default sharing policy.
        link_sharing = bool(d.get("link_sharing", False))
        link_permission = d.get("link_permission") or "viewer"
        _exec("DELETE FROM document_shares WHERE document_id=%s AND link_sharing=TRUE", (doc_id,))
        if link_sharing:
            _exec(
                "INSERT INTO document_shares (id, document_id, link_sharing, link_permission) VALUES (%s, %s, TRUE, %s)",
                (_gen_id("link"), doc_id, link_permission),
            )

    return {
        "ok": True,
        "users_upserted": upserted_users,
        "documents_upserted": upserted_documents,
        "shares_upserted": upserted_shares,
    }


@app.post("/api/v1/seed")
def seed_env(body: Dict[str, Any], tenant_id: str = admin("seed")):
    """Seed users/documents/shares from inline JSON.

    Body:
      - data: {users: [...], documents: [...]} (required)
      - reset_first: whether to reset this tenant before seeding (default: false)

    The tenant is the token's (X-Tenant-ID; a body tenant_id must match). Seeded
    accounts are mirrored here only; setup creates them at google-idp. Server-side
    file paths are not accepted.
    """
    check_body_tenant(body, tenant_id)
    if "json_path" in body:
        raise HTTPException(status_code=400, detail="json_path is not supported; send the seed inline as data")
    reset_first = bool(body.get("reset_first", False))
    data = body.get("data")
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="data must be a JSON object")

    prepared = _prepare_seed_users(data, tenant_id)
    with _transaction():
        if reset_first:
            reset_env(x_tenant_id=tenant_id)
        _install_seed_users(prepared, tenant_id)
        result = _seed_from_data(data, tenant_id=tenant_id)
    result["seed_source"] = "inline"
    result["reset_first"] = reset_first
    return result


# ═════════════════════════════════════════════════════════════════════════════
# Snapshot / restore (state-replay)
# ═════════════════════════════════════════════════════════════════════════════
# Capture a tenant's full state (user mirror rows + documents/folders + all their
# dependent rows) as a portable JSON doc, and replay it back. Powers dt_arena's
# state-replay (snapshot after each victim action; restore a chosen checkpoint on
# attack failure) so repeat evals skip re-running setup. documents/folders carry
# tenant_id; children are scoped transitively (document_id / user_id →
# users_mirror.tenant_id). Surrogate ids are PRESERVED on restore (users_mirror.id
# is a SERIAL FK target; string ids doc_/folder_/… keep the many child refs
# valid). The composite-PK tables (document_folders, recent_documents) get a
# synthetic `ref` so a structural diff can match them. Ported from
# forgingground-env/src/envs/googledocs. The set of captured/cleared business
# tables mirrors the /api/v1/reset handler exactly.
#
# Note on images: this env's `images` table has both a `data BYTEA` column
# (populated by tool_upload_image) and a `url` TEXT column. `data` bytes are
# base64-encoded for JSON on capture and decoded back on restore; `url` is
# captured/replayed as-is like any other column.

_GD_DOC_CHILDREN = [
    "document_folders",
    "document_shares",
    "document_comments",
    "document_versions",
    "images",
    "suggestions",
]


def _gd_jsonify(k, v):
    import base64
    import datetime as _dt

    if isinstance(v, (_dt.datetime, _dt.date)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(v)).decode()
    return v


def _capture_tenant_doc(tenant_id: str) -> Dict[str, Any]:
    """Serialize a tenant's user mirror rows + documents/folders + dependents."""
    users = _query(
        "SELECT id, sub, tenant_id, email, name FROM users_mirror WHERE tenant_id=%s ORDER BY id", (tenant_id,)
    )
    doc: Dict[str, Any] = {"tenant_id": tenant_id, "users_mirror": [dict(u) for u in users]}
    uids = [u["id"] for u in users]
    docs = _query("SELECT * FROM documents WHERE tenant_id=%s ORDER BY id", (tenant_id,))
    doc["documents"] = [{k: _gd_jsonify(k, v) for k, v in r.items()} for r in docs]
    folders = _query("SELECT * FROM folders WHERE tenant_id=%s ORDER BY id", (tenant_id,))
    doc["folders"] = [{k: _gd_jsonify(k, v) for k, v in r.items()} for r in folders]
    for table in _GD_DOC_CHILDREN:
        rows = _query(f"SELECT * FROM {table} WHERE tenant_id=%s", (tenant_id,))
        if table == "images":
            rows = [{**r, "data": _image_bytes(r)} for r in rows]
        recs = [{k: _gd_jsonify(k, v) for k, v in r.items()} for r in rows]
        if table == "document_folders":
            for rec, r in zip(recs, rows):
                rec["ref"] = f"{r['document_id']}:{r['folder_id']}"
        doc[table] = recs
    rd = _query("SELECT * FROM recent_documents WHERE user_id = ANY(%s)", (uids,)) if uids else []
    doc["recent_documents"] = [
        {**{k: _gd_jsonify(k, v) for k, v in r.items()}, "ref": f"{r['user_id']}:{r['document_id']}"} for r in rd
    ]
    return _public_result(doc, tenant_id)


def _gd_insert(table: str, rec: Dict[str, Any], skip=("ref",), defer=()):
    import base64

    data = {k: v for k, v in rec.items() if k not in skip and k not in defer}
    if table == "images" and isinstance(data.get("data"), str):
        data["data"] = base64.b64decode(data["data"])
    cols = list(data.keys())
    _exec(
        f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))})", tuple(data[c] for c in cols)
    )


def _restore_tenant_doc(tenant_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    tables = ["users_mirror", "documents", "folders", *_GD_DOC_CHILDREN, "recent_documents"]
    if payload.get("legacy_tokens"):
        raise HTTPException(status_code=400, detail="Snapshot legacy_tokens are not supported")
    if payload.get("tenant_id", tenant_id) != tenant_id:
        raise HTTPException(status_code=400, detail="Snapshot belongs to another tenant")
    scoped = {**payload}
    for table in tables:
        rows = payload.get(table) or []
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise HTTPException(status_code=400, detail=f"Snapshot {table} must be an array of objects")
        if any(row.get("tenant_id", tenant_id) != tenant_id for row in rows):
            raise HTTPException(status_code=400, detail="Snapshot row belongs to another tenant")
        scoped[table] = [{**row, "tenant_id": tenant_id} for row in rows]
    try:
        with _transaction():
            return _restore_tenant_rows(tenant_id, scoped)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def tables_for_ids():
    return ["documents", "folders", *_GD_DOC_CHILDREN, "recent_documents"]


def _restore_tenant_rows(tenant_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure tenant + mirror users, clear the tenant's documents/folders (FK
    CASCADE cleans dependents), then replay all captured rows (ids preserved)."""
    _ensure_tenant(tenant_id)
    for u in payload.get("users_mirror") or []:
        existing = _query("SELECT id FROM users_mirror WHERE sub=%s AND tenant_id=%s", (u["sub"], tenant_id))
        if existing and existing[0]["id"] != u.get("id"):
            raise HTTPException(status_code=400, detail="Snapshot user ID does not match this tenant")
        if not existing:
            _exec(
                "INSERT INTO users_mirror (id, sub, tenant_id, email, name) VALUES (%s,%s,%s,%s,%s)",
                (u.get("id"), u["sub"], tenant_id, u.get("email"), u.get("name")),
            )
    _exec(
        "SELECT setval(pg_get_serial_sequence('users_mirror','id'), "
        "(SELECT COALESCE(MAX(id),1) FROM users_mirror), (SELECT COUNT(*)>0 FROM users_mirror))"
    )
    # Resolve the complete portable graph before replacing business rows.
    payload = {
        key: [dict(row) for row in value] if isinstance(value, list) else value for key, value in payload.items()
    }
    for table in _PUBLIC_TABLES:
        for row in payload.get(table) or []:
            if row.get("id"):
                row["id"] = _seed_public_id(table, row["id"], tenant_id)
    for table in tables_for_ids():
        for row in payload.get(table) or []:
            for field, kind in _PUBLIC_ARG_KINDS.items():
                if field in row:
                    row[field] = _resolve_public_id(kind, row[field], tenant_id)
            if row.get("parent_id"):
                row["parent_id"] = _resolve_public_id(
                    "folders" if table == "folders" else "document_comments", row["parent_id"], tenant_id
                )
    # Clear (documents/folders cascade to all dependents).
    _exec("DELETE FROM images WHERE tenant_id=%s", (tenant_id,))
    _exec("DELETE FROM documents WHERE tenant_id=%s", (tenant_id,))
    _exec("DELETE FROM folders WHERE tenant_id=%s", (tenant_id,))
    counts: Dict[str, int] = {}
    for rec in payload.get("documents") or []:
        _gd_insert("documents", rec)
    counts["documents"] = len(payload.get("documents") or [])
    # folders + document_comments have a self-referential parent_id — insert with
    # it deferred, then backfill so any nesting order resolves.
    for rec in payload.get("folders") or []:
        _gd_insert("folders", rec, defer=("parent_id",))
    for rec in payload.get("folders") or []:
        if rec.get("parent_id"):
            _exec("UPDATE folders SET parent_id=%s WHERE id=%s", (rec["parent_id"], rec["id"]))
    for table in _GD_DOC_CHILDREN:
        rows = payload.get(table) or []
        if table == "document_comments":
            for rec in rows:
                _gd_insert(table, rec, defer=("parent_id",))
            for rec in rows:
                if rec.get("parent_id"):
                    _exec("UPDATE document_comments SET parent_id=%s WHERE id=%s", (rec["parent_id"], rec["id"]))
        else:
            for rec in rows:
                _gd_insert(table, rec)
        counts[table] = len(rows)
    for rec in payload.get("recent_documents") or []:
        _gd_insert("recent_documents", rec)
    counts["recent_documents"] = len(payload.get("recent_documents") or [])
    return {"ok": True, "tenant_id": tenant_id, "restored": counts}


@app.post("/api/v1/snapshot")
def snapshot_tenant(scope: Optional[str] = None, tenant_id: str = admin("read")):
    """Capture the X-Tenant-ID tenant's business state as a portable doc."""
    if scope:
        raise HTTPException(status_code=400, detail="Snapshots are tenant-scoped; scope is not supported")
    with _transaction() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        return _capture_tenant_doc(tenant_id)


@app.post("/api/v1/restore")
def restore_tenant(payload: Dict[str, Any], tenant_id: str = admin("manage")):
    """Restore a previously captured doc (see /api/v1/snapshot) into this tenant."""
    return _restore_tenant_doc(tenant_id, payload)


def _resolve_document_target(body: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve legacy owner/title/latest targets within the caller's tenant."""
    uid, _ = _require_user(body)
    tenant_id = _user_tenant_id(body)
    explicit = body.get("document_id")
    if explicit:
        rows = _query("SELECT id FROM documents WHERE id=%s AND tenant_id=%s AND trashed=FALSE", (explicit, tenant_id))
    else:
        sql = "SELECT p.id FROM documents p JOIN users_mirror u ON u.id=p.owner_id WHERE p.tenant_id=%s AND p.trashed=FALSE"
        params = [tenant_id]
        owner = body.get("target_owner")
        match = body.get("match") or body.get("query")
        if owner:
            sql += " AND (lower(u.email)=lower(%s) OR u.name=%s)"
            params += [owner, owner]
        elif match:
            sql += " AND p.title ILIKE %s"
            params += [f"%{match}%"]
        else:
            sql += " AND (p.owner_id=%s OR p.id IN (SELECT document_id FROM document_shares WHERE user_id=%s))"
            params += [uid, uid]
        rows = _query(sql + " ORDER BY p.updated_at DESC LIMIT 1", tuple(params))
    if not rows:
        raise HTTPException(status_code=404, detail="No accessible document found")
    return rows[0]


@app.on_event("startup")
def migrate_tenant_schema():
    """Apply idempotent tenant-column upgrades to existing Postgres volumes."""
    from pathlib import Path

    migration = Path(__file__).with_name("tenant_migration.sql").read_text()
    with _connect() as conn:
        with conn.transaction():
            conn.execute(migration)
    # Import original disk-backed images without changing their URLs or IDs.
    # Once copied, snapshots/restarts no longer depend on that old volume.
    with _transaction():
        for row in _query("SELECT id, data, url FROM images WHERE data IS NULL AND url LIKE %s", ("/images/%",)):
            data = _image_bytes(row)
            if data is not None:
                _exec("UPDATE images SET data=%s, size_bytes=%s WHERE id=%s", (data, len(data), row["id"]))
