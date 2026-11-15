"""run_sql.py: run one .sql file read-only and print the result."""
import duckdb
import pytest

import run_sql


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "db.duckdb"
    c = duckdb.connect(str(path))
    c.execute("CREATE TABLE t AS SELECT * FROM (VALUES (1, 'a'), (2, 'b')) AS v(x, y)")
    c.close()
    return path


def test_run_sql_file_returns_the_query_result(tmp_path, database):
    query = tmp_path / "q.sql"
    query.write_text("SELECT x, y FROM t ORDER BY x DESC", encoding="utf-8")
    c = duckdb.connect(str(database), read_only=True)
    try:
        df = run_sql.run_sql_file(c, query)
    finally:
        c.close()

    assert list(df.columns) == ["x", "y"]
    assert df["x"].tolist() == [2, 1]
    assert df["y"].tolist() == ["b", "a"]


def test_read_only_connection_rejects_writes(tmp_path, database):
    query = tmp_path / "write.sql"
    query.write_text("CREATE TABLE should_not_exist AS SELECT 1 AS x", encoding="utf-8")
    c = duckdb.connect(str(database), read_only=True)
    try:
        with pytest.raises(duckdb.Error):
            run_sql.run_sql_file(c, query)
        tables = {r[0] for r in c.sql("SELECT table_name FROM information_schema.tables").fetchall()}
    finally:
        c.close()

    assert tables == {"t"}


@pytest.mark.parametrize("argv", [["run_sql.py"], ["run_sql.py", "a.sql", "b.sql"]])
def test_main_with_wrong_number_of_arguments_exits_with_usage(argv):
    with pytest.raises(SystemExit) as exc:
        run_sql.main(argv)

    assert exc.value.code == "Usage: python src/run_sql.py path/to/query.sql"


def test_main_prints_the_result_and_opens_the_database_read_only(tmp_path, database, capsys):
    query = tmp_path / "q.sql"
    query.write_text("SELECT SUM(x) AS total FROM t", encoding="utf-8")
    before = database.read_bytes()

    run_sql.main(["run_sql.py", str(query)], database=str(database))

    printed = capsys.readouterr().out
    assert "total" in printed and "3" in printed
    assert database.read_bytes() == before


def test_main_cannot_write_through_a_sql_file(tmp_path, database):
    query = tmp_path / "write.sql"
    query.write_text("DROP TABLE t", encoding="utf-8")

    with pytest.raises(duckdb.Error):
        run_sql.main(["run_sql.py", str(query)], database=str(database))
