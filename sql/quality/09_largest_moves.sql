WITH r AS (
    SELECT date, ticker, close,
           LAG(close) OVER (PARTITION BY ticker ORDER BY date) AS prev_close,
           LAG(date)  OVER (PARTITION BY ticker ORDER BY date) AS prev_date
    FROM prices
)
SELECT ticker, prev_date, date, prev_close, close,
       ROUND(close / prev_close - 1, 4) AS ret
FROM r
WHERE prev_close IS NOT NULL
ORDER BY ABS(close / prev_close - 1) DESC
LIMIT 15;
