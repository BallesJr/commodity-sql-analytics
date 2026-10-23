SELECT date, ticker,
       close / FIRST_VALUE(close) OVER (PARTITION BY ticker ORDER BY date) * 100 AS norm_price
FROM prices_clean
WHERE NOT is_suspect
ORDER BY ticker, date;
