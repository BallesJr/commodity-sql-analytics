"""Fixtures. Fast tests use hand-made rows in an in-memory DuckDB database:
no network, no price file and nothing written under data/."""
import hashlib
import socket

import duckdb
import pytest

import build_views
import ingest
from helpers import REAL_DATABASE, REAL_PARQUET, SQL


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


@pytest.fixture(scope="session", autouse=True)
def real_data_is_never_modified():
    """Fails the run if any test changed the real database or parquet file."""
    before = {p: _sha256(p) for p in (REAL_DATABASE, REAL_PARQUET)}
    yield
    after = {p: _sha256(p) for p in (REAL_DATABASE, REAL_PARQUET)}
    assert before == after, "a test modified files under data/"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any attempt to open a socket fails the test."""
    def blocked(*args, **kwargs):
        raise RuntimeError("network access is not allowed in tests")
    monkeypatch.setattr(socket, "socket", blocked)


@pytest.fixture(autouse=True)
def run_in_tmp_dir(tmp_path, monkeypatch):
    """Every test runs in an empty temporary directory, so the scripts' relative
    default paths (data/..., reports/...) can never reach the real files."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def con():
    """In-memory database with empty `prices` and `instruments` tables (same
    columns as the real ones) and the real prices_clean view on top."""
    c = duckdb.connect(":memory:")
    c.execute("""CREATE TABLE prices (date DATE, ticker VARCHAR, open DOUBLE, high DOUBLE,
                                      low DOUBLE, close DOUBLE, volume BIGINT)""")
    c.execute(ingest.CREATE_INSTRUMENTS)
    build_views.build_views(c, SQL / "views")
    yield c
    c.close()
