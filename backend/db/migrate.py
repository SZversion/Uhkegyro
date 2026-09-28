from pathlib import Path


MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def migration_sql() -> str:
    return (MIGRATIONS_DIR / "001_initial.sql").read_text(encoding="utf-8")


async def migrate(connection) -> None:
    await connection.execute(migration_sql())
