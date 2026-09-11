"""Remove external IDs without changing product IDs or detail foreign keys."""
import hashlib
import json

from alembic import op
import sqlalchemy as sa

revision = "b23c45d67e89"
down_revision = "a12b34c56d78"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(sa.text("SELECT pg_advisory_xact_lock(731942810)"))
    rows = connection.execute(sa.text(
        "SELECT product_id, category, title, first_air_date FROM products WHERE csv_row_hash IS NOT NULL"
    )).mappings().all()
    hashes = {}
    for row in rows:
        identity = (row["category"], row["title"], row["first_air_date"])
        key = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
        if key in hashes:
            raise ValueError(f"Ambiguous product IDs: {hashes[key]} and {row['product_id']}")
        hashes[key] = row["product_id"]
    # Clear only import hashes inside this transaction to avoid intermediate conflicts.
    connection.execute(sa.text("UPDATE products SET csv_row_hash = NULL WHERE csv_row_hash IS NOT NULL"))
    for key, product_id in hashes.items():
        connection.execute(sa.text("UPDATE products SET csv_row_hash = :key WHERE product_id = :id"),
                           {"key": key, "id": product_id})
    op.drop_column("movie_details", "tmdb_id")


def downgrade() -> None:
    # Removed external ID values cannot be reconstructed.
    op.add_column("movie_details", sa.Column("tmdb_id", sa.BigInteger(), nullable=True))
    op.create_unique_constraint("uq_movie_details_tmdb_id", "movie_details", ["tmdb_id"])
