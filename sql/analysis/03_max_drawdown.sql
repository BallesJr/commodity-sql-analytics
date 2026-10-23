WITH dd AS (
    SELECT ticker, date, close,
           MAX(close) OVER (PARTITION BY ticker ORDER BY date
                            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_max
    FROM prices_clean
    WHERE NOT is_suspect
      AND close > 0
),
ranked AS (
    SELECT *,
           close / running_max - 1 AS drawdown,
           ROW_NUMBER() OVER (PARTITION BY ticker
                              ORDER BY close / running_max - 1) AS rn
    FROM dd
)
SELECT ticker,
       date               AS trough_date,
       ROUND(close, 2)       AS trough_close,
       ROUND(running_max, 2) AS prior_peak,
       ROUND(drawdown, 4)    AS max_drawdown
FROM ranked
WHERE rn = 1
ORDER BY max_drawdown;
