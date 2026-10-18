WITH dups AS (
    SELECT ticker, COUNT(*)::INTEGER AS duplicate_keys
    FROM (
        SELECT ticker, date
        FROM prices
        GROUP BY ticker, date
        HAVING COUNT(*) > 1
    ) AS k
    GROUP BY ticker
),
checks AS (
    SELECT ticker,
           SUM(CASE WHEN open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL
                    THEN 1 ELSE 0 END)::INTEGER AS null_prices,
           SUM(CASE WHEN LEAST(open, high, low, close) <= 0
                    THEN 1 ELSE 0 END)::INTEGER AS non_positive,
           SUM(CASE WHEN high < low THEN 1 ELSE 0 END)::INTEGER AS high_below_low,
           SUM(CASE WHEN open > high OR open < low THEN 1 ELSE 0 END)::INTEGER AS open_outside,
           SUM(CASE WHEN close > high OR close < low THEN 1 ELSE 0 END)::INTEGER AS close_outside
    FROM prices
    GROUP BY ticker
)
SELECT c.*, COALESCE(d.duplicate_keys, 0) AS duplicate_keys
FROM checks c
LEFT JOIN dups d ON d.ticker = c.ticker
ORDER BY c.ticker;
