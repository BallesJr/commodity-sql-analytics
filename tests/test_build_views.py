"""build_views.py: runs the view files against a connection."""
import datetime as dt

import duckdb
import pytest

import build_views
from helpers import SQL, add_prices, bar


@pytest.fixture
def db():
    c = duckdb.connect(":memory:")
    c.execute("""CREATE TABLE prices (date DATE, ticker VARCHAR, open DOUBLE, high DOUBLE,
                                      low DOUBLE, close DOUBLE, volume BIGINT)""")
    yield c
    c.close()


def view_names(c):
    return {r[0] for r in c.sql("SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()}


def test_creates_the_prices_clean_view(db):
    build_views.build_views(db, SQL / "views")

    assert view_names(db) == {"prices_clean"}


def test_running_twice_does_not_fail(db):
    build_views.build_views(db, SQL / "views")
    build_views.build_views(db, SQL / "views")

    assert view_names(db) == {"prices_clean"}


def test_raw_prices_table_is_not_modified(db):
    add_prices(db, [bar(dt.date(2024, 1, 2), close=10.0, volume=0),
                    bar(dt.date(2024, 1, 3), close=11.0)])
    before = db.sql("SELECT * FROM prices ORDER BY date").fetchall()

    build_views.build_views(db, SQL / "views")

    assert db.sql("SELECT * FROM prices ORDER BY date").fetchall() == before
    assert before[0][-1] == 0                              # the zero volume is still in the table


def test_files_run_in_alphabetical_order(tmp_path, capsys):
    # 02 depends on 01, so any other order fails; 10 sorts after 02 as text
    (tmp_path / "02_second.sql").write_text("CREATE VIEW second AS SELECT x + 1 AS y FROM first;")
    (tmp_path / "01_first.sql").write_text("CREATE VIEW first AS SELECT 1 AS x;")
    (tmp_path / "10_third.sql").write_text("CREATE VIEW third AS SELECT y + 1 AS z FROM second;")
    (tmp_path / "notes.txt").write_text("not sql, must be ignored")
    c = duckdb.connect(":memory:")
    try:
        build_views.build_views(c, tmp_path)
        assert c.sql("SELECT z FROM third").fetchone()[0] == 3
    finally:
        c.close()

    printed = [line for line in capsys.readouterr().out.splitlines() if line.startswith("Running")]
    assert [line.rsplit("/", 1)[-1] for line in printed] == [
        "01_first.sql", "02_second.sql", "10_third.sql"]


def test_main_builds_the_view_in_a_database_file(tmp_path):
    database = tmp_path / "db.duckdb"
    c = duckdb.connect(str(database))
    c.execute("""CREATE TABLE prices (date DATE, ticker VARCHAR, open DOUBLE, high DOUBLE,
                                      low DOUBLE, close DOUBLE, volume BIGINT)""")
    c.close()

    build_views.main(database=str(database), views_dir=SQL / "views")

    c = duckdb.connect(str(database), read_only=True)
    try:
        assert view_names(c) == {"prices_clean"}
    finally:
        c.close()
