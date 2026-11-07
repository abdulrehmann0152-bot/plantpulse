"""Test configuration.

* Password hashing is made cheap so the suite stays fast (production uses many more rounds).
* If PP_TEST_PG_URL is set, the WHOLE suite runs against that PostgreSQL server instead of SQLite: every test starts from an empty schema.
  Use a throw-away database only, never the real one:  set PP_TEST_PG_URL=postgresql://user:pass@localhost/testdb
"""
import os

import pytest

os.environ.setdefault("PLANTPULSE_PBKDF2_ITERATIONS", "1000")
PG_URL = os.environ.get("PP_TEST_PG_URL")


@pytest.fixture(autouse=True)
def _fresh_postgres(monkeypatch):
    if not PG_URL:
        yield
        return
    from core import db
    monkeypatch.setattr(db, "_target", lambda: ("pg", PG_URL))
    db._READY.discard(("pg", PG_URL))
    with db._tx() as conn:                                  # an empty schema for every test
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    yield
