"""The chart queries repeat the logic of the analysis queries; these tests make
sure the two copies stay in agreement."""
import numpy as np
import pandas as pd
import pytest

from helpers import add_prices, bar, raw, run_sql, series


@pytest.fixture
def market(con):
    """Two tickers, 80 days each, built from a fixed seed, plus one suspect row."""
    rng = np.random.default_rng(5)
    for ticker, start, scale in (("A", 100.0, 0.02), ("B", 40.0, 0.05)):
        closes = start * np.exp(np.cumsum(rng.normal(0.0, scale, 80)))
        rows = series(ticker, closes)
        if ticker == "B":
            d = rows[40][0]
            rows[40] = raw(d, "B", closes[40], closes[40], closes[40], closes[40], 0)   # placeholder
        add_prices(con, rows)
    return con


def test_rolling_vol_series_peaks_where_the_analysis_says(market):
    chart = run_sql(market, "charts/rolling_vol.sql")
    peaks = run_sql(market, "analysis/02_rolling_vol_peaks.sql").set_index("ticker")

    for ticker, s in chart.groupby("ticker"):
        top = s.loc[s["vol_21d"].idxmax()]
        assert round(top["vol_21d"] * 100, 1) == pytest.approx(peaks.loc[ticker, "peak_vol_21d_pct"])
        assert pd.Timestamp(top["date"]) == pd.Timestamp(peaks.loc[ticker, "peak_date"])


def test_drawdown_series_bottoms_where_the_analysis_says(market):
    chart = run_sql(market, "charts/drawdowns.sql")
    worst = run_sql(market, "analysis/03_max_drawdown.sql").set_index("ticker")

    for ticker, s in chart.groupby("ticker"):
        low = s.loc[s["drawdown"].idxmin()]
        assert round(low["drawdown"] * 100, 1) == pytest.approx(worst.loc[ticker, "max_drawdown_pct"])
        assert pd.Timestamp(low["date"]) == pd.Timestamp(worst.loc[ticker, "trough_date"])
        assert (s["drawdown"] <= 0).all()


def test_normalized_series_ends_where_the_analysis_says(market):
    chart = run_sql(market, "charts/normalized_prices.sql")
    final = run_sql(market, "analysis/05_final_values.sql").set_index("ticker")

    for ticker, s in chart.groupby("ticker"):
        assert s["norm_price"].iloc[0] == pytest.approx(100.0)
        assert round(s["norm_price"].iloc[-1], 1) == pytest.approx(final.loc[ticker, "final_norm_price"])
        assert s["date"].is_monotonic_increasing


def test_chart_queries_leave_out_suspect_rows(market):
    suspect_dates = market.sql("SELECT date FROM prices_clean WHERE is_suspect").df()["date"]
    assert len(suspect_dates) == 1

    for path in ("charts/normalized_prices.sql", "charts/drawdowns.sql"):
        chart = run_sql(market, path)
        b_dates = pd.to_datetime(chart[chart["ticker"] == "B"]["date"])
        assert pd.Timestamp(suspect_dates.iloc[0]) not in set(b_dates)
        assert len(b_dates) == 79
