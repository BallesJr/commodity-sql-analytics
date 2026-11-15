"""The analysis queries in sql/analysis/, compared with values worked out by hand."""
import datetime as dt
import math

import numpy as np
import pandas as pd
import pytest

from helpers import add_prices, bar, raw, run_sql, series


def by_ticker(df):
    return df.set_index("ticker")


def day(i):
    """The i-th business day of the synthetic calendar (0 = 2024-01-01, a Monday)."""
    return pd.bdate_range("2024-01-01", periods=i + 1)[-1].date()


# ---01: return statistics---

def test_01_annualised_mean_and_volatility(con):
    closes = [100, 110, 99, 108.9]                         # +10%, -10%, +10%
    add_prices(con, series("A", closes))
    out = by_ticker(run_sql(con, "analysis/01_return_stats.sql")).loc["A"]

    logs = np.array([math.log(1.1), math.log(0.9), math.log(1.1)])
    assert out["n_returns"] == 3
    assert out["ann_mean_log_ret_pct"] == pytest.approx(round(logs.mean() * 252 * 100, 1))
    assert out["ann_vol_pct"] == pytest.approx(round(logs.std(ddof=1) * math.sqrt(252) * 100, 1))
    assert out["worst_day_pct"] == pytest.approx(-10.0)
    assert out["best_day_pct"] == pytest.approx(10.0)


def test_01_excludes_suspect_rows_but_keeps_the_return_measured_from_them(con):
    # Current behaviour: the suspect row's own return (-50%) is excluded, but the
    # next return is still measured from the suspect close (50 -> 110 = +120%)
    add_prices(con, [bar(day(0), close=100.0), raw(day(1), "A", 50, 50, 50, 50, 0),
                     bar(day(2), close=110.0)])
    out = by_ticker(run_sql(con, "analysis/01_return_stats.sql")).loc["A"]

    assert out["n_returns"] == 1
    assert out["worst_day_pct"] == pytest.approx(120.0)
    assert out["best_day_pct"] == pytest.approx(120.0)


def test_01_orders_tickers_by_volatility_descending(con):
    add_prices(con, series("CALM", [100, 101, 100, 101]) + series("WILD", [100, 150, 100, 150]))
    out = run_sql(con, "analysis/01_return_stats.sql")

    assert out["ticker"].tolist() == ["WILD", "CALM"]
    assert out["ann_vol_pct"].is_monotonic_decreasing


# ---02: rolling volatility peaks---

def closes_from_log_returns(log_returns, start=100.0):
    return start * np.exp(np.concatenate([[0.0], np.cumsum(log_returns)]))


def test_02_needs_twenty_one_returns_for_a_window(con):
    pattern = [0.01, -0.01] * 11                           # 22 returns available to slice
    add_prices(con, series("FULL", closes_from_log_returns(pattern[:21])))     # 22 rows, 21 returns
    add_prices(con, series("SHORT", closes_from_log_returns(pattern[:20])))    # 21 rows, 20 returns
    out = by_ticker(run_sql(con, "analysis/02_rolling_vol_peaks.sql"))

    assert "SHORT" not in out.index
    expected = np.std(pattern[:21], ddof=1) * math.sqrt(252) * 100
    assert out.loc["FULL", "peak_vol_21d_pct"] == pytest.approx(round(expected, 1))
    assert pd.Timestamp(out.loc["FULL", "peak_date"]).date() == day(21)       # the only full window


def test_02_finds_the_window_with_the_highest_volatility(con):
    # 60 quiet returns with one burst; the expected peak is computed independently with pandas
    log_returns = np.array([0.002 if i % 2 == 0 else -0.002 for i in range(60)])
    log_returns[30:34] = [0.08, -0.07, 0.09, -0.06]
    closes = closes_from_log_returns(log_returns)
    add_prices(con, series("A", closes))
    out = by_ticker(run_sql(con, "analysis/02_rolling_vol_peaks.sql")).loc["A"]

    rolling = pd.Series(log_returns).rolling(21).std(ddof=1) * math.sqrt(252)
    peak_return_index = int(rolling.idxmax())              # return i belongs to row i + 1
    assert pd.Timestamp(out["peak_date"]).date() == day(peak_return_index + 1)
    assert out["peak_vol_21d_pct"] == pytest.approx(round(rolling.max() * 100, 1))
    assert 33 <= peak_return_index <= 50                   # a window that contains the whole burst


# ---03: maximum drawdown---

def test_03_drawdown_from_the_running_peak(con):
    add_prices(con, series("A", [100, 120, 60, 90]))
    out = by_ticker(run_sql(con, "analysis/03_max_drawdown.sql")).loc["A"]

    assert pd.Timestamp(out["trough_date"]).date() == day(2)
    assert out["trough_close"] == 60.0
    assert out["prior_peak"] == 120.0
    assert out["max_drawdown_pct"] == pytest.approx(-50.0)


def test_03_ignores_non_positive_closes(con):
    add_prices(con, [bar(day(0), close=100.0), raw(day(1), "A", 1, 2, -6, -5, 5),
                     bar(day(2), close=80.0)])
    out = by_ticker(run_sql(con, "analysis/03_max_drawdown.sql")).loc["A"]

    assert out["trough_close"] == 80.0                     # not the negative close
    assert out["max_drawdown_pct"] == pytest.approx(-20.0)


def test_03_never_falling_series_has_zero_drawdown_and_order_is_worst_first(con):
    add_prices(con, series("UP", [100, 110, 120]) + series("DOWN", [100, 120, 60, 90]))
    out = run_sql(con, "analysis/03_max_drawdown.sql")

    assert out["ticker"].tolist() == ["DOWN", "UP"]
    assert out["max_drawdown_pct"].tolist() == [-50.0, 0.0]


# ---04: correlations---

def test_04_proportional_and_inverse_series(con):
    a = [100, 110, 99, 108.9]
    log_a = np.diff(np.log(a))
    add_prices(con, series("A", a))
    add_prices(con, series("B", [2 * x for x in a]))                   # same returns as A
    add_prices(con, series("C", closes_from_log_returns(-log_a, 50)))  # opposite log returns
    out = run_sql(con, "analysis/04_correlations.sql")
    corr = {(r.ticker_a, r.ticker_b): (r.n_days, r.corr) for r in out.itertuples()}

    assert set(corr) == {("A", "B"), ("A", "C"), ("B", "C")}           # each pair once, a < b
    assert corr[("A", "B")] == (3, 1.0)
    assert corr[("A", "C")] == (3, -1.0)
    assert corr[("B", "C")] == (3, -1.0)
    assert out["corr"].is_monotonic_decreasing


def test_04_counts_only_days_where_both_have_a_return(con):
    add_prices(con, series("A", [100, 110, 99, 108.9, 120]))           # returns on days 1-4
    add_prices(con, series("B", [10, 11, 12], start=str(day(2))))      # returns on days 3-4
    out = run_sql(con, "analysis/04_correlations.sql")

    assert out["n_days"].tolist() == [2]


def test_04_excludes_suspect_rows_of_either_ticker(con):
    add_prices(con, series("A", [100, 110, 99, 108.9]))
    add_prices(con, [bar(day(0), "B", close=10.0), bar(day(1), "B", close=11.0),
                     raw(day(2), "B", 12, 11, 9, 10, 5),               # suspect: open above high
                     bar(day(3), "B", close=12.0)])
    out = run_sql(con, "analysis/04_correlations.sql")

    assert out["n_days"].tolist() == [2]                               # day 2 dropped for the pair


# ---05: final values---

def test_05_final_index_and_drawdowns(con):
    add_prices(con, series("A", [100, 120, 60, 90]))
    out = by_ticker(run_sql(con, "analysis/05_final_values.sql")).loc["A"]

    assert pd.Timestamp(out["last_date"]).date() == day(3)
    assert out["final_norm_price"] == pytest.approx(90.0)              # first close = 100
    assert out["final_drawdown_pct"] == pytest.approx(-25.0)           # 90 / 120 - 1
    assert out["max_drawdown_pct"] == pytest.approx(-50.0)


def test_05_index_starts_at_the_first_non_suspect_close(con):
    add_prices(con, [raw(day(0), "A", 40, 40, 40, 40, 0),              # suspect first row
                     bar(day(1), close=50.0), bar(day(2), close=75.0)])
    out = by_ticker(run_sql(con, "analysis/05_final_values.sql")).loc["A"]

    assert out["final_norm_price"] == pytest.approx(150.0)             # 75 / 50, not 75 / 40


def test_05_agrees_with_03_on_the_maximum_drawdown(con):
    add_prices(con, series("A", [100, 120, 60, 90]) + series("B", [50, 40, 45, 30, 60]))
    final = by_ticker(run_sql(con, "analysis/05_final_values.sql"))
    worst = by_ticker(run_sql(con, "analysis/03_max_drawdown.sql"))

    for ticker in ("A", "B"):
        assert final.loc[ticker, "max_drawdown_pct"] == worst.loc[ticker, "max_drawdown_pct"]
    assert final.index.tolist() == ["A", "B"]
