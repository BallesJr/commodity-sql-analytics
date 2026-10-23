SELECT a.ticker AS ticker_a,
       b.ticker AS ticker_b,
       COUNT(*)::INTEGER                    AS n_days,
       ROUND(CORR(a.log_ret, b.log_ret), 3) AS corr
FROM prices_clean a
JOIN prices_clean b
  ON a.date = b.date
 AND a.ticker < b.ticker
WHERE NOT a.is_suspect
  AND NOT b.is_suspect
  AND a.log_ret IS NOT NULL
  AND b.log_ret IS NOT NULL
GROUP BY a.ticker, b.ticker
ORDER BY corr DESC;
