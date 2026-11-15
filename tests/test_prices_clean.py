"""The prices_clean view: flags, NULL volume, is_suspect and returns."""
import datetime as dt
import math

import pytest

from helpers import add_prices, bar, clean_row, raw

D1, D2, D3, D4 = (dt.date(2024, 1, d) for d in (2, 3, 4, 5))
FLAGS = ["flag_zero_volume", "flag_flat_bar", "flag_ohlc_inconsistent", "flag_non_positive"]


# ---Flags---

def test_healthy_row_has_every_flag_false(con):
    add_prices(con, [bar(D1)])
    row = clean_row(con, D1)

    assert [row[f] for f in FLAGS] == [False, False, False, False]
    assert row["is_suspect"] is False
    assert row["volume"] == 100


def test_zero_volume_is_flagged_and_becomes_null(con):
    add_prices(con, [bar(D1, volume=0), bar(D2, volume=1)])

    assert clean_row(con, D1)["flag_zero_volume"] is True
    assert clean_row(con, D1)["volume"] is None
    assert clean_row(con, D2)["flag_zero_volume"] is False
    assert clean_row(con, D2)["volume"] == 1               # positive volume is kept


def test_flat_bar_needs_all_four_prices_equal(con):
    add_prices(con, [raw(D1, "A", 10, 10, 10, 10, 5),      # flat
                     raw(D2, "A", 10, 10, 10, 10.5, 5),    # close differs (also inconsistent)
                     raw(D3, "A", 10, 11, 10, 10, 5)])     # high differs

    assert clean_row(con, D1)["flag_flat_bar"] is True
    assert clean_row(con, D2)["flag_flat_bar"] is False
    assert clean_row(con, D3)["flag_flat_bar"] is False


@pytest.mark.parametrize("o, h, l, c, case", [
    (10, 9, 11, 10, "high below low"),
    (12, 11, 9, 10, "open above high"),
    (8, 11, 9, 10, "open below low"),
    (10, 11, 9, 12, "close above high"),
    (10, 11, 9, 8, "close below low"),
])
def test_each_ohlc_inconsistency_is_flagged(con, o, h, l, c, case):
    add_prices(con, [raw(D1, "A", o, h, l, c, 5)])

    assert clean_row(con, D1)["flag_ohlc_inconsistent"] is True, case


@pytest.mark.parametrize("o, h, l, c", [
    (10, 11, 9, 10),       # inside the range
    (11, 11, 9, 9),        # open at the high, close at the low: still consistent
    (10, 10, 10, 10),      # flat bar is consistent
])
def test_consistent_bars_are_not_flagged(con, o, h, l, c):
    add_prices(con, [raw(D1, "A", o, h, l, c, 5)])

    assert clean_row(con, D1)["flag_ohlc_inconsistent"] is False


@pytest.mark.parametrize("o, h, l, c, expected", [
    (10, 11, 9, 10, False),
    (1, 2, 0, 1, True),            # a zero counts as non-positive
    (-14, -10, -40, -37.63, True),
    (1, 2, 0.01, 1, False),
])
def test_non_positive_flag_looks_at_the_lowest_price(con, o, h, l, c, expected):
    add_prices(con, [raw(D1, "A", o, h, l, c, 5)])

    assert clean_row(con, D1)["flag_non_positive"] is expected


# ---is_suspect---

@pytest.mark.parametrize("row, expected, case", [
    (raw(D1, "A", 10, 11, 9, 10, 0), False, "zero volume alone"),
    (raw(D1, "A", 10, 10, 10, 10, 5), False, "flat bar alone"),
    (raw(D1, "A", 10, 10, 10, 10, 0), True, "zero volume and flat bar"),
    (raw(D1, "A", 12, 11, 9, 10, 5), True, "OHLC inconsistent"),
    (raw(D1, "A", -14, -10, -40, -37.63, 5), False, "non-positive but consistent"),
])
def test_is_suspect_truth_table(con, row, expected, case):
    add_prices(con, [row])

    assert clean_row(con, D1)["is_suspect"] is expected, case


def test_view_keeps_every_row_of_prices(con):
    add_prices(con, [raw(D1, "A", 10, 10, 10, 10, 0),      # suspect
                     raw(D2, "A", 12, 11, 9, 10, 5),       # suspect
                     bar(D3), bar(D1, "B")])

    assert con.sql("SELECT COUNT(*) FROM prices_clean").fetchone()[0] == 4
    assert con.sql("SELECT COUNT(*) FROM prices").fetchone()[0] == 4


# ---Returns---

def test_returns_match_hand_calculation(con):
    add_prices(con, [bar(D1, close=10.0), bar(D2, close=11.0), bar(D3, close=9.9)])

    assert clean_row(con, D2)["prev_close"] == 10.0
    assert clean_row(con, D2)["ret"] == pytest.approx(0.1)
    assert clean_row(con, D2)["log_ret"] == pytest.approx(math.log(1.1))
    assert clean_row(con, D3)["ret"] == pytest.approx(-0.1)
    assert clean_row(con, D3)["log_ret"] == pytest.approx(math.log(0.9))


def test_first_row_of_each_ticker_has_no_return(con):
    add_prices(con, [bar(D1, "A"), bar(D2, "A"), bar(D2, "B"), bar(D3, "B")])

    for date, ticker in ((D1, "A"), (D2, "B")):
        row = clean_row(con, date, ticker)
        assert (row["prev_close"], row["ret"], row["log_ret"]) == (None, None, None)


def test_returns_are_null_when_close_or_previous_close_is_not_positive(con):
    add_prices(con, [raw(D1, "A", 18, 19, 17, 18.27, 5),
                     raw(D2, "A", 17, 18, -40, -37.63, 5),     # close <= 0
                     raw(D3, "A", -14, 13, -16, 10.01, 5),     # previous close <= 0
                     raw(D4, "A", 10, 12, 9, 11.0, 5)])

    assert clean_row(con, D2)["ret"] is None and clean_row(con, D2)["log_ret"] is None
    assert clean_row(con, D3)["ret"] is None and clean_row(con, D3)["log_ret"] is None
    assert clean_row(con, D4)["ret"] == pytest.approx(11.0 / 10.01 - 1)


def test_zero_close_gives_null_returns_on_both_sides(con):
    add_prices(con, [bar(D1, close=10.0), raw(D2, "A", 1, 2, 0, 0, 5), bar(D3, close=10.0)])

    assert clean_row(con, D2)["ret"] is None
    assert clean_row(con, D3)["ret"] is None


def test_previous_close_never_crosses_tickers(con):
    add_prices(con, [bar(D1, "A", close=10.0), bar(D2, "A", close=20.0),
                     bar(D1, "B", close=100.0), bar(D2, "B", close=110.0)])

    assert clean_row(con, D2, "A")["prev_close"] == 10.0
    assert clean_row(con, D2, "B")["prev_close"] == 100.0
    assert clean_row(con, D2, "B")["ret"] == pytest.approx(0.1)


def test_previous_close_follows_dates_not_insertion_order(con):
    add_prices(con, [bar(D3, close=30.0), bar(D1, close=10.0), bar(D2, close=20.0)])

    assert clean_row(con, D2)["prev_close"] == 10.0
    assert clean_row(con, D3)["prev_close"] == 20.0


def test_return_is_per_row_so_it_spans_missing_days(con):
    # Current behaviour: with D2 missing, the D3 return covers two days
    add_prices(con, [bar(D1, close=10.0), bar(D3, close=12.0)])

    assert clean_row(con, D3)["prev_close"] == 10.0
    assert clean_row(con, D3)["ret"] == pytest.approx(0.2)


def test_return_after_a_suspect_row_is_measured_from_the_suspect_close(con):
    # Current behaviour: returns are computed on all rows, suspect ones included
    add_prices(con, [bar(D1, close=100.0), raw(D2, "A", 50, 50, 50, 50, 0), bar(D3, close=110.0)])

    assert clean_row(con, D2)["is_suspect"] is True
    assert clean_row(con, D3)["prev_close"] == 50.0
    assert clean_row(con, D3)["ret"] == pytest.approx(1.2)


# ---Known issue: NULL inputs give NULL flags instead of false---

NULL_FLAGS_BUG = ("Known bug: the flags are plain comparisons, so a NULL volume or price makes "
                  "them NULL instead of false; is_suspect then becomes NULL and "
                  "'WHERE NOT is_suspect' silently drops the row from every analysis query.")


@pytest.mark.xfail(strict=True, reason=NULL_FLAGS_BUG)
def test_null_volume_gives_false_flags_not_null(con):
    add_prices(con, [raw(D1, "A", 10, 11, 9, 10, None)])
    row = clean_row(con, D1)

    assert [row[f] for f in FLAGS] == [False, False, False, False]
    assert row["is_suspect"] is False


@pytest.mark.xfail(strict=True, reason=NULL_FLAGS_BUG)
def test_flat_bar_with_null_volume_is_not_suspect(con):
    # Unknown volume is not zero volume, so the placeholder rule does not apply
    add_prices(con, [raw(D1, "A", 10, 10, 10, 10, None)])
    row = clean_row(con, D1)

    assert row["flag_flat_bar"] is True
    assert row["flag_zero_volume"] is False
    assert row["is_suspect"] is False


@pytest.mark.xfail(strict=True, reason=NULL_FLAGS_BUG)
def test_null_price_gives_false_flags_not_null(con):
    add_prices(con, [raw(D1, "A", None, 11, 9, 10, 5)])
    row = clean_row(con, D1)

    assert [row[f] for f in FLAGS] == [False, False, False, False]
    assert row["is_suspect"] is False


@pytest.mark.xfail(strict=True, reason=NULL_FLAGS_BUG)
def test_rows_with_nulls_are_not_dropped_by_the_not_is_suspect_filter(con):
    add_prices(con, [bar(D1), raw(D2, "A", 10, 10, 10, 10, None), raw(D3, "A", None, 11, 9, 10, 5)])

    kept = con.sql("SELECT COUNT(*) FROM prices_clean WHERE NOT is_suspect").fetchone()[0]
    assert kept == 3
