"""Migration-parsing tests — no database required.

Pins the bug where a semicolon *inside a `--` comment* faked a statement boundary and fed
comment text to Postgres as SQL (broke the 0002 migration in CI). Also validates that every
real migration file parses to pure DDL.

Standalone:  python3 tests/test_migrations.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kitchenaid.store import _MIGRATIONS_DIR, _sql_statements  # noqa: E402


def test_semicolon_inside_a_comment_is_not_a_statement_boundary():
    sql = "-- durable storage; not the gate's authority\nCREATE TABLE t (id int);"
    assert _sql_statements(sql) == ["CREATE TABLE t (id int)"]


def test_multiple_statements_split():
    sql = "CREATE TABLE a (id int);\nCREATE TABLE b (id int);"
    assert _sql_statements(sql) == ["CREATE TABLE a (id int)", "CREATE TABLE b (id int)"]


def test_trailing_and_blank_fragments_dropped():
    assert _sql_statements("CREATE TABLE a (id int);\n\n-- trailing comment\n") == \
        ["CREATE TABLE a (id int)"]


def test_real_migrations_parse_to_pure_ddl():
    files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    assert files, "no migration files found"
    for f in files:
        stmts = _sql_statements(f.read_text(encoding="utf-8"))
        assert stmts, f"{f.name} parsed to nothing"
        for s in stmts:
            assert s.upper().startswith(("CREATE", "ALTER", "DROP", "INSERT")), \
                f"{f.name}: stray non-DDL fragment {s[:40]!r}"


def _run_standalone():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} migration-parsing tests passed.")


if __name__ == "__main__":
    _run_standalone()
