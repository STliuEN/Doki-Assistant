"""Enforce the final E3 user identity constraints."""

import sqlalchemy as sa

from alembic import op

revision = "20260901_0007_e3_auth"
down_revision = "20260831_0006_e3_auth_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {
        item["name"]: tuple(item["column_names"])
        for item in sa.inspect(op.get_bind()).get_unique_constraints("users")
        if item.get("name")
    }
    if "uq_users_username" in existing:
        if existing["uq_users_username"] != ("username",):
            raise RuntimeError("uq_users_username exists with an unexpected definition")
        return
    op.create_unique_constraint("uq_users_username", "users", ["username"])


def downgrade() -> None:
    op.drop_constraint("uq_users_username", "users", type_="unique")
