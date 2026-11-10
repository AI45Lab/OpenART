"""Verify DTAP admin tokens and answer the deployment ownership challenge.

Canonical reference implementation for native backends. Vendor this file
byte-identical into a backend; a repository test compares every copy. It
depends only on ``cryptography``.

Configuration is read from the environment when this module is imported and an
import with a missing or invalid value raises :class:`ConfigError`, so a
backend that imports it refuses to start without its admin configuration:

- ``DTAP_ADMIN_PUBLIC_KEY``: the deployment's RSA public key (PEM).
- ``DTAP_ADMIN_AUDIENCE``: this backend's audience (its Compose service name).
- ``DTAP_BACKEND_PROOF_KEY``: this backend's ownership-proof key.

An admin token is a JWT signed with RS256 by the env server and sent in the
``X-DTAP-Admin-Token`` header (never ``Authorization``). ``verify`` checks the
signature against the configured key only, the header ``kid``, ``iss``,
``aud`` == this backend, ``iat``/``exp`` with 30 seconds of clock skew, a
lifetime of at most 3600 seconds, ``tenant`` == the request's tenant, and that
``scope`` holds the scope the endpoint requires (or one of the scopes it
accepts). A missing token raises :class:`MissingToken` (HTTP 401); every other
failure raises an :class:`AdminAuthError` subclass whose ``status`` is 403.

A judge reads an account's state as that account sees it with a read-as
request: the account's email in ``X-DTAP-Read-As``, the tenant in
``X-Tenant-ID`` and a token holding the ``read`` scope in
``X-DTAP-Admin-Token``. :func:`read_as` authorizes it for a user route, which
then serves the account's own view; only ``GET`` and ``HEAD`` are allowed. A
request without ``X-DTAP-Read-As`` is an ordinary user request, and the admin
token alone still authenticates no user.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

HEADER = "X-DTAP-Admin-Token"
READ_AS_HEADER = "X-DTAP-Read-As"
TENANT_HEADER = "X-Tenant-ID"
READ_AS_METHODS = ("GET", "HEAD")
READ_AS_MAX_LENGTH = 320
ISSUER = "dtap-env-server"
ALGORITHM = "RS256"
SCOPES = ("manage", "register", "seed", "read", "inject", "signup", "session")
MAX_LIFETIME = 3600
CLOCK_SKEW = 30
MIN_KEY_BITS = 2048
PROOF_PATH = "/.well-known/dtap-deployment"
PROOF_CONTEXT = "dtap-deployment:"
PUBLIC_KEY_ENV = "DTAP_ADMIN_PUBLIC_KEY"
AUDIENCE_ENV = "DTAP_ADMIN_AUDIENCE"
PROOF_KEY_ENV = "DTAP_BACKEND_PROOF_KEY"
REQUIRED_CLAIMS = ("iss", "aud", "tenant", "scope", "iat", "exp", "jti")

_AUDIENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_NONCE = re.compile(r"[0-9A-Fa-f]{1,128}")
_SEGMENT = re.compile(r"[A-Za-z0-9_-]*")


class ConfigError(RuntimeError):
    """The admin configuration is missing or invalid; the backend must not start."""


class InvalidNonce(ValueError):
    """The ownership challenge nonce is not 1-128 hex characters (answer HTTP 400)."""

    status = 400
    code = "invalid_nonce"


class AdminAuthError(Exception):
    """An admin request is not authorized. ``status`` is the HTTP status to answer with."""

    status = 403
    code = "invalid_token"


class MissingToken(AdminAuthError):
    """No admin token was sent."""

    status = 401
    code = "missing_token"


class InvalidToken(AdminAuthError):
    """The token is malformed, forged, expired, or meant for another backend."""

    status = 403
    code = "invalid_token"


class TenantMismatch(AdminAuthError):
    """The token is valid but for another tenant than the request names."""

    status = 403
    code = "tenant_mismatch"


class InsufficientScope(AdminAuthError):
    """The token is valid but lacks the scope this endpoint requires."""

    status = 403
    code = "insufficient_scope"


class ReadOnly(AdminAuthError):
    """A read-as request asked for anything but ``GET`` or ``HEAD``."""

    status = 403
    code = "read_only"


class InvalidReadAs(AdminAuthError):
    """The ``X-DTAP-Read-As`` value is not an account identifier (answer HTTP 400)."""

    status = 400
    code = "invalid_read_as"


def _b64decode(segment: str) -> bytes:
    if not _SEGMENT.fullmatch(segment) or len(segment) % 4 == 1:
        raise InvalidToken("token segment is not base64url")
    try:
        return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
    except (binascii.Error, ValueError) as error:
        raise InvalidToken("token segment is not base64url") from error


def _json_object(raw: bytes, what: str) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise InvalidToken(f"token {what} is not JSON") from error
    if not isinstance(value, dict):
        raise InvalidToken(f"token {what} is not a JSON object")
    return value


def _integer(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _accepted(scope) -> tuple:
    """The scopes an endpoint accepts: one scope, or a non-empty list of them."""
    accepted = (scope,) if isinstance(scope, str) else tuple(scope) if isinstance(scope, (list, tuple)) else ()
    if not accepted or any(not isinstance(item, str) or item not in SCOPES for item in accepted):
        raise ValueError(f"unknown admin scope {scope!r}; use one of {SCOPES} or a non-empty list of them")
    return accepted


class Verifier:
    """Admin-token verification and ownership proof for one backend audience."""

    def __init__(self, public_key_pem: str, audience: str, proof_key: str):
        if not isinstance(public_key_pem, str) or not public_key_pem.strip():
            raise ConfigError(f"{PUBLIC_KEY_ENV} is empty")
        try:
            key = serialization.load_pem_public_key(public_key_pem.strip().encode())
        except (ValueError, TypeError) as error:
            raise ConfigError(f"{PUBLIC_KEY_ENV} is not a PEM public key") from error
        if not isinstance(key, rsa.RSAPublicKey):
            raise ConfigError(f"{PUBLIC_KEY_ENV} is not an RSA public key")
        if key.key_size < MIN_KEY_BITS:
            raise ConfigError(f"{PUBLIC_KEY_ENV} is shorter than {MIN_KEY_BITS} bits")
        if not isinstance(audience, str) or not _AUDIENCE.fullmatch(audience):
            raise ConfigError(f"{AUDIENCE_ENV} must be 1-128 characters of [A-Za-z0-9_.-]")
        if not isinstance(proof_key, str) or len(proof_key.strip()) < 32 or proof_key != proof_key.strip():
            raise ConfigError(f"{PROOF_KEY_ENV} must be at least 32 characters without surrounding whitespace")
        der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        self._key = key
        self._proof_key = proof_key.encode()
        self.audience = audience
        self.kid = hashlib.sha256(der).hexdigest()[:16]

    def __repr__(self) -> str:
        return f"Verifier(audience={self.audience!r}, kid={self.kid!r})"

    def verify(self, token, tenant: str, scope, *, now: float | None = None) -> dict:
        """Return the token's claims, or raise an :class:`AdminAuthError` subclass.

        ``tenant`` is the tenant the request acts on (``X-Tenant-ID``, path or
        body tenant); ``scope`` is the scope the endpoint requires, or a list of
        scopes any one of which it accepts (``/auth/register`` accepts
        ``["register", "signup"]`` and decides from ``claims["scope"]`` what the
        caller may create).
        """
        accepted = _accepted(scope)
        if token is None or (isinstance(token, str) and not token.strip()):
            raise MissingToken(f"{HEADER} is required")
        if not isinstance(token, str):
            raise InvalidToken("token is not a string")
        parts = token.strip().split(".")
        if len(parts) != 3:
            raise InvalidToken("token is not a JWS compact serialization")
        header = _json_object(_b64decode(parts[0]), "header")
        if header.get("alg") != ALGORITHM:
            raise InvalidToken(f"token algorithm must be {ALGORITHM}")
        if header.get("kid") != self.kid:
            raise InvalidToken("token was signed with another key")
        if "crit" in header or header.get("typ", "JWT") != "JWT":
            raise InvalidToken("token header is not supported")
        signature = _b64decode(parts[2])
        try:
            self._key.verify(signature, f"{parts[0]}.{parts[1]}".encode(), padding.PKCS1v15(), hashes.SHA256())
        except InvalidSignature as error:
            raise InvalidToken("token signature is invalid") from error
        claims = _json_object(_b64decode(parts[1]), "payload")

        missing = [name for name in REQUIRED_CLAIMS if name not in claims]
        if missing:
            raise InvalidToken(f"token is missing claims: {', '.join(missing)}")
        if claims["iss"] != ISSUER:
            raise InvalidToken("token issuer is not the env server")
        if not isinstance(claims["aud"], str) or claims["aud"] != self.audience:
            raise InvalidToken("token is for another backend")
        for name in ("tenant", "scope", "jti"):
            if not isinstance(claims[name], str) or not claims[name]:
                raise InvalidToken(f"token claim {name} must be a non-empty string")
        issued, expires = claims["iat"], claims["exp"]
        if not _integer(issued) or not _integer(expires):
            raise InvalidToken("token iat and exp must be integers")
        if expires <= issued or expires - issued > MAX_LIFETIME:
            raise InvalidToken(f"token lifetime must be 1-{MAX_LIFETIME} seconds")
        current = time.time() if now is None else now
        if issued > current + CLOCK_SKEW:
            raise InvalidToken("token is not yet valid")
        if current >= expires + CLOCK_SKEW:
            raise InvalidToken("token has expired")
        granted = claims["scope"].split(" ")
        if any(item not in SCOPES for item in granted):
            raise InvalidToken("token scope is malformed")

        if not isinstance(tenant, str) or not tenant or claims["tenant"] != tenant:
            raise TenantMismatch("token is for another tenant")
        if not any(item in granted for item in accepted):
            raise InsufficientScope(f"token lacks the {' or '.join(accepted)} scope")
        return claims

    def read_as(self, token, tenant: str, method, email, *, now: float | None = None) -> dict:
        """Authorize a judge's read of ``email``'s own view; return ``{"tenant", "email"}``.

        The token is checked first, exactly as :meth:`verify` with the ``read``
        scope; then ``method`` must be ``GET`` or ``HEAD`` (:class:`ReadOnly`)
        and ``email`` a non-empty single-line value of at most 320 characters
        (:class:`InvalidReadAs`). The email is returned stripped; the backend
        resolves it to an account of ``tenant`` and answers 404 when there is none.
        """
        claims = self.verify(token, tenant, "read", now=now)
        if not isinstance(method, str) or method.upper() not in READ_AS_METHODS:
            raise ReadOnly(f"{READ_AS_HEADER} requests may only {' or '.join(READ_AS_METHODS)}")
        value = email.strip() if isinstance(email, str) else ""
        if not value or len(value) > READ_AS_MAX_LENGTH or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise InvalidReadAs(f"{READ_AS_HEADER} must be one account identifier of 1-{READ_AS_MAX_LENGTH} characters")
        return {"tenant": claims["tenant"], "email": value}

    def prove(self, nonce) -> dict:
        """Answer ``GET /.well-known/dtap-deployment?nonce=<hex>`` with this body."""
        if not isinstance(nonce, str) or not _NONCE.fullmatch(nonce):
            raise InvalidNonce("nonce must be 1-128 hex characters")
        proof = hmac.new(self._proof_key, (PROOF_CONTEXT + nonce).encode(), hashlib.sha256).hexdigest()
        return {"proof": proof, "audience": self.audience}


def config_from_env(environ=None) -> Verifier:
    """Build the verifier from ``DTAP_ADMIN_PUBLIC_KEY``, ``DTAP_ADMIN_AUDIENCE`` and ``DTAP_BACKEND_PROOF_KEY``."""
    environ = os.environ if environ is None else environ
    missing = [name for name in (PUBLIC_KEY_ENV, AUDIENCE_ENV, PROOF_KEY_ENV) if not environ.get(name)]
    if missing:
        raise ConfigError(f"Missing {', '.join(missing)}; start this backend through dtap env up")
    return Verifier(environ[PUBLIC_KEY_ENV], environ[AUDIENCE_ENV], environ[PROOF_KEY_ENV])


# Importing this module refuses a backend without a valid admin configuration.
verifier = config_from_env()


def verify(token, tenant: str, scope) -> dict:
    """Verify ``token`` for ``tenant`` and ``scope`` (one scope or a list) with this backend's configuration."""
    return verifier.verify(token, tenant, scope)


def prove(nonce) -> dict:
    """The ownership-proof response body for ``nonce``."""
    return verifier.prove(nonce)


def read_as(headers, method) -> dict | None:
    """The read-as grant ``{"tenant", "email"}`` of a request, or ``None`` when it sends no ``X-DTAP-Read-As``.

    ``headers`` is the request's case-insensitive header mapping (``request.headers``)
    and ``method`` its HTTP method. Raises like :meth:`Verifier.read_as`.
    """
    email = headers.get(READ_AS_HEADER)
    if email is None:
        return None
    tenant = (headers.get(TENANT_HEADER) or "").strip()
    return verifier.read_as(headers.get(HEADER), tenant, method, email)
