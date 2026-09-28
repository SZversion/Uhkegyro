from pathlib import Path

from backend.db.migrate import MIGRATIONS_DIR, migrate, migration_sql
from backend.shared.config import Settings


def test_database_url_is_required():
    assert Settings.model_fields["database_url"].is_required()


def test_initial_migration_contains_session_and_job_tables():
    sql = migration_sql()

    assert "CREATE TABLE IF NOT EXISTS sessions" in sql
    assert "user_id" not in sql
    assert "CREATE TABLE IF NOT EXISTS jobs" in sql
    assert "REFERENCES sessions(session_id) ON DELETE CASCADE" in sql
    assert "next_retry_at TIMESTAMPTZ DEFAULT NULL" in sql


def test_migration_file_is_in_repository():
    migration = Path(__file__).parents[1] / "db" / "migrations" / "001_initial.sql"

    assert migration.is_file()


def test_legacy_user_id_migration_is_in_repository():
    migration = MIGRATIONS_DIR / "002_remove_legacy_session_user_id.sql"

    assert "DROP COLUMN IF EXISTS user_id" in migration.read_text(encoding="utf-8")


def test_migrate_applies_sql_files_in_order():
    import asyncio

    class Connection:
        def __init__(self):
            self.statements = []

        async def execute(self, statement):
            self.statements.append(statement)

    connection = Connection()
    asyncio.run(migrate(connection))

    assert len(connection.statements) == 2
    assert "CREATE TABLE IF NOT EXISTS sessions" in connection.statements[0]
    assert "DROP COLUMN IF EXISTS user_id" in connection.statements[1]
