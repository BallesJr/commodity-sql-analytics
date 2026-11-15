"""Integration tests on the real database, opened read-only.

Run with `pytest -m slow`. They are skipped when data/commodities.duckdb does not
exist (the data folder is not in git). The numbers checked are the ones quoted in
the README.
"""
import hashlib

import duckdb
import pandas as pd
import pytest

import build_views
from helpers import REAL_DATABASE, SQL, run_sql

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not REAL_DATABASE.exists(), reason="data/commodities.duckdb not available"),
]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def real():
    con = duckdb.connect(str(REAL_DATABASE), read_only=True)
    yield con
    con.close()


def test_table_sizes(real):
    counts = real.sql("""SELECT (SELECT COUNT(*) FROM prices), (SELECT COUNT(*) FROM instruments),
                                (SELECT COUNT(*) FROM prices_clean)""").fetchone()

    assert counts == (15085, 6, 15085)


def test_no_duplicate_keys_and_no_null_prices(real):
    out = run_sql(real, "quality/07_integrity_checks.sql")

    assert out["duplicate_keys"].sum() == 0
    assert out["null_prices"].sum() == 0
    assert out["non_positive"].sum() == 2                  # WTI on 2020-04-20 and 2020-04-21
    assert out.set_index("ticker").loc["CL=F", "non_positive"] == 2


def test_missing_weekdays_per_ticker(real):
    out = run_sql(real, "quality/01_missing_days.sql")

    assert len(out) == 6
    assert out["missing_days"].between(94, 96).all()


def test_clean_view_validation_numbers(real):
    out = run_sql(real, "quality/10_clean_view_check.sql").set_index("ticker")
    suspect = out["n_suspect"][out["n_suspect"] > 0].to_dict()

    assert out["n_rows"].sum() == 15085
    assert suspect == {"GC=F": 28, "BZ=F": 1, "HG=F": 1}
    assert out["n_suspect"].sum() == 30
    assert out["n_null_volume"].sum() == 67
    assert out["n_null_ret"].sum() == 8


def test_wti_brent_correlation(real):
    out = run_sql(real, "analysis/04_correlations.sql")
    pair = out[(out["ticker_a"] == "BZ=F") & (out["ticker_b"] == "CL=F")]

    assert len(pair) == 1
    assert pair["corr"].iloc[0] == pytest.approx(0.895, abs=0.0005)    # README rounds to 3 decimals
    assert out["corr"].iloc[0] == pair["corr"].iloc[0]                 # the highest of all pairs
    assert out["corr"].iloc[1] < 0.26


def test_stored_view_equals_the_view_rebuilt_from_the_sql_file(real):
    stored = real.sql("SELECT * FROM prices_clean ORDER BY ticker, date").df()
    prices = real.sql("SELECT * FROM prices").df()

    memory = duckdb.connect(":memory:")
    try:
        memory.register("real_prices", prices)
        memory.execute("CREATE TABLE prices AS SELECT * FROM real_prices")
        build_views.build_views(memory, SQL / "views")
        rebuilt = memory.sql("SELECT * FROM prices_clean ORDER BY ticker, date").df()
    finally:
        memory.close()

    pd.testing.assert_frame_equal(stored, rebuilt)


def test_every_query_runs_and_the_database_file_is_unchanged():
    before = sha256(REAL_DATABASE)

    con = duckdb.connect(str(REAL_DATABASE), read_only=True)
    try:
        files = sorted(p for folder in ("quality", "analysis", "charts")
                       for p in (SQL / folder).glob("*.sql"))
        assert len(files) == 19
        for path in files:
            assert len(con.sql(path.read_text(encoding="utf-8")).df()) > 0, path.name
    finally:
        con.close()

    assert sha256(REAL_DATABASE) == before
