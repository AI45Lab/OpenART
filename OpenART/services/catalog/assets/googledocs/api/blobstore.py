"""Shared id-keyed blob store for binary files / attachments.

Both the Gmail attachment endpoints and the Google Drive file storage use this
so the two envs handle binary blobs identically:

  * each blob is a file ``{root}/{id}`` plus a ``{root}/{id}.json`` sidecar
    holding ``{id, filename, content_type, size, owner_id, created}``;
  * uploads are capped by a per-file limit (413) and a total-staging quota
    (507);
  * blobs older than an optional TTL are swept on access (keeps the area
    bounded);
  * ``clear_all()`` wipes the whole store so an env reset returns to a clean
    baseline (task runs are reproducible — modified/created files never leak
    across runs);
  * downloads are id-keyed and ownership-checked by the caller via the sidecar;
    HTTP Range helpers are provided so large blobs stream resumably.

This module is duplicated verbatim into each env's source tree (the envs build
as isolated containers and cannot import a common path), so keep the copies in
``envs/_shared/blobstore.py``, ``envs/googledrive/api/blobstore.py`` and
``envs/gmail/user_service/blobstore.py`` identical.
"""
from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from typing import Any, Dict, Optional, Tuple

_CHUNK = 256 * 1024


class BlobError(Exception):
    """Quota / validation error carrying an HTTP status code + detail."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class BlobStore:
    def __init__(
        self,
        root: str,
        *,
        max_file_bytes: int = 50 * 1024 * 1024,
        max_total_bytes: int = 500 * 1024 * 1024,
        ttl_seconds: Optional[int] = None,
        url_prefix: str = "/api/v1/files",
    ):
        self.root = root
        self.max_file_bytes = int(max_file_bytes)
        self.max_total_bytes = int(max_total_bytes)
        self.ttl_seconds = ttl_seconds
        self.url_prefix = url_prefix.rstrip("/")
        try:
            os.makedirs(self.root, exist_ok=True)
        except Exception:
            pass

    # ---- paths / urls -----------------------------------------------------
    def path(self, blob_id: str) -> str:
        return os.path.join(self.root, blob_id)

    def meta_path(self, blob_id: str) -> str:
        return self.path(blob_id) + ".json"

    def url(self, blob_id: str) -> str:
        return f"{self.url_prefix}/{blob_id}"

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex

    # ---- housekeeping -----------------------------------------------------
    def sweep(self) -> int:
        """Delete blobs older than the TTL (if set); return live total bytes."""
        now = time.time()
        total = 0
        try:
            entries = list(os.scandir(self.root))
        except FileNotFoundError:
            return 0
        for entry in entries:
            if not entry.is_file() or entry.name.endswith(".json"):
                continue
            try:
                st = entry.stat()
            except FileNotFoundError:
                continue
            if self.ttl_seconds is not None and now - st.st_mtime > self.ttl_seconds:
                for p in (entry.path, entry.path + ".json"):
                    try:
                        os.remove(p)
                    except FileNotFoundError:
                        pass
            else:
                total += st.st_size
        return total

    def clear_all(self) -> int:
        """Wipe the entire store (used on env reset). Returns items removed."""
        removed = 0
        try:
            entries = list(os.scandir(self.root))
        except FileNotFoundError:
            return 0
        for entry in entries:
            try:
                if entry.is_dir():
                    shutil.rmtree(entry.path, ignore_errors=True)
                else:
                    os.remove(entry.path)
                removed += 1
            except FileNotFoundError:
                pass
            except Exception:
                pass
        try:
            os.makedirs(self.root, exist_ok=True)
        except Exception:
            pass
        return removed

    # ---- write ------------------------------------------------------------
    def precheck(self, incoming_bytes: int) -> None:
        """Raise BlobError if this upload would breach the per-file or total quota."""
        if incoming_bytes > self.max_file_bytes:
            raise BlobError(413, f"Blob exceeds per-file limit of {self.max_file_bytes} bytes")
        if self.sweep() + incoming_bytes > self.max_total_bytes:
            raise BlobError(507, "Blob storage quota exceeded")

    def write_meta(self, blob_id: str, meta: Dict[str, Any]) -> None:
        with open(self.meta_path(blob_id), "w") as f:
            json.dump(meta, f)

    def save_bytes(
        self,
        data: bytes,
        *,
        filename: str = "file",
        content_type: str = "application/octet-stream",
        owner_id: Any = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Buffered save (whole blob already in memory). Returns the sidecar meta
        (plus an injected ``url``). Raises BlobError on empty/oversize/quota."""
        if not data:
            raise BlobError(400, "Empty body")
        self.precheck(len(data))
        os.makedirs(self.root, exist_ok=True)
        blob_id = self.new_id()
        try:
            with open(self.path(blob_id), "wb") as f:
                f.write(data)
        except BaseException:
            self.delete(blob_id)
            raise
        meta = {
            "id": blob_id,
            "filename": filename,
            "content_type": content_type,
            "size": len(data),
            "owner_id": owner_id,
            "created": time.time(),
        }
        if extra:
            meta.update(extra)
        self.write_meta(blob_id, meta)
        out = dict(meta)
        out["url"] = self.url(blob_id)
        return out

    # ---- read -------------------------------------------------------------
    def exists(self, blob_id: str) -> bool:
        return os.path.exists(self.path(blob_id)) and os.path.exists(self.meta_path(blob_id))

    def read_meta(self, blob_id: str) -> Optional[Dict[str, Any]]:
        if not self.exists(blob_id):
            return None
        try:
            with open(self.meta_path(blob_id)) as f:
                return json.load(f)
        except Exception:
            return None

    def read_bytes(self, blob_id: str) -> Optional[bytes]:
        if not os.path.exists(self.path(blob_id)):
            return None
        with open(self.path(blob_id), "rb") as f:
            return f.read()

    def size(self, blob_id: str) -> int:
        return os.path.getsize(self.path(blob_id))

    def delete(self, blob_id: str) -> None:
        for p in (self.path(blob_id), self.meta_path(blob_id)):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass


# ---- HTTP Range helpers (shared by both envs' download endpoints) ----------
def parse_range(range_header: Optional[str], file_size: int) -> Optional[Tuple[int, int]]:
    """Parse a single ``bytes=start-end`` range -> (start, end) inclusive, or None
    if absent/unsatisfiable (caller then serves the whole file)."""
    if not range_header:
        return None
    try:
        unit, _, rng = range_header.partition("=")
        if unit.strip().lower() != "bytes" or "," in rng:
            return None
        start_s, _, end_s = rng.partition("-")
        if start_s == "":
            if not end_s:
                return None
            start = max(0, file_size - int(end_s))
            end = file_size - 1
        else:
            start = int(start_s)
            end = int(end_s) if end_s else file_size - 1
        end = min(end, file_size - 1)
        if start > end or start >= file_size:
            return None
        return start, end
    except (ValueError, TypeError):
        return None


def file_iter(path: str, start: int = 0, length: Optional[int] = None, chunk: int = _CHUNK):
    with open(path, "rb") as f:
        f.seek(start)
        remaining = length
        while True:
            n = chunk if remaining is None else min(chunk, remaining)
            if n <= 0:
                break
            data = f.read(n)
            if not data:
                break
            if remaining is not None:
                remaining -= len(data)
            yield data
