# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC
"""Read / write ``pn-cache.json`` in the active hub with optimistic-retry.

Flow on assignment:

    1. Download the latest pn-cache.json (or treat missing as empty).
    2. Compute the new counters the caller wants.
    3. Upload the new JSON — this creates a new version of the DataFile.
    4. Verify our uploaded version is now the latest (no concurrent writer
       raced us); if it isn't, retry from step 1.

Up to 3 retries before surfacing an error to the caller.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

import adsk.core

from . import hub_fs
from . import schemes


MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 0.6  # doubles each retry: 0.6, 1.2, 2.4
UPLOAD_POLL_INTERVAL_SECONDS = 0.25
UPLOAD_TIMEOUT_SECONDS = 60

CACHE_SCHEMA_VERSION = 1


class PnCacheError(Exception):
    """Raised when the pn-cache.json cannot be read, written, or reconciled."""


@dataclass
class Snapshot:
    """An in-memory view of pn-cache.json at a particular version."""

    counters: Dict[str, int] = field(default_factory=dict)
    source_version_number: int = 0  # 0 = file did not exist yet
    raw: dict = field(default_factory=dict)

    def last_used(self, prefix: str) -> int:
        return int(self.counters.get(prefix, 0))


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def download_snapshot(folder: adsk.core.DataFolder,
                      tmp_dir: str) -> Snapshot:
    """Download pn-cache.json from *folder* and return a Snapshot.

    Returns an empty snapshot (counters all zero, source_version_number=0)
    when the file does not exist yet.
    """
    data_file = hub_fs.find_pn_cache_file(folder)
    if data_file is None:
        return Snapshot()

    os.makedirs(tmp_dir, exist_ok=True)
    local_path = os.path.join(tmp_dir, hub_fs.PN_CACHE_FILENAME)
    # Best-effort cleanup of any stale copy from a prior run.
    try:
        if os.path.exists(local_path):
            os.remove(local_path)
    except Exception:
        pass

    # DataFile.download is synchronous when handler=None.
    ok = data_file.download(local_path, None)
    if not ok or not os.path.exists(local_path):
        raise PnCacheError(
            f"Failed to download {hub_fs.PN_CACHE_FILENAME} from Assets/Pn-Cache."
        )

    try:
        with open(local_path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except Exception as exc:
        raise PnCacheError(
            f"Assets/Pn-Cache/{hub_fs.PN_CACHE_FILENAME} is not valid JSON: {exc}. "
            f"Open it in the Fusion Team web UI to repair."
        ) from exc

    counters: Dict[str, int] = {}
    schemes_obj = raw.get("schemes", {})
    if isinstance(schemes_obj, dict):
        for k, v in schemes_obj.items():
            try:
                counters[str(k)] = int(v.get("lastUsed", 0)) if isinstance(v, dict) else 0
            except Exception:
                counters[str(k)] = 0

    try:
        source_version = int(data_file.latestVersionNumber)
    except Exception:
        source_version = int(getattr(data_file, "versionNumber", 0) or 0)

    return Snapshot(
        counters=counters,
        source_version_number=source_version,
        raw=raw if isinstance(raw, dict) else {},
    )


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def _serialize(counters: Dict[str, int], updated_by: str) -> bytes:
    payload = {
        "version": CACHE_SCHEMA_VERSION,
        "schemes": {p: {"lastUsed": int(counters.get(p, 0))} for p in schemes.SCHEME_PREFIXES},
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "updatedBy": updated_by or "",
    }
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")


def _wait_for_upload(future) -> None:
    """Block until a DataFileFuture finishes, or raise PnCacheError on timeout/failure."""
    if future is None:
        raise PnCacheError("uploadFile returned no future.")

    # Fusion exposes adsk.core.UploadStates; resolve values defensively since
    # the exact enum members can vary between API versions.
    state_finished = getattr(adsk.core.UploadStates, "UploadFinished", None)
    state_failed = getattr(adsk.core.UploadStates, "UploadFailed", None)

    deadline = time.time() + UPLOAD_TIMEOUT_SECONDS
    while time.time() < deadline:
        state = future.uploadState
        if state_finished is not None and state == state_finished:
            return
        if state_failed is not None and state == state_failed:
            raise PnCacheError("pn-cache.json upload failed (UploadFailed state).")
        adsk.doEvents()
        time.sleep(UPLOAD_POLL_INTERVAL_SECONDS)

    raise PnCacheError(
        f"pn-cache.json upload did not complete within {UPLOAD_TIMEOUT_SECONDS}s."
    )


def upload_snapshot(folder: adsk.core.DataFolder,
                    counters: Dict[str, int],
                    updated_by: str,
                    tmp_dir: str) -> int:
    """Upload the given counters as a new version of pn-cache.json.

    Returns the new latest version number (>= 1). Raises PnCacheError on
    failure.
    """
    os.makedirs(tmp_dir, exist_ok=True)

    # Use a deterministic filename — Fusion keys versions off the file name.
    local_path = os.path.join(tmp_dir, hub_fs.PN_CACHE_FILENAME)
    with open(local_path, "wb") as fh:
        fh.write(_serialize(counters, updated_by))

    future = folder.uploadFile(local_path)
    _wait_for_upload(future)

    # Re-resolve the DataFile to pick up the new version.
    new_file = hub_fs.find_pn_cache_file(folder)
    if new_file is None:
        raise PnCacheError(
            "pn-cache.json uploaded but could not be re-located in Assets/Pn-Cache."
        )
    try:
        return int(new_file.latestVersionNumber)
    except Exception:
        # Best effort: if the API returns a DataFileFuture.dataFile instead.
        try:
            return int(future.dataFile.latestVersionNumber)
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# Read-modify-write with optimistic retry
# ---------------------------------------------------------------------------


@dataclass
class CommitResult:
    """Outcome of a successful commit_assignments call."""

    snapshot_before: Snapshot
    counters_after: Dict[str, int]
    new_version_number: int
    retries_used: int


def commit_assignments(app: adsk.core.Application,
                       increments: Dict[str, int],
                       updated_by: str,
                       tmp_dir: str) -> CommitResult:
    """Atomically bump the named scheme counters in pn-cache.json.

    ``increments`` maps prefix -> how many numbers to reserve. The returned
    ``counters_after`` is what the caller should use to compute the actual
    assigned numbers (new value = last_used_before + i-th assignment).

    On return, the cache has been durably updated. The caller is responsible
    for stamping component/document partNumbers AFTER this call succeeds.
    """
    last_error: Optional[Exception] = None
    backoff = RETRY_BACKOFF_SECONDS

    for attempt in range(MAX_RETRIES + 1):
        try:
            project = hub_fs.find_assets_project(app)
            folder = hub_fs.find_or_create_pn_cache_folder(project)
            snapshot = download_snapshot(folder, tmp_dir)

            new_counters = dict(snapshot.counters)
            for prefix, n in increments.items():
                if n <= 0:
                    continue
                new_counters[prefix] = snapshot.last_used(prefix) + int(n)

            # Zero-bump is a no-op — surface as a CommitResult so callers still
            # get a consistent return shape.
            if all(v <= 0 for v in increments.values()):
                return CommitResult(
                    snapshot_before=snapshot,
                    counters_after=new_counters,
                    new_version_number=snapshot.source_version_number,
                    retries_used=attempt,
                )

            new_version = upload_snapshot(folder, new_counters, updated_by, tmp_dir)

            # Verify nobody raced us: re-download and confirm the counters we
            # just wrote are what's live. We compare counters rather than
            # version numbers because the Fusion DataFile version is bumped
            # once per upload and our write is the most recent one.
            verify = download_snapshot(folder, tmp_dir)
            if _counters_match(verify.counters, new_counters):
                return CommitResult(
                    snapshot_before=snapshot,
                    counters_after=new_counters,
                    new_version_number=new_version or verify.source_version_number,
                    retries_used=attempt,
                )

            # Somebody else's write clobbered ours — retry from scratch.
            last_error = PnCacheError(
                "Detected a concurrent writer to pn-cache.json; retrying."
            )
        except Exception as exc:
            last_error = exc

        if attempt < MAX_RETRIES:
            time.sleep(backoff)
            backoff *= 2

    raise PnCacheError(
        f"Could not commit pn-cache.json after {MAX_RETRIES + 1} attempts: {last_error}"
    )


def _counters_match(a: Dict[str, int], b: Dict[str, int]) -> bool:
    keys = set(a.keys()) | set(b.keys())
    for k in keys:
        if int(a.get(k, 0)) != int(b.get(k, 0)):
            return False
    return True


# ---------------------------------------------------------------------------
# Helpers for callers
# ---------------------------------------------------------------------------


def default_tmp_dir() -> str:
    """Return the add-in's cache directory for pn-cache.json scratch writes."""
    # commands/partnumber_shared/ -> commands/ -> addin root
    here = os.path.dirname(os.path.abspath(__file__))
    addin_root = os.path.dirname(os.path.dirname(here))
    return os.path.join(addin_root, "cache", "pn-cache")
