from pathlib import Path

from backend.db.migrate import migration_sql
from backend.shared.config import Settings


def test_database_url_is_required():
    assert Settings.model_fields["database_url"].is_required()


def test_initial_migration_contains_session_and_job_tables():
    sql = migration_sql()

    assert "CREATE TABLE IF NOT EXISTS sessions" in sql
    assert "user_id UUID NOT NULL" in sql
    assert "CREATE TABLE IF NOT EXISTS jobs" in sql
    assert "REFERENCES sessions(session_id) ON DELETE CASCADE" in sql
    assert "next_retry_at TIMESTAMPTZ DEFAULT NULL" in sql


def test_migration_file_is_in_repository():
    migration = Path(__file__).parents[1] / "db" / "migrations" / "001_initial.sql"

    assert migration.is_file()
