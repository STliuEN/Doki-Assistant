"""Owner predicates for additive canonical identity migration."""

from sqlalchemy import and_, or_


def business_owner_filter(model, user_id: str):
    """Prefer migrated ownership; fall back only for rows without a shadow owner."""

    return or_(
        model.canonical_user_id == user_id,
        and_(model.canonical_user_id.is_(None), model.user_id == user_id),
    )


def business_owner_matches(row, user_id: str) -> bool:
    canonical = getattr(row, "canonical_user_id", None)
    return (canonical if canonical is not None else row.user_id) == user_id
