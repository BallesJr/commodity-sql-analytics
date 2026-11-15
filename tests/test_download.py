"""download.py with a fake downloader: no network involved."""
import pandas as pd
import pytest

import download


def fake_frame(ticker, closes, multiindex=True):
    """A frame shaped like the one yfinance returns for one ticker."""
    index = pd.DatetimeIndex(pd.bdate_range("2024-01-01", periods=len(closes)), name="Date")
    data = {
        "Adj Close": closes,
        "Close": closes,
        "High": [c + 1 for c in closes],
        "Low": [c - 1 for c in closes],
        "Open": closes,
        "Volume": [100 * (i + 1) for i in range(len(closes))],
    }
    df = pd.DataFrame(data, index=index)
    if multiindex:
        df.columns = pd.MultiIndex.from_tuples([(c, ticker) for c in df.columns],
                                               names=["Price", "Ticker"])
    return df


class FakeDownloader:
    def __init__(self, frames):
        self.frames = frames
        self.calls = []

    def __call__(self, ticker, **kwargs):
        self.calls.append((ticker, kwargs))
        return self.frames[ticker]


def test_multiindex_columns_are_flattened_and_lowercased():
    fake = FakeDownloader({"AAA": fake_frame("AAA", [10.0, 11.0])})
    prices = download.download_prices(["AAA"], downloader=fake)

    assert list(prices.columns) == ["date", "ticker", "open", "high", "low", "close", "volume"]
    assert prices["close"].tolist() == [10.0, 11.0]
    assert prices["high"].tolist() == [11.0, 12.0]


def test_flat_columns_are_accepted_too():
    fake = FakeDownloader({"AAA": fake_frame("AAA", [10.0, 11.0], multiindex=False)})
    prices = download.download_prices(["AAA"], downloader=fake)

    assert list(prices.columns) == ["date", "ticker", "open", "high", "low", "close", "volume"]
    assert prices["volume"].tolist() == [100, 200]


def test_date_moves_from_the_index_into_a_column():
    fake = FakeDownloader({"AAA": fake_frame("AAA", [10.0, 11.0, 12.0])})
    prices = download.download_prices(["AAA"], downloader=fake)

    assert prices["date"].tolist() == list(pd.bdate_range("2024-01-01", periods=3))
    assert list(prices.index) == [0, 1, 2]


def test_tickers_are_tagged_and_concatenated_in_order():
    fake = FakeDownloader({"AAA": fake_frame("AAA", [10.0, 11.0]),
                           "BBB": fake_frame("BBB", [5.0, 6.0, 7.0])})
    prices = download.download_prices(["AAA", "BBB"], downloader=fake)

    assert prices["ticker"].tolist() == ["AAA", "AAA", "BBB", "BBB", "BBB"]
    assert prices["close"].tolist() == [10.0, 11.0, 5.0, 6.0, 7.0]
    assert list(prices.index) == [0, 1, 2, 3, 4]          # ignore_index


def test_values_are_not_cleaned():
    frame = fake_frame("AAA", [10.0, -37.63], multiindex=False)
    frame["Volume"] = [0, 5]
    prices = download.download_prices(["AAA"], downloader=FakeDownloader({"AAA": frame}))

    assert prices["close"].tolist() == [10.0, -37.63]      # negative price kept
    assert prices["volume"].tolist() == [0, 5]             # zero volume kept


def test_downloader_is_called_once_per_ticker_with_unadjusted_prices():
    fake = FakeDownloader({"AAA": fake_frame("AAA", [1.0]), "BBB": fake_frame("BBB", [2.0])})
    download.download_prices(["AAA", "BBB"], start="2020-01-01", end="2020-02-01", downloader=fake)

    assert [t for t, _ in fake.calls] == ["AAA", "BBB"]
    for _, kwargs in fake.calls:
        assert kwargs == {"start": "2020-01-01", "end": "2020-02-01",
                          "auto_adjust": False, "progress": False}


def test_default_configuration_is_the_documented_universe_and_period():
    assert download.TICKERS == ["CL=F", "BZ=F", "NG=F", "GC=F", "HG=F", "ZW=F"]
    assert (download.START, download.END) == ("2016-01-01", "2026-01-01")


def test_save_prices_creates_the_folder_and_round_trips(tmp_path):
    fake = FakeDownloader({"AAA": fake_frame("AAA", [10.0, 11.0])})
    prices = download.download_prices(["AAA"], downloader=fake)
    target = tmp_path / "new_folder" / "raw.parquet"

    download.save_prices(prices, target)

    assert target.exists()
    pd.testing.assert_frame_equal(pd.read_parquet(target), prices)


def test_real_network_is_blocked_in_tests():
    import socket
    with pytest.raises(RuntimeError, match="network access"):
        socket.socket()
