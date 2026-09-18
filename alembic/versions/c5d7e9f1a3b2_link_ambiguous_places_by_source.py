"""Use the CSV source to distinguish movies from dramas sharing a title."""
from alembic import op

revision = "c5d7e9f1a3b2"
down_revision = "b4c6d8e0f2a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO product_places (product_id, place_id)
        SELECT product.product_id, place.place_id
        FROM places place
        JOIN products product ON product.title = place.title
        WHERE place.title IS NOT NULL
          AND product.category = CASE
              WHEN place.source LIKE '%한국영상자료원%'
                OR place.source LIKE '%한국영화자료원%' THEN 'MOVIE'
              ELSE 'DRAMA'
          END
          AND (SELECT count(*) FROM products candidate
               WHERE candidate.title = place.title
                 AND candidate.category = product.category) = 1
          AND NOT EXISTS (
              SELECT 1 FROM product_places existing WHERE existing.place_id = place.place_id
          )
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    # Data relationships cannot be identified as migration-owned after deployment.
    pass
