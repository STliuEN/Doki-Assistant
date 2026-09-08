"""Offline payload checks for the E4 CLI, without inspecting live resources."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.e4.identity import deterministic_target_uuid
from app.e4.importer import (
    E4BusinessBundle,
    E4ImportBlocked,
    E4ImportError,
    _decode_media,
    _digest,
    _encrypted_key_requires_quarantine,
    _model_for_entity,
    _prepare_row,
    _required_text,
    _row_data,
    _sha256_json,
    _source_key,
    _source_key_token,
    _uuid,
    load_business_bundle,
)


def _owner_candidate(item: Mapping[str, Any]) -> str | None:
    explicit = item.get("canonical_user_id", _row_data(item).get("canonical_user_id"))
    owner = item.get("owner")
    if str(item.get("scope", item.get("scope_type"))).casefold() == "global":
        if explicit is not None or owner is not None:
            raise E4ImportBlocked("global payload must not have an owner")
        return None
    candidate = deterministic_target_uuid(_source_key(owner)) if isinstance(owner, Mapping) else None
    if explicit is not None:
        explicit = _uuid(explicit, "canonical_user_id")
        if candidate is not None and explicit != candidate:
            raise E4ImportBlocked("payload owner conflicts with canonical identity")
    if candidate is None and explicit is None:
        raise E4ImportBlocked("user payload requires an owner")
    return explicit or candidate


def _entity_issue(entity: Mapping[str, Any]) -> str | None:
    key = _source_key(entity)
    try:
        model = _model_for_entity(key.entity_type)
    except E4ImportBlocked:
        return "unsupported_entity_type"
    if not _row_data(entity):
        return "missing_row_payload"
    try:
        row = _prepare_row(model, entity, deterministic_target_uuid(key), _owner_candidate(entity), {})
        for attribute in model.__mapper__.column_attrs:
            column = attribute.columns[0]
            if not column.nullable and column.default is None and column.server_default is None:
                if row.get(attribute.key) is None:
                    return "missing_required_column"
        if _encrypted_key_requires_quarantine(model, entity, row):
            return "missing_key_version"
        blob = row.get("content_blob")
        if isinstance(blob, bytes):
            if row.get("file_size") != len(blob) or row.get("md5") != hashlib.md5(blob).hexdigest():
                return "document_bytes_mismatch"
    except (E4ImportError, TypeError, ValueError):
        return "invalid_row_payload"
    return None


def _media_issue(item: Mapping[str, Any]) -> str | None:
    try:
        blob = _decode_media(item)
        _owner_candidate(item)
        _required_text(item.get("filename"), "filename", 255)
        _required_text(item.get("mime_type"), "mime_type", 255)
        artifact = item.get("artifact_digest")
        if artifact is not None and _digest(artifact, "artifact_digest") != hashlib.sha256(blob).hexdigest():
            return "media_bytes_mismatch"
        legacy_md5 = item.get("legacy_md5")
        if legacy_md5 is not None and str(legacy_md5).casefold() != hashlib.md5(blob).hexdigest():
            return "media_bytes_mismatch"
        if str(item.get("status", "active")).casefold() not in {"active", "quarantined"}:
            return "invalid_media_status"
    except (E4ImportError, TypeError, ValueError):
        return "invalid_media_payload"
    return None


def build_business_payload_report(
    bundle: E4BusinessBundle | Mapping[str, Any] | str | Path,
) -> dict[str, Any]:
    """Check adapter coverage, row shape, required fields, bytes and key versions.

    This is not a target constraint check, a source authenticity check, or a
    key-decryption test. Live ownership, schema, grants and restore gates remain
    mandatory even when this report has no issues.
    """

    parsed = load_business_bundle(bundle)
    issues = []
    for entity in parsed.entities:
        issue = _entity_issue(entity)
        if issue is not None:
            issues.append({"source_key_sha256": _source_key_token(_source_key(entity)), "code": issue})
    for item in parsed.media:
        issue = _media_issue(item)
        if issue is not None:
            key = _source_key({**item, "entity_type": item.get("entity_type", "media")})
            issues.append({"source_key_sha256": _source_key_token(key), "code": issue})
    result = {
        "scope": "offline-payload-only",
        "blocked": bool(issues),
        "checked_entities": len(parsed.entities),
        "checked_media": len(parsed.media),
        "issues": sorted(issues, key=lambda issue: (issue["source_key_sha256"], issue["code"])),
    }
    return {**result, "report_sha256": _sha256_json(result)}
