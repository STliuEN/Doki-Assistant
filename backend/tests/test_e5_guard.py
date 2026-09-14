import pytest

from app.db.e4_guard import E4GuardError, allowlist_fingerprint, parse_e4_allowlist
from tests.test_e4_guard import TOPOLOGY_ALLOWLIST


def test_e5_single_target_is_explicit_and_fingerprint_survives_normalization():
    target = TOPOLOGY_ALLOWLIST["targets"][1]
    manifest = {"schema_version": 1, "stage": "E5", "targets": [target]}
    parsed = parse_e4_allowlist(manifest)
    assert allowlist_fingerprint(manifest) == allowlist_fingerprint(parsed)
    with pytest.raises(E4GuardError):
        parse_e4_allowlist({"targets": [target]})
    with pytest.raises(E4GuardError):
        parse_e4_allowlist({**manifest, "targets": TOPOLOGY_ALLOWLIST["targets"]})
    with pytest.raises(E4GuardError):
        parse_e4_allowlist({**manifest, "targets": [{**target, "role": "source", "read_only": True}]})
