CREATE OR REPLACE VIEW prices_clean AS
WITH base AS (
    SELECT date, ticker, open, high, low, close,
           NULLIF(volume, 0) AS volume,
           COALESCE(volume = 0, FALSE) AS flag_zero_volume,
           COALESCE(open = high AND high = low AND low = close, FALSE) AS flag_flat_bar,
           COALESCE(high < low OR open > high OR open < low
                               OR close > high OR close < low, FALSE) AS flag_ohlc_inconsistent,
           COALESCE(LEAST(open, high, low, close) <= 0, FALSE) AS flag_non_positive,
           (open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL) AS flag_null_price,
           LAG(close) OVER (PARTITION BY ticker ORDER BY date) AS prev_close
    FROM prices
)
SELECT *,
       (flag_zero_volume AND flag_flat_bar)
           OR flag_ohlc_inconsistent
           OR flag_null_price AS is_suspect,
       CASE WHEN prev_close > 0 AND close > 0
            THEN close / prev_close - 1 END AS ret,
       CASE WHEN prev_close > 0 AND close > 0
            THEN LN(close / prev_close) END AS log_ret
FROM base;
