-- Retired: these migrations and tables are now used by My Page.
-- Keep this file as a guard for the earlier recovery command.
-- Apply the restored migration history with: python -m alembic upgrade head
DO $$
BEGIN
    RAISE EXCEPTION 'Recovery retired: My Page requires these tables. Run alembic upgrade head instead.';
END;
$$;
