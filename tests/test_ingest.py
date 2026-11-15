"""ingest.py on a hand-made parquet file in a temporary folder."""
import datetime as dt

import duckdb
import pandas as pd
import pytest

import build_views
import ingest
from helpers import SQL


@pytest.fixture
def parquet(tmp_path):
    """Raw file shaped like download.py's output: timestamps, int64 volume."""
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-02", "2024-01-03"]),
        "ticker": ["CL=F", "CL=F", "GC=F", "GC=F"],
        "open": [70.0, 71.0, 2000.0, 2010.0],
        "high": [72.0, 73.0, 2020.0, 2010.0],
        "low": [69.0, 70.0, 1990.0, 2010.0],
        "close": [71.0, -37.63, 2010.0, 2010.0],
        "volume": [1000, 2000, 0, 0],
    })
    path = tmp_path / "raw.parquet"
    df.to_parquet(path, index=False)
    return path


@pytest.fixture
def db():
    c = duckdb.connect(":memory:")
    yield c
    c.close()


def test_columns_are_cast_to_the_documented_types(db, parquet):
    ingest.ingest(db, parquet)
    types = dict(db.sql("SELECT column_name, data_type FROM information_schema.columns "
                        "WHERE table_name = 'prices'").fetchall())

    assert types == {"date": "DATE", "ticker": "VARCHAR", "open": "DOUBLE", "high": "DOUBLE",
                     "low": "DOUBLE", "close": "DOUBLE", "volume": "BIGINT"}


def test_rows_are_loaded_as_is_without_cleaning(db, parquet):
    ingest.ingest(db, parquet)
    rows = db.sql("SELECT * FROM prices ORDER BY ticker, date").fetchall()

    assert rows == [
        (dt.date(2024, 1, 2), "CL=F", 70.0, 72.0, 69.0, 71.0, 1000),
        (dt.date(2024, 1, 3), "CL=F", 71.0, 73.0, 70.0, -37.63, 2000),     # negative close kept
        (dt.date(2024, 1, 2), "GC=F", 2000.0, 2020.0, 1990.0, 2010.0, 0),  # zero volume kept
        (dt.date(2024, 1, 3), "GC=F", 2010.0, 2010.0, 2010.0, 2010.0, 0),  # flat bar kept
    ]


def test_ingest_is_idempotent(db, parquet):
    ingest.ingest(db, parquet)
    first = db.sql("SELECT * FROM prices ORDER BY ticker, date").fetchall()
    ingest.ingest(db, parquet)

    assert db.sql("SELECT * FROM prices ORDER BY ticker, date").fetchall() == first
    assert db.sql("SELECT COUNT(*) FROM instruments").fetchone()[0] == 6       # not 12


def test_instruments_reference_table(db, parquet):
    ingest.ingest(db, parquet)
    rows = db.sql("SELECT ticker, name, sector, unit FROM instruments ORDER BY ticker").fetchall()

    assert rows == [
        ("BZ=F", "Brent Crude Oil", "Energy", "USD/barrel"),
        ("CL=F", "WTI Crude Oil", "Energy", "USD/barrel"),
        ("GC=F", "Gold", "Precious Metals", "USD/troy oz"),
        ("HG=F", "Copper", "Industrial Metals", "USD/lb"),
        ("NG=F", "Natural Gas", "Energy", "USD/MMBtu"),
        ("ZW=F", "Wheat", "Agriculture", "USc/bushel"),
    ]


def test_ingest_works_when_the_view_already_exists(db, parquet):
    ingest.ingest(db, parquet)
    build_views.build_views(db, SQL / "views")
    ingest.ingest(db, parquet)                             # replaces the table under the view

    assert db.sql("SELECT COUNT(*) FROM prices_clean").fetchone()[0] == 4


def test_summary_gives_rows_and_date_range_per_ticker(db, parquet):
    ingest.ingest(db, parquet)
    s = ingest.summary(db)

    assert s["ticker"].tolist() == ["CL=F", "GC=F"]
    assert s["n_rows"].tolist() == [2, 2]
    assert [d.date() for d in pd.to_datetime(s["first_date"])] == [dt.date(2024, 1, 2)] * 2
    assert [d.date() for d in pd.to_datetime(s["last_date"])] == [dt.date(2024, 1, 3)] * 2


def test_parquet_path_with_a_quote_is_escaped(db, tmp_path, parquet):
    odd = tmp_path / "it's raw.parquet"
    odd.write_bytes(parquet.read_bytes())
    ingest.ingest(db, odd)

    assert db.sql("SELECT COUNT(*) FROM prices").fetchone()[0] == 4


def test_default_sql_reads_the_documented_parquet_path():
    assert "read_parquet('data/raw_prices.parquet')" in ingest.create_prices_sql()


def test_main_creates_the_database_file_and_prints_the_summary(tmp_path, parquet, capsys):
    database = tmp_path / "out.duckdb"
    ingest.main(database=str(database), parquet=parquet)

    assert database.exists()
    printed = capsys.readouterr().out
    assert "CL=F" in printed and "n_rows" in printed
    c = duckdb.connect(str(database), read_only=True)
    try:
        assert c.sql("SELECT COUNT(*) FROM prices").fetchone()[0] == 4
        assert c.sql("SELECT COUNT(*) FROM instruments").fetchone()[0] == 6
    finally:
        c.close()
