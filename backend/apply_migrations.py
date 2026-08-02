"""Apply versioned PostgreSQL migrations before the API starts."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
from pathlib import Path

import asyncpg

MIGRATION_PATTERN = re.compile(r"^V(?P<version>\d+)__.+\.sql$")
MIGRATION_LOCK_ID = 6_745_594_623_761_013_742


def _asyncpg_url(database_url: str) -> str:
    """Convert SQLAlchemy's asyncpg URL into an asyncpg-compatible DSN."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _migration_files(directory: Path) -> list[tuple[int, Path]]:
    migrations: list[tuple[int, Path]] = []
    versions: set[int] = set()
    for path in directory.iterdir():
        match = MIGRATION_PATTERN.match(path.name)
        if not path.is_file() or match is None:
            continue
        version = int(match.group("version"))
        if version in versions:
            raise RuntimeError(f"Duplicate migration version V{version:03d}")
        versions.add(version)
        migrations.append((version, path))
    return sorted(migrations, key=lambda item: item[0])


async def apply_migrations() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")

    directory = Path(os.environ.get("MIGRATIONS_DIR", "/app/migrations"))
    if not directory.is_dir():
        raise RuntimeError(f"Migration directory does not exist: {directory}")

    migrations = _migration_files(directory)
    if not migrations:
        raise RuntimeError(f"No versioned migrations found in {directory}")

    connection = await asyncpg.connect(_asyncpg_url(database_url))
    try:
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version integer PRIMARY KEY,
                filename text NOT NULL,
                checksum varchar(64) NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        await connection.execute("SELECT pg_advisory_lock($1)", MIGRATION_LOCK_ID)
        try:
            rows = await connection.fetch(
                "SELECT version, filename, checksum FROM schema_migrations"
            )
            applied = {row["version"]: row for row in rows}

            for version, path in migrations:
                sql = path.read_text(encoding="utf-8")
                checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
                previous = applied.get(version)
                if previous:
                    if previous["filename"] != path.name or previous["checksum"] != checksum:
                        raise RuntimeError(
                            f"Applied migration V{version:03d} differs from {path.name}"
                        )
                    print(f"Migration {path.name} already applied", flush=True)
                    continue

                async with connection.transaction():
                    await connection.execute(sql)
                    await connection.execute(
                        """
                        INSERT INTO schema_migrations (version, filename, checksum)
                        VALUES ($1, $2, $3)
                        """,
                        version,
                        path.name,
                        checksum,
                    )
                print(f"Applied migration {path.name}", flush=True)
        finally:
            await connection.execute("SELECT pg_advisory_unlock($1)", MIGRATION_LOCK_ID)
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(apply_migrations())
