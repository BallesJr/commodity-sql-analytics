from pathlib import Path

import pandas as pd
import yfinance as yf

TICKERS = ["CL=F", "BZ=F", "NG=F", "GC=F", "HG=F", "ZW=F"]
START = "2016-01-01"
END = "2026-01-01"  # yfinance's end date is exclusive, so this includes 2025-12-31
OUTPUT = "data/raw_prices.parquet"


def download_prices(tickers=TICKERS, start=START, end=END, downloader=None):
    """Download daily prices for each ticker and return them as one long table.

    `downloader` is the function that fetches one ticker (yfinance's `download`
    by default); passing another one lets the function run without network.
    """
    if downloader is None:
        downloader = yf.download

    frames = []
    for ticker in tickers:
        # Download one ticker at a time
        df = downloader(ticker, start=start, end=end, auto_adjust=False, progress=False)

        # Flatten multi-level columns like ("Close", "CL=F") -> "Close"
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Move the date from the index into a column and add the ticker
        df = df.reset_index()
        df.columns = [str(c).lower() for c in df.columns]
        df["ticker"] = ticker

        # Keep only the columns we need (no cleaning)
        frames.append(df[["date", "ticker", "open", "high", "low", "close", "volume"]])

    # Combine all tickers into one table
    return pd.concat(frames, ignore_index=True)


def save_prices(prices, output=OUTPUT):
    """Save the price table as a parquet file, creating its folder if needed."""
    Path(output).parent.mkdir(parents=True, exist_ok=True)  # data/ is not in git, create it if missing
    prices.to_parquet(output, index=False)


def main():
    prices = download_prices()
    save_prices(prices)

    print(prices.head(5))
    print()
    print("Rows per ticker:")
    print(prices["ticker"].value_counts(sort=False))


if __name__ == "__main__":
    main()
