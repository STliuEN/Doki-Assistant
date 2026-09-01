from __future__ import annotations

import pytest

from app.auth.migration import MigrationConflict, _source_text
from app.router.user import ProfilePayload


def test_profile_gender_is_validated_as_a_bounded_string() -> None:
    assert ProfilePayload(gender="1").gender == "1"
    assert ProfilePayload(gender=None).gender is None


def test_migration_profile_text_preserves_line_breaks_but_rejects_dangerous_controls() -> None:
    assert _source_text("line one\nline two\t", field="bio", max_length=32) == "line one\nline two\t"
    with pytest.raises(MigrationConflict):
        _source_text("bad\x00value", field="bio", max_length=32)
