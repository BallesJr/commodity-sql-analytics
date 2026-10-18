CREATE OR REPLACE VIEW prices_clean AS
WITH base AS (
    SELECT date, ticker, open, high, low, close,
           NULLIF(volume, 0) AS volume,
           (volume = 0) AS flag_zero_volume,
           (open = high AND high = low AND low = close) AS flag_flat_bar,
           (high < low OR open > high OR open < low
                       OR close > high OR close < low) AS flag_ohlc_inconsistent,
           (LEAST(open, high, low, close) <= 0) AS flag_non_positive,
           LAG(close) OVER (PARTITION BY ticker ORDER BY date) AS prev_close
    FROM prices
)
SELECT *,
       (flag_zero_volume AND flag_flat_bar) OR flag_ohlc_inconsistent AS is_suspect,
       CASE WHEN prev_close > 0 AND close > 0
            THEN close / prev_close - 1 END AS ret,
       CASE WHEN prev_close > 0 AND close > 0
            THEN LN(close / prev_close) END AS log_ret
FROM base;
