import pandas as pd
import yfinance as yf

TICKERS = ["CL=F", "BZ=F", "NG=F", "GC=F", "HG=F", "ZW=F"]
START = "2016-01-01"
END = "2026-01-01"  # yfinance's end date is exclusive, so this includes 2025-12-31
OUTPUT = "data/raw_prices.parquet"

frames = []
for ticker in TICKERS:
    # Download one ticker at a time
    df = yf.download(ticker, start=START, end=END, auto_adjust=False, progress=False)

    # Flatten multi-level columns like ("Close", "CL=F") -> "Close"
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Move the date from the index into a column and add the ticker
    df = df.reset_index()
    df.columns = [str(c).lower() for c in df.columns]
    df["ticker"] = ticker

    # Keep only the columns we need (no cleaning)
    frames.append(df[["date", "ticker", "open", "high", "low", "close", "volume"]])

# Combine all tickers into one table and save it
prices = pd.concat(frames, ignore_index=True)
prices.to_parquet(OUTPUT, index=False)

print(prices.head(5))
print()
print("Rows per ticker:")
print(prices["ticker"].value_counts(sort=False))
