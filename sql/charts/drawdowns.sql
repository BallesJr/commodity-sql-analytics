WITH dd AS (
    SELECT ticker, date, close,
           MAX(close) OVER (PARTITION BY ticker ORDER BY date
                            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_max
    FROM prices_clean
    WHERE NOT is_suspect
      AND close > 0
)
SELECT date, ticker, close / running_max - 1 AS drawdown
FROM dd
ORDER BY ticker, date;
