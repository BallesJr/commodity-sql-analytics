import duckdb

PARQUET = "data/raw_prices.parquet"
DATABASE = "data/commodities.duckdb"

# Price table: one row per ticker per day, loaded as-is from the parquet file
CREATE_PRICES = f"""
CREATE OR REPLACE TABLE prices AS
SELECT
    CAST(date AS DATE)     AS date,
    CAST(ticker AS VARCHAR) AS ticker,
    CAST(open AS DOUBLE)   AS open,
    CAST(high AS DOUBLE)   AS high,
    CAST(low AS DOUBLE)    AS low,
    CAST(close AS DOUBLE)  AS close,
    CAST(volume AS BIGINT) AS volume
FROM read_parquet('{PARQUET}');
"""

# Reference table describing each instrument
CREATE_INSTRUMENTS = """
CREATE OR REPLACE TABLE instruments (
    ticker VARCHAR,
    name   VARCHAR,
    sector VARCHAR,
    unit   VARCHAR
);
"""

INSERT_INSTRUMENTS = """
INSERT INTO instruments VALUES
    ('CL=F', 'WTI Crude Oil',   'Energy',            'USD/barrel'),
    ('BZ=F', 'Brent Crude Oil', 'Energy',            'USD/barrel'),
    ('NG=F', 'Natural Gas',     'Energy',            'USD/MMBtu'),
    ('GC=F', 'Gold',            'Precious Metals',   'USD/troy oz'),
    ('HG=F', 'Copper',          'Industrial Metals', 'USD/lb'),
    ('ZW=F', 'Wheat',           'Agriculture',       'USc/bushel');
"""

# Check: rows and date range per ticker
SUMMARY = """
SELECT ticker, COUNT(*) AS n_rows, MIN(date) AS first_date, MAX(date) AS last_date
FROM prices GROUP BY ticker ORDER BY ticker;
"""

# Connect (creates the database file if it does not exist)
con = duckdb.connect(DATABASE)

con.execute(CREATE_PRICES)
con.execute(CREATE_INSTRUMENTS)
con.execute(INSERT_INSTRUMENTS)

# Print as a pandas DataFrame (plain text, works in any Windows terminal)
print(con.sql(SUMMARY).df())

con.close()
