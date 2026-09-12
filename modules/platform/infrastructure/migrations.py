"""Versioned-SQL migration runner for the managed Supabase project.

Migrations live in ``migrations/`` as ordered ``NNNN_name.sql`` files and
are applied exactly once, each inside a single transaction, with the
applied version recorded in ``public.schema_migrations``. Re-running is a
no-op, so ``make migrate`` is safe at every deploy and in CI.

Run from the repository root:

    uv run python -m modules.platform.infrastructure.migrations
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

import asyncpg

MIGRATIONS_TABLE = "schema_migrations"
_VERSION_RE = re.compile(r"^(\d{4})_.+\.sql$")


@dataclass(frozen=True)
class Migration:
    """A single versioned migration file."""

    version: str
    name: str
    path: Path


def load_migrations(migrations_dir: Path) -> list[Migration]:
    """Return the migrations under ``migrations_dir`` in version order."""
    migrations = []
    for path in sorted(migrations_dir.glob("*.sql")):
        match = _VERSION_RE.match(path.name)
        if not match:
            continue
        migrations.append(Migration(version=match.group(1), name=path.stem, path=path))
    return migrations


async def applied_versions(conn: asyncpg.Connection) -> set[str]:
    """Versions already recorded in the migrations table."""
    await conn.execute(
        f"create table if not exists public.{MIGRATIONS_TABLE} ("
        "version text primary key, "
        "name text not null, "
        "applied_at timestamptz not null default now())"
    )
    rows = await conn.fetch(f"select version from public.{MIGRATIONS_TABLE}")
    return {row["version"] for row in rows}


async def migrate(dsn: str, migrations_dir: Path) -> list[str]:
    """Apply every pending migration. Returns the versions applied."""
    migrations = load_migrations(migrations_dir)
    if not migrations:
        raise ValueError(f"no migrations found in {migrations_dir}")
    conn = await asyncpg.connect(dsn)
    try:
        done = await applied_versions(conn)
        applied = []
        for migration in migrations:
            if migration.version in done:
                continue
            sql = migration.path.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    f"insert into public.{MIGRATIONS_TABLE} (version, name) "
                    "values ($1, $2)",
                    migration.version,
                    migration.name,
                )
            applied.append(migration.version)
        return applied
    finally:
        await conn.close()


def migrations_dir_from_repo(repo_root: Path) -> Path:
    return repo_root / "migrations"


async def main() -> None:
    """CLI entry: apply pending migrations using settings from the environment."""
    from dotenv import load_dotenv

    load_dotenv()

    from modules.platform.infrastructure.settings import Settings

    settings = Settings.from_env()
    migrations_dir = migrations_dir_from_repo(Path(__file__).resolve().parents[3])
    applied = await migrate(settings.database_dsn_asyncpg, migrations_dir)
    if applied:
        print(f"applied migrations: {', '.join(applied)}")
    else:
        print("database is up to date")


if __name__ == "__main__":
    asyncio.run(main())
