"""The data quality checks in sql/quality/, each against hand-made rows."""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from helpers import add_instruments, add_prices, bar, raw, run_sql, series

WEEKDAYS = pd.bdate_range("2016-01-01", "2025-12-31")     # the calendar the checks expect
N_WEEKDAYS = 2609


def fill_calendar(con, tickers, skip=()):
    """Insert a healthy row for every weekday of 2016-2025 and every ticker,
    except the (date, ticker) pairs in `skip`."""
    skip = set(skip)
    df = pd.DataFrame([(d.date(), t) for t in tickers for d in WEEKDAYS
                       if (d.date(), t) not in skip], columns=["date", "ticker"])
    df["open"], df["high"], df["low"], df["close"], df["volume"] = 10.0, 11.0, 9.0, 10.0, 100
    con.register("calendar_rows", df)
    con.execute("INSERT INTO prices SELECT * FROM calendar_rows")
    con.unregister("calendar_rows")


def by_ticker(df):
    return df.set_index("ticker")


# ---01-03: missing days---

def test_calendar_has_the_documented_number_of_weekdays():
    assert len(WEEKDAYS) == N_WEEKDAYS


def test_01_counts_missing_weekdays_per_ticker(con):
    add_instruments(con, ["FULL", "GAPS", "EMPTY"])
    gaps = {(dt.date(2018, 1, 29), "GAPS"), (dt.date(2023, 11, 23), "GAPS")}
    fill_calendar(con, ["FULL", "GAPS"], skip=gaps)
    add_prices(con, [bar(dt.date(2024, 1, 6), "GAPS")])    # a Saturday row changes nothing

    out = by_ticker(run_sql(con, "quality/01_missing_days.sql"))

    assert out.loc["GAPS", "missing_days"] == 2
    assert out.loc["EMPTY", "missing_days"] == N_WEEKDAYS
    assert "FULL" not in out.index                         # nothing missing, no row


def test_01_only_checks_tickers_listed_in_instruments(con):
    add_instruments(con, ["LISTED"])
    fill_calendar(con, ["LISTED"])
    add_prices(con, [bar(dt.date(2024, 1, 2), "UNLISTED")])

    assert run_sql(con, "quality/01_missing_days.sql").empty


@pytest.fixture
def six_tickers_with_gaps(con):
    """Six tickers with a full calendar except: one date missing for two of them,
    one date missing for one, one date missing for all six."""
    tickers = ["T1", "T2", "T3", "T4", "T5", "T6"]
    add_instruments(con, tickers)
    partial_two, partial_one, everyone = dt.date(2018, 1, 29), dt.date(2025, 7, 4), dt.date(2020, 12, 25)
    skip = ({(partial_two, "T2"), (partial_two, "T1"), (partial_one, "T6")}
            | {(everyone, t) for t in tickers})
    fill_calendar(con, tickers, skip=skip)
    return con, partial_two, partial_one, everyone


def test_02_groups_dates_by_number_of_tickers_missing(six_tickers_with_gaps):
    con, *_ = six_tickers_with_gaps
    out = run_sql(con, "quality/02_missing_days_summary.sql")

    assert dict(zip(out["n_tickers_missing"], out["n_dates"])) == {1: 1, 2: 1, 6: 1}
    assert out["n_tickers_missing"].tolist() == [1, 2, 6]


def test_03_lists_only_dates_missing_for_some_tickers(six_tickers_with_gaps):
    con, partial_two, partial_one, everyone = six_tickers_with_gaps
    out = run_sql(con, "quality/03_missing_days_partial.sql")

    assert [d.date() for d in pd.to_datetime(out["date"])] == [partial_two, partial_one]
    assert out["weekday"].tolist() == ["Monday", "Friday"]
    assert out["n_tickers_missing"].tolist() == [2, 1]
    assert out["tickers_missing"].tolist() == ["T1, T2", "T6"]         # sorted by ticker


# ---04-06: zero volume and flat bars---

@pytest.fixture
def suspicious(con):
    add_prices(con, [
        bar(dt.date(2023, 4, 6), "A", volume=0),                       # zero volume
        raw(dt.date(2023, 4, 7), "A", 10, 10, 10, 10, 5),              # flat bar
        raw(dt.date(2024, 1, 2), "A", 10, 10, 10, 10, 0),              # both
        raw(dt.date(2024, 1, 3), "A", 10, 11, 9, 10, None),            # NULL volume
        bar(dt.date(2025, 6, 18), "A"),                                # healthy
        bar(dt.date(2023, 4, 6), "B", volume=0),                       # zero volume, same date as A
        bar(dt.date(2024, 5, 1), "B", volume=0),                       # zero volume in 2024
        bar(dt.date(2025, 6, 18), "B", volume=0),
        bar(dt.date(2023, 4, 6), "C"),                                 # healthy ticker
        bar(dt.date(2024, 1, 2), "C"),
    ])
    return con


def test_04_counts_zero_volume_null_volume_and_flat_bars(suspicious):
    out = by_ticker(run_sql(suspicious, "quality/04_suspicious_rows.sql"))
    columns = ["n_rows", "zero_volume", "null_volume", "flat_bars"]

    assert out.loc["A", columns].tolist() == [5, 2, 1, 2]
    assert out.loc["B", columns].tolist() == [3, 3, 0, 0]
    assert out.loc["C", columns].tolist() == [2, 0, 0, 0]


def test_05_breaks_the_counts_down_by_year(suspicious):
    out = run_sql(suspicious, "quality/05_suspicious_by_year.sql")
    rows = {(r.ticker, r.yr): (r.zero_volume, r.flat_bars, r.both) for r in out.itertuples()}

    assert rows == {
        ("A", 2023): (1, 1, 0),        # one of each, on different rows
        ("A", 2024): (1, 1, 1),        # the same row is both
        ("B", 2023): (1, 0, 0),
        ("B", 2024): (1, 0, 0),
        ("B", 2025): (1, 0, 0),
    }                                  # A 2025 and all of C are clean: no row
    assert list(zip(out["ticker"], out["yr"])) == sorted(rows)


def test_06_lists_zero_volume_dates_of_2023_and_2025_only(suspicious):
    out = run_sql(suspicious, "quality/06_zero_volume_dates.sql")

    assert [d.date() for d in pd.to_datetime(out["date"])] == [dt.date(2023, 4, 6), dt.date(2025, 6, 18)]
    assert out["weekday"].tolist() == ["Thursday", "Wednesday"]
    assert out["n_tickers"].tolist() == [2, 1]
    assert out["tickers"].tolist() == ["A, B", "B"]
    # The 2024 zero-volume rows exist but the query has the years hard-coded
    assert suspicious.sql("SELECT COUNT(*) FROM prices WHERE volume = 0 AND year(date) = 2024").fetchone()[0] == 2


# ---07-08: integrity---

D = dt.date(2024, 1, 2)
INTEGRITY_COLUMNS = ["null_prices", "non_positive", "high_below_low", "open_outside",
                     "close_outside", "duplicate_keys"]


@pytest.fixture
def integrity(con):
    add_prices(con, [
        bar(D, "CLEAN"), bar(dt.date(2024, 1, 3), "CLEAN"),
        raw(D, "NULLPRICE", None, 11, 9, 10, 5),
        raw(D, "NONPOS", 1, 2, 0, 1, 5),                   # low = 0, otherwise consistent
        raw(D, "OPENHIGH", 12, 11, 9, 10, 5),              # open above high
        raw(D, "OPENLOW", 8, 11, 9, 10, 5),                # open below low
        raw(D, "CLOSEOUT", 10, 11, 9, 8, 5),               # close below low
        raw(D, "HIGHLOW", 10, 9, 11, 10, 5),               # high below low
        bar(D, "DUP"), bar(D, "DUP"), bar(dt.date(2024, 1, 3), "DUP"),
    ])
    return con


def test_07_each_bad_row_increments_its_own_counter(integrity):
    out = by_ticker(run_sql(integrity, "quality/07_integrity_checks.sql"))
    counts = {t: out.loc[t, INTEGRITY_COLUMNS].tolist() for t in out.index}

    assert counts == {
        "CLEAN":     [0, 0, 0, 0, 0, 0],
        "NULLPRICE": [1, 0, 0, 0, 0, 0],
        "NONPOS":    [0, 1, 0, 0, 0, 0],
        "OPENHIGH":  [0, 0, 0, 1, 0, 0],
        "OPENLOW":   [0, 0, 0, 1, 0, 0],
        "CLOSEOUT":  [0, 0, 0, 0, 1, 0],
        # high < low leaves no valid range, so open and close are outside it too
        "HIGHLOW":   [0, 0, 1, 1, 1, 0],
        "DUP":       [0, 0, 0, 0, 0, 1],                   # one duplicated key, not two rows
    }
    assert list(out.index) == sorted(out.index)


def test_08_details_non_positive_and_open_outside_rows(integrity):
    out = run_sql(integrity, "quality/08_integrity_detail.sql")
    detail = {r.ticker: (r.issue, r.open_gap) for r in out.itertuples()}

    assert detail["NONPOS"] == ("non_positive", 0.0)
    assert detail["OPENHIGH"] == ("open_outside", 1.0)     # open 12 - high 11
    assert detail["OPENLOW"] == ("open_outside", 1.0)      # low 9 - open 8
    assert "CLEAN" not in detail and "DUP" not in detail


def test_08_non_positive_label_wins_and_rows_are_ordered_by_date(con):
    add_prices(con, [raw(dt.date(2024, 1, 5), "A", 12, 11, 9, 10, 5),
                     raw(dt.date(2024, 1, 3), "A", 5, 2, -1, 1, 5)])    # non-positive and open outside
    out = run_sql(con, "quality/08_integrity_detail.sql")

    assert [d.date() for d in pd.to_datetime(out["date"])] == [dt.date(2024, 1, 3), dt.date(2024, 1, 5)]
    assert out["issue"].tolist() == ["non_positive", "open_outside"]
    assert out["open_gap"].tolist() == [3.0, 1.0]


DETAIL_BUG = ("Known bug: 08_integrity_detail only filters on non-positive prices and open outside "
              "the range, so it does not list every row that 07_integrity_checks counts: a close "
              "outside the range is missing, and high < low is reported as 'open_outside'.")


@pytest.mark.xfail(strict=True, reason=DETAIL_BUG)
def test_08_lists_every_row_counted_by_07(integrity):
    out = run_sql(integrity, "quality/08_integrity_detail.sql")

    assert set(out["ticker"]) == {"NONPOS", "OPENHIGH", "OPENLOW", "CLOSEOUT", "HIGHLOW"}


@pytest.mark.xfail(strict=True, reason=DETAIL_BUG)
def test_08_labels_a_close_outside_the_range(integrity):
    out = run_sql(integrity, "quality/08_integrity_detail.sql")
    issues = dict(zip(out["ticker"], out["issue"]))

    assert issues.get("CLOSEOUT") == "close_outside"


@pytest.mark.xfail(strict=True, reason=DETAIL_BUG)
def test_08_labels_high_below_low(integrity):
    out = run_sql(integrity, "quality/08_integrity_detail.sql")
    issues = dict(zip(out["ticker"], out["issue"]))

    assert issues.get("HIGHLOW") == "high_below_low"


# ---09: largest moves---

def test_09_ranks_moves_by_absolute_size(con):
    add_prices(con, series("A", [100, 110, 55, 56.1]) + series("B", [10, 10.5]))
    out = run_sql(con, "quality/09_largest_moves.sql")

    assert out["ret"].tolist() == [-0.5, 0.1, 0.05, 0.02]  # 55/110, 110/100, 10.5/10, 56.1/55
    assert out["ticker"].tolist() == ["A", "A", "B", "A"]
    top = out.iloc[0]
    assert (top["prev_close"], top["close"]) == (110.0, 55.0)
    assert (pd.Timestamp(top["prev_date"]).date(), pd.Timestamp(top["date"]).date()) == (
        dt.date(2024, 1, 2), dt.date(2024, 1, 3))


def test_09_skips_the_first_row_of_each_ticker_and_rounds_to_four_decimals(con):
    add_prices(con, series("A", [3, 4]) + series("B", [7, 7]))
    out = run_sql(con, "quality/09_largest_moves.sql")

    assert len(out) == 2                                   # 4 rows, 2 first rows skipped
    assert out["ret"].tolist() == [0.3333, 0.0]


def test_09_returns_at_most_fifteen_rows(con):
    add_prices(con, series("A", [100 + i for i in range(30)]))

    assert len(run_sql(con, "quality/09_largest_moves.sql")) == 15


MOVES_BUG = ("Known bug: 09_largest_moves divides by the previous close without checking that it "
             "is positive (the view does check), so a previous close of 0 gives an infinite "
             "return and a negative one gives a return with a meaningless sign and size.")


@pytest.mark.xfail(strict=True, reason=MOVES_BUG)
def test_09_has_no_infinite_return_after_a_zero_close(con):
    add_prices(con, [bar(dt.date(2024, 1, 2), close=10.0),
                     raw(dt.date(2024, 1, 3), "A", 1, 2, 0, 0, 5),
                     bar(dt.date(2024, 1, 4), close=10.0)])
    out = run_sql(con, "quality/09_largest_moves.sql")

    assert np.isfinite(out["ret"].dropna()).all()


@pytest.mark.xfail(strict=True, reason=MOVES_BUG)
def test_09_has_no_return_measured_from_a_non_positive_close(con):
    add_prices(con, [raw(dt.date(2024, 1, 2), "A", 18, 19, 17, 18.27, 5),
                     raw(dt.date(2024, 1, 3), "A", 17, 18, -40, -37.63, 5),
                     raw(dt.date(2024, 1, 6), "A", -14, 13, -16, 10.01, 5)])
    out = run_sql(con, "quality/09_largest_moves.sql")

    from_bad_close = out[out["prev_close"] <= 0]
    assert from_bad_close["ret"].isna().all()


# ---10-11: checks on the clean view---

@pytest.fixture
def view_rows(con):
    add_prices(con, [
        bar(dt.date(2024, 1, 2), "A"),
        raw(dt.date(2024, 1, 3), "A", 10, 10, 10, 10, 0),              # suspect: placeholder
        bar(dt.date(2024, 1, 4), "A", volume=0),                       # zero volume only
        raw(dt.date(2024, 1, 5), "A", 12, 11, 9, 10, 5),               # suspect: OHLC
        bar(dt.date(2024, 1, 2), "B"),
        raw(dt.date(2024, 1, 3), "B", 1, 2, -3, -1, 5),                # negative close
        bar(dt.date(2024, 1, 4), "B"),
    ])
    return con


def test_10_summarises_the_view_per_ticker(view_rows):
    out = by_ticker(run_sql(view_rows, "quality/10_clean_view_check.sql"))
    columns = ["n_rows", "n_suspect", "n_null_ret", "n_null_volume"]

    assert out.loc["A", columns].tolist() == [4, 2, 1, 2]              # first row; two zero volumes
    assert out.loc["B", columns].tolist() == [3, 0, 3, 0]              # first row + both sides of the negative close


def test_11_lists_exactly_the_suspect_rows(view_rows):
    out = run_sql(view_rows, "quality/11_suspect_rows.sql")

    assert out["ticker"].tolist() == ["A", "A"]
    assert [d.date() for d in pd.to_datetime(out["date"])] == [dt.date(2024, 1, 3), dt.date(2024, 1, 5)]
    assert pd.isna(out["volume"].iloc[0])                               # zero volume shown as NULL
    assert list(out.columns) == ["date", "ticker", "open", "high", "low", "close", "volume"]
