WITH calendar AS (
    SELECT CAST(d AS DATE) AS date
    FROM generate_series(DATE '2016-01-01', DATE '2025-12-31', INTERVAL 1 DAY) AS t(d)
    WHERE dayofweek(d) BETWEEN 1 AND 5
),
expected AS (
    SELECT c.date, i.ticker
    FROM calendar c
    CROSS JOIN instruments i
),
missing AS (
    SELECT e.date, e.ticker
    FROM expected e
    LEFT JOIN prices p
        ON p.date = e.date AND p.ticker = e.ticker
    WHERE p.date IS NULL
)
SELECT date,
       dayname(date) AS weekday,
       COUNT(*) AS n_tickers_missing,
       STRING_AGG(ticker, ', ' ORDER BY ticker) AS tickers_missing
FROM missing
GROUP BY date
HAVING COUNT(*) < 6
ORDER BY date;
