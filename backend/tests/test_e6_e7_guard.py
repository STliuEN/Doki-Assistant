import pytest

from app.db.e4_guard import E4GuardError, allowlist_fingerprint, parse_e4_allowlist
from tests.test_e4_guard import TOPOLOGY_ALLOWLIST


def test_joint_stage_is_bound_to_preflight_fingerprint():
    target = TOPOLOGY_ALLOWLIST["targets"][1]
    joint = {"schema_version": 1, "stage": "E6E7", "targets": [target]}
    e5 = {**joint, "stage": "E5"}
    assert allowlist_fingerprint(joint) == allowlist_fingerprint(parse_e4_allowlist(joint))
    assert allowlist_fingerprint(joint) != allowlist_fingerprint(e5)
    with pytest.raises(E4GuardError):
        parse_e4_allowlist({**joint, "targets": TOPOLOGY_ALLOWLIST["targets"]})
