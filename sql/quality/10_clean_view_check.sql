SELECT ticker,
       COUNT(*)::INTEGER AS n_rows,
       SUM(CASE WHEN is_suspect THEN 1 ELSE 0 END)::INTEGER AS n_suspect,
       SUM(CASE WHEN ret IS NULL THEN 1 ELSE 0 END)::INTEGER AS n_null_ret,
       SUM(CASE WHEN volume IS NULL THEN 1 ELSE 0 END)::INTEGER AS n_null_volume
FROM prices_clean
GROUP BY ticker
ORDER BY ticker;
