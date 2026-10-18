SELECT ticker,
       COUNT(*) AS n_rows,
       SUM(CASE WHEN volume = 0 THEN 1 ELSE 0 END)        AS zero_volume,
       SUM(CASE WHEN volume IS NULL THEN 1 ELSE 0 END)    AS null_volume,
       SUM(CASE WHEN open = high AND high = low AND low = close
                THEN 1 ELSE 0 END)                         AS flat_bars
FROM prices
GROUP BY ticker
ORDER BY ticker;
