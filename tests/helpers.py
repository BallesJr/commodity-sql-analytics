"""Small helpers shared by the tests: paths, row builders and query runners."""
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
SQL = REPO / "sql"
REAL_DATABASE = REPO / "data" / "commodities.duckdb"
REAL_PARQUET = REPO / "data" / "raw_prices.parquet"

PRICE_COLUMNS = ["date", "ticker", "open", "high", "low", "close", "volume"]


def bar(date, ticker="A", close=10.0, open=None, high=None, low=None, volume=100):
    """One healthy price row: consistent OHLC, not flat, positive volume.

    By default open = close, high = close + 1 and low = close - 1; any field can
    be overridden to build a specific bad case.
    """
    return (
        date,
        ticker,
        close if open is None else open,
        close + 1 if high is None else high,
        close - 1 if low is None else low,
        close,
        volume,
    )


def raw(date, ticker, open, high, low, close, volume):
    """A price row with every field given explicitly (None becomes NULL)."""
    return (date, ticker, open, high, low, close, volume)


def add_prices(con, rows):
    """Insert price rows (tuples in PRICE_COLUMNS order) into the prices table."""
    con.executemany("INSERT INTO prices VALUES (?, ?, ?, ?, ?, ?, ?)", list(rows))


def add_instruments(con, tickers):
    con.executemany("INSERT INTO instruments VALUES (?, ?, 'Sector', 'unit')",
                    [(t, f"Name {t}") for t in tickers])


def series(ticker, closes, start="2024-01-01"):
    """Healthy rows for consecutive business days with the given closes."""
    dates = pd.bdate_range(start, periods=len(closes))
    return [bar(d.date(), ticker, float(c)) for d, c in zip(dates, closes)]


def run_sql(con, relative_path):
    """Run one of the project's .sql files and return a DataFrame."""
    return con.sql((SQL / relative_path).read_text(encoding="utf-8")).df()


def clean_row(con, date, ticker="A"):
    """The prices_clean row of one (date, ticker) as a dict of Python values."""
    cur = con.execute("SELECT * FROM prices_clean WHERE date = ? AND ticker = ?", [date, ticker])
    names = [d[0] for d in cur.description]
    rows = cur.fetchall()
    assert len(rows) == 1, f"expected one row for {date} {ticker}, got {len(rows)}"
    return dict(zip(names, rows[0]))
