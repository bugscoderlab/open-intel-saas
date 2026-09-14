"""Unit tests for the database DSN builder's pooler fallback.

Supabase pulls the direct connect host's DNS record during failovers
and maintenance; the Supavisor pooler keeps answering. When
SUPABASE_POOLER_HOST is configured, settings must fall back to the
pooler (session mode, user ``postgres.<ref>``) for as long as the
direct host does not resolve, and prefer the direct host again once it
does — without any manual env juggling.
"""

import socket

from modules.platform.infrastructure.settings import (
    _database_dsn,
    _ref_from_db_host,
)

PASSWORD = "p@ss/word"
BASE_ENV = {
    "SUPABASE_DB_HOST": "db.abc123.supabase.co",
    "SUPABASE_DB_PASSWORD": PASSWORD,
}


def _dns_up(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(None, None)])


def _dns_down(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: (_ for _ in ()).throw(socket.gaierror())
    )


def test_database_url_wins_outright(monkeypatch):
    _dns_down(monkeypatch)
    env = {
        **BASE_ENV,
        "SUPABASE_POOLER_HOST": "aws-0-ap-south-1.pooler.supabase.com",
        "DATABASE_URL": "postgresql+asyncpg://custom@example.com:5432/db",
    }
    assert _database_dsn(env) == "postgresql+asyncpg://custom@example.com:5432/db"


def test_direct_host_used_when_it_resolves(monkeypatch):
    _dns_up(monkeypatch)
    env = {
        **BASE_ENV,
        "SUPABASE_POOLER_HOST": "aws-0-ap-south-1.pooler.supabase.com",
    }
    assert (
        _database_dsn(env)
        == "postgresql+asyncpg://postgres:p%40ss%2Fword@db.abc123.supabase.co:5432/postgres"
    )


def test_pooler_fallback_when_direct_host_does_not_resolve(monkeypatch):
    _dns_down(monkeypatch)
    env = {
        **BASE_ENV,
        "SUPABASE_POOLER_HOST": "aws-0-ap-south-1.pooler.supabase.com",
    }
    assert (
        _database_dsn(env)
        == "postgresql+asyncpg://postgres.abc123:p%40ss%2Fword"
        "@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
    )


def test_project_ref_env_var_preferred_over_host_parse(monkeypatch):
    _dns_down(monkeypatch)
    env = {
        **BASE_ENV,
        "SUPABASE_PROJECT_REF": "zzz999",
        "SUPABASE_POOLER_HOST": "aws-0-ap-south-1.pooler.supabase.com",
        "SUPABASE_POOLER_PORT": "6543",
    }
    dsn = _database_dsn(env)
    assert dsn.startswith("postgresql+asyncpg://postgres.zzz999:")
    assert ":6543/postgres" in dsn


def test_no_pooler_configured_keeps_direct_dsn_even_when_broken(monkeypatch):
    _dns_down(monkeypatch)
    assert (
        _database_dsn(dict(BASE_ENV))
        == "postgresql+asyncpg://postgres:p%40ss%2Fword@db.abc123.supabase.co:5432/postgres"
    )


def test_ref_from_db_host():
    assert _ref_from_db_host("db.abc123.supabase.co") == "abc123"
    assert _ref_from_db_host("postgres.internal") == ""
    assert _ref_from_db_host("db.supabase.co") == "supabase"
