WITH dup_keys AS (
    SELECT ticker, date
    FROM prices
    GROUP BY ticker, date
    HAVING COUNT(*) > 1
),
flagged AS (
    SELECT p.date, p.ticker, p.open, p.high, p.low, p.close, p.volume,
           (p.open IS NULL OR p.high IS NULL OR p.low IS NULL OR p.close IS NULL) AS null_price,
           COALESCE(LEAST(p.open, p.high, p.low, p.close) <= 0, FALSE)       AS non_positive,
           COALESCE(p.high < p.low, FALSE)                                   AS high_below_low,
           COALESCE(p.open > p.high OR p.open < p.low, FALSE)                AS open_outside,
           COALESCE(p.close > p.high OR p.close < p.low, FALSE)              AS close_outside,
           (d.date IS NOT NULL)                                              AS duplicate_key
    FROM prices p
    LEFT JOIN dup_keys d
        ON d.ticker = p.ticker AND d.date = p.date
)
SELECT date, ticker, open, high, low, close, volume,
       CONCAT_WS(', ',
           CASE WHEN null_price     THEN 'null_price' END,
           CASE WHEN non_positive   THEN 'non_positive' END,
           CASE WHEN high_below_low THEN 'high_below_low' END,
           CASE WHEN open_outside   THEN 'open_outside' END,
           CASE WHEN close_outside  THEN 'close_outside' END,
           CASE WHEN duplicate_key  THEN 'duplicate_key' END) AS issues,
       GREATEST(open - high, low - open, 0) AS open_gap
FROM flagged
WHERE null_price OR non_positive OR high_below_low
   OR open_outside OR close_outside OR duplicate_key
ORDER BY date, ticker;
