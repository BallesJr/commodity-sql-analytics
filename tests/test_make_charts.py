"""make_charts.py helpers and a smoke test of the figures on synthetic data."""
import duckdb
import numpy as np
import pandas as pd
import pytest

import build_views
import ingest
import make_charts
from helpers import REPO, SQL, add_prices, series


def frame(dates, values, ticker="A", column="value"):
    return pd.DataFrame({"date": pd.to_datetime(dates), "ticker": ticker, column: values})


# ---break_gaps---

def test_break_gaps_inserts_a_nan_row_the_day_before_the_series_resumes(capsys):
    s = frame(["2024-01-01", "2024-01-02", "2024-01-12", "2024-01-15"], [1.0, 2.0, 3.0, 4.0])
    out = make_charts.break_gaps(s, "value", "chart.png")

    assert len(out) == 5
    gap_row = out[out["value"].isna()]
    assert gap_row["date"].tolist() == [pd.Timestamp("2024-01-11")]
    assert out["date"].is_monotonic_increasing
    assert out["value"].dropna().tolist() == [1.0, 2.0, 3.0, 4.0]      # real points untouched
    assert "chart.png: A gap 2024-01-02 -> 2024-01-12 (10 days)" in capsys.readouterr().out


def test_break_gaps_leaves_short_gaps_alone(capsys):
    # A long weekend (5 days) is not a gap; the threshold is "more than 5 days"
    s = frame(["2024-01-01", "2024-01-02", "2024-01-07", "2024-01-08"], [1.0, 2.0, 3.0, 4.0])
    out = make_charts.break_gaps(s, "value", "chart.png")

    assert len(out) == 4
    assert not out["value"].isna().any()
    assert capsys.readouterr().out == ""


# ---query---

def test_query_runs_a_sql_file_and_parses_the_date_column(tmp_path):
    path = tmp_path / "q.sql"
    path.write_text("SELECT DATE '2024-01-02' AS date, 'A' AS ticker, 1.5 AS value", encoding="utf-8")
    c = duckdb.connect(":memory:")
    try:
        df = make_charts.query(c, path)
    finally:
        c.close()

    assert pd.api.types.is_datetime64_any_dtype(df["date"])
    assert df["date"].iloc[0] == pd.Timestamp("2024-01-02")
    assert df["value"].iloc[0] == 1.5


# ---Figures (smoke test)---

@pytest.fixture
def chart_database(tmp_path):
    """Database file with the six real tickers and 60 synthetic days each."""
    parquet = tmp_path / "raw.parquet"
    rng = np.random.default_rng(3)
    frames = []
    for i, ticker in enumerate(make_charts.TICKERS):
        closes = (50.0 + 10 * i) * np.exp(np.cumsum(rng.normal(0.0, 0.02, 60)))
        frames.append(pd.DataFrame(series(ticker, closes),
                                   columns=["date", "ticker", "open", "high", "low", "close", "volume"]))
    pd.concat(frames).assign(date=lambda d: pd.to_datetime(d["date"])).to_parquet(parquet, index=False)

    database = tmp_path / "charts.duckdb"
    c = duckdb.connect(str(database))
    ingest.ingest(c, parquet)
    build_views.build_views(c, SQL / "views")
    c.close()
    return database


def test_main_writes_the_four_figures_without_touching_the_database(
        chart_database, tmp_path, monkeypatch, capsys):
    out_dir = tmp_path / "figures"
    before = chart_database.read_bytes()
    monkeypatch.chdir(REPO)                                # the chart queries are read from sql/

    make_charts.main(database=str(chart_database), out_dir=out_dir)

    names = sorted(p.name for p in out_dir.glob("*.png"))
    assert names == ["correlation_heatmap.png", "drawdowns.png",
                     "normalized_prices.png", "rolling_vol.png"]
    assert all((out_dir / n).stat().st_size > 10_000 for n in names)
    assert chart_database.read_bytes() == before
    assert capsys.readouterr().out.count("Saved ") == 4


def test_every_ticker_has_a_fixed_color():
    assert set(make_charts.COLORS) == set(make_charts.TICKERS)
    assert len(set(make_charts.COLORS.values())) == len(make_charts.TICKERS)
