"""add password reset codes and one-time tokens

Revision ID: a3f9c6d2e7b1
Revises: e5f7a9b1c3d5
"""
from alembic import op
import sqlalchemy as sa


revision = "a3f9c6d2e7b1"
down_revision = "e5f7a9b1c3d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_resets",
        sa.Column("reset_id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("reset_token_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("token_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_password_resets_email_created", "password_resets", ["email", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_password_resets_email_created", table_name="password_resets")
    op.drop_table("password_resets")
