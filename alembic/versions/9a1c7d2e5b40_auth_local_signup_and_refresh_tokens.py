"""3단계 인증 — 일반 회원가입(local) + refresh_tokens + email_verifications

바뀌는 것
  1) enum `auth_provider`에 값 `local` 추가          ← ⚠️ 되돌릴 수 없다(아래 설명)
  2) users: email · password_hash · email_verified · created_at 추가,
     provider_user_id를 nullable로 완화, 경로별 필수칼럼 CHECK 제약 추가
  3) refresh_tokens 신규      — 서버에서 취소 가능한 토큰 = 진짜 로그아웃
  4) email_verifications 신규 — 회원가입 이메일 인증코드

⚠️ **PostgreSQL enum 주의**
  · `ALTER TYPE ... ADD VALUE`는 PG 12+ 부터 트랜잭션 안에서 실행할 수 있지만,
    **같은 트랜잭션 안에서 그 새 값을 사용할 수는 없다.** 그래서 이 마이그레이션은
    값을 추가만 하고, 실제로 'local' 행을 넣는 일은 런타임(회원가입)에서 일어난다.
  · enum에서 값을 **빼는 문법은 PostgreSQL에 없다.** downgrade는 타입을 새로 만들어
    갈아끼우는 방식이라, local 사용자가 이미 있으면 실패한다(그게 맞다 — 지우면 안 되니까).

Revision ID: 9a1c7d2e5b40
Revises: 06fb23255fb0
Create Date: 2026-08-22
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a1c7d2e5b40"
down_revision: Union[str, Sequence[str], None] = "06fb23255fb0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1) enum에 'local' 추가 ───────────────────────────────────────────────
    # ⚠️ `autocommit_block`이 필수다. Alembic은 마이그레이션 전체를 한 트랜잭션으로 감싸는데,
    #    PostgreSQL은 **새로 추가한 enum 값을 같은 트랜잭션 안에서 사용하지 못하게** 막는다.
    #    아래 CHECK 제약이 'local'을 참조하므로, 여기서 먼저 커밋해 두지 않으면
    #    "unsafe use of new value of enum type" 로 실패한다.
    #    IF NOT EXISTS 덕분에 재시도해도 안전하다.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE auth_provider ADD VALUE IF NOT EXISTS 'local'")

    # ── 2) users 확장 ───────────────────────────────────────────────────────
    op.add_column("users", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column(
        "users", sa.Column("password_hash", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    # local 가입자는 소셜 id가 없다.
    op.alter_column("users", "provider_user_id", existing_type=sa.String(255), nullable=True)
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    # 경로별 필수 칼럼을 DB가 강제 — 코드 버그로 반쪽짜리 계정이 생기는 걸 막는다.
    # ⚠️ op.f()로 감싸야 한다. 없으면 alembic이 alembic.ini의 명명규칙
    #    ("ck_%(table_name)s_%(constraint_name)s")을 한 번 더 적용해
    #    `ck_users_ck_users_provider_fields`라는 중복 접두사 이름이 만들어진다.
    op.create_check_constraint(
        op.f("ck_users_provider_fields"),
        "users",
        "(auth_provider = 'local'"
        "  AND email IS NOT NULL AND password_hash IS NOT NULL"
        "  AND provider_user_id IS NULL)"
        " OR (auth_provider <> 'local'"
        "  AND provider_user_id IS NOT NULL AND password_hash IS NULL)",
    )

    # ── 3) refresh_tokens ───────────────────────────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column("token_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        # SHA-256 hex 64자. 원문은 저장하지 않는다.
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token_id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    # ── 4) email_verifications ──────────────────────────────────────────────
    op.create_table(
        "email_verifications",
        sa.Column(
            "verification_id", sa.BigInteger(), autoincrement=True, nullable=False
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("verification_id", name=op.f("pk_email_verifications")),
    )
    op.create_index(
        "ix_email_verifications_email_created",
        "email_verifications",
        ["email", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_email_verifications_email_created", table_name="email_verifications")
    op.drop_table("email_verifications")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_constraint(op.f("ck_users_provider_fields"), "users", type_="check")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_column("users", "created_at")
    op.drop_column("users", "email_verified")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "email")
    op.alter_column(
        "users", "provider_user_id", existing_type=sa.String(255), nullable=False
    )

    # enum에서 값을 빼는 문법이 없어 타입을 통째로 갈아끼운다.
    # local 사용자가 남아 있으면 USING 캐스팅에서 실패한다 — 데이터를 지우지 않기 위한 의도된 동작이다.
    op.execute("ALTER TYPE auth_provider RENAME TO auth_provider_old")
    op.execute("CREATE TYPE auth_provider AS ENUM ('google', 'kakao')")
    op.execute(
        "ALTER TABLE users ALTER COLUMN auth_provider "
        "TYPE auth_provider USING auth_provider::text::auth_provider"
    )
    op.execute("DROP TYPE auth_provider_old")
