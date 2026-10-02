"""Value object for the content hash used by the CDC between layers."""

import hashlib
import json
from collections.abc import Mapping
from typing import Any


class ContentHash(str):
    """
    Deterministic SHA-256 of a raw payload, used to detect source changes.

    Hashing the canonical JSON (sorted keys, unescaped unicode) makes the value
    stable across runs and independent of the source key order, so the
    Ingestion -> Staging CDC can compare it safely.
    """

    @classmethod
    def of(cls, payload: Mapping[str, Any]) -> "ContentHash":
        canonical_payload = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return cls(hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest())
