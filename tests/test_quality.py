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


def issues_by_ticker(out):
    return {t: sorted(set(g["issues"])) for t, g in out.groupby("ticker")}


def test_08_lists_exactly_the_rows_counted_by_07(integrity):
    out = run_sql(integrity, "quality/08_integrity_detail.sql")
    rows_per_ticker = out.groupby("ticker").size().to_dict()

    assert rows_per_ticker == {"NULLPRICE": 1, "NONPOS": 1, "OPENHIGH": 1, "OPENLOW": 1,
                               "CLOSEOUT": 1, "HIGHLOW": 1,
                               "DUP": 2}       # both rows of the duplicated key, not the third
    assert "CLEAN" not in rows_per_ticker


def test_08_names_every_issue_of_each_row(integrity):
    out = run_sql(integrity, "quality/08_integrity_detail.sql")

    assert issues_by_ticker(out) == {
        "NULLPRICE": ["null_price"],
        "NONPOS":    ["non_positive"],
        "OPENHIGH":  ["open_outside"],
        "OPENLOW":   ["open_outside"],
        "CLOSEOUT":  ["close_outside"],
        # high < low leaves no valid range, so open and close are outside it too
        "HIGHLOW":   ["high_below_low, open_outside, close_outside"],
        "DUP":       ["duplicate_key"],
    }


def test_08_open_gap_measures_how_far_the_open_is_outside_the_range(integrity):
    out = run_sql(integrity, "quality/08_integrity_detail.sql")
    gap = {r.ticker: r.open_gap for r in out.itertuples() if r.ticker != "DUP"}

    assert gap["OPENHIGH"] == 1.0                          # open 12 - high 11
    assert gap["OPENLOW"] == 1.0                           # low 9 - open 8
    assert gap["NONPOS"] == 0.0 and gap["CLOSEOUT"] == 0.0


def test_08_lists_all_issues_of_a_row_and_orders_by_date(con):
    add_prices(con, [raw(dt.date(2024, 1, 5), "A", 12, 11, 9, 10, 5),
                     raw(dt.date(2024, 1, 3), "A", 5, 2, -1, 1, 5)])    # non-positive and open outside
    out = run_sql(con, "quality/08_integrity_detail.sql")

    assert [d.date() for d in pd.to_datetime(out["date"])] == [dt.date(2024, 1, 3), dt.date(2024, 1, 5)]
    assert out["issues"].tolist() == ["non_positive, open_outside", "open_outside"]
    assert out["open_gap"].tolist() == [3.0, 1.0]


def test_08_is_empty_for_clean_data(con):
    add_prices(con, series("A", [10, 11, 12]) + series("B", [5, 6]))

    assert run_sql(con, "quality/08_integrity_detail.sql").empty


# 07 column -> label used in the `issues` column of 08
ISSUE_LABELS = {"null_prices": "null_price", "non_positive": "non_positive",
                "high_below_low": "high_below_low", "open_outside": "open_outside",
                "close_outside": "close_outside"}


def test_08_row_counts_per_issue_match_the_counts_of_07(integrity):
    # Extra rows so that some tickers have several problems, on one row or on several
    add_prices(integrity, [
        raw(dt.date(2024, 1, 4), "NONPOS", 5, 2, -1, 1, 5),            # non-positive + open outside
        raw(dt.date(2024, 1, 5), "NONPOS", None, 11, 9, 12, 5),        # NULL open + close outside
        raw(dt.date(2024, 1, 4), "DUP", 10, 11, 9, 8, 5),              # duplicated key whose rows
        raw(dt.date(2024, 1, 4), "DUP", 10, 11, 9, 8, 5),              # are also close outside
        raw(dt.date(2024, 1, 4), "DUP", 10, 11, 9, 8, 5),
    ])
    counts = run_sql(integrity, "quality/07_integrity_checks.sql").set_index("ticker")
    detail = run_sql(integrity, "quality/08_integrity_detail.sql")
    labels = detail["issues"].str.split(", ")

    for ticker in counts.index:
        of_ticker = detail["ticker"] == ticker
        for column, label in ISSUE_LABELS.items():
            listed = (of_ticker & labels.apply(lambda found: label in found)).sum()
            assert listed == counts.loc[ticker, column], (ticker, column)
        # 07 counts duplicated keys, 08 lists their rows: compare distinct keys
        dup_rows = detail[of_ticker & labels.apply(lambda found: "duplicate_key" in found)]
        assert dup_rows["date"].nunique() == counts.loc[ticker, "duplicate_keys"], ticker

    assert counts.loc["DUP", "duplicate_keys"] == 2
    assert counts.loc["NONPOS", ["null_prices", "non_positive", "open_outside",
                                 "close_outside"]].tolist() == [1, 2, 1, 1]
    # only known labels appear, and every listed row has at least one
    assert {l for found in labels for l in found} <= set(ISSUE_LABELS.values()) | {"duplicate_key"}
    assert (detail["issues"] != "").all()


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


def test_09_has_no_infinite_return_after_a_zero_close(con):
    add_prices(con, [bar(dt.date(2024, 1, 2), close=10.0),
                     raw(dt.date(2024, 1, 3), "A", 1, 2, 0, 0, 5),
                     bar(dt.date(2024, 1, 4), close=10.0),
                     bar(dt.date(2024, 1, 5), close=11.0)])
    out = run_sql(con, "quality/09_largest_moves.sql")

    assert np.isfinite(out["ret"]).all()
    assert out["ret"].tolist() == [0.1]                    # only 10 -> 11 has a valid return


def test_09_has_no_return_measured_from_or_to_a_non_positive_close(con):
    # Same rule as prices_clean: both the close and the previous close must be positive
    add_prices(con, [raw(dt.date(2024, 1, 2), "A", 18, 19, 17, 18.27, 5),
                     raw(dt.date(2024, 1, 3), "A", 17, 18, -40, -37.63, 5),
                     raw(dt.date(2024, 1, 4), "A", -14, 13, -16, 10.01, 5),
                     raw(dt.date(2024, 1, 5), "A", 10, 14, 10, 13.78, 5)])
    out = run_sql(con, "quality/09_largest_moves.sql")

    assert ((out["prev_close"] > 0) & (out["close"] > 0)).all()
    assert len(out) == 1
    assert out["ret"].tolist() == [round(13.78 / 10.01 - 1, 4)]


def test_09_lists_the_same_returns_as_the_clean_view(con):
    add_prices(con, series("A", [100, 110, 55, 56.1])
               + [raw(dt.date(2024, 1, 5), "A", 1, 2, -3, -1, 5), bar(dt.date(2024, 1, 8), close=50.0)])
    moves = run_sql(con, "quality/09_largest_moves.sql")
    view = con.sql("SELECT date, ROUND(ret, 4) AS ret FROM prices_clean WHERE ret IS NOT NULL").df()

    assert sorted(moves["ret"]) == sorted(view["ret"])
    assert set(pd.to_datetime(moves["date"])) == set(pd.to_datetime(view["date"]))


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
