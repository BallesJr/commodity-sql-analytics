SELECT ticker,
       year(date) AS yr,
       SUM(CASE WHEN volume = 0 THEN 1 ELSE 0 END)::INTEGER AS zero_volume,
       SUM(CASE WHEN open = high AND high = low AND low = close
                THEN 1 ELSE 0 END)::INTEGER AS flat_bars,
       SUM(CASE WHEN volume = 0
                 AND open = high AND high = low AND low = close
                THEN 1 ELSE 0 END)::INTEGER AS both
FROM prices
GROUP BY ticker, year(date)
HAVING SUM(CASE WHEN volume = 0 THEN 1 ELSE 0 END) > 0
    OR SUM(CASE WHEN open = high AND high = low AND low = close
                THEN 1 ELSE 0 END) > 0
ORDER BY ticker, yr;
