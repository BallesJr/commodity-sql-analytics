WITH n AS (
    SELECT date, ticker,
           close / FIRST_VALUE(close) OVER (PARTITION BY ticker ORDER BY date) * 100 AS norm_price
    FROM prices_clean
    WHERE NOT is_suspect
),
dd AS (
    SELECT ticker, date,
           close / MAX(close) OVER (PARTITION BY ticker ORDER BY date
                                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) - 1 AS drawdown
    FROM prices_clean
    WHERE NOT is_suspect
      AND close > 0
)
SELECT n.ticker,
       MAX(n.date) AS last_date,
       ROUND(arg_max(n.norm_price, n.date), 1) AS final_norm_price,
       ROUND((SELECT arg_max(drawdown, date) FROM dd WHERE dd.ticker = n.ticker) * 100, 1) AS final_drawdown_pct,
       ROUND((SELECT MIN(drawdown) FROM dd WHERE dd.ticker = n.ticker) * 100, 1) AS max_drawdown_pct
FROM n
GROUP BY n.ticker
ORDER BY n.ticker;
