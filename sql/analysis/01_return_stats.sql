SELECT ticker,
       COUNT(log_ret)::INTEGER                       AS n_returns,
       ROUND(AVG(log_ret) * 252 * 100, 1)               AS ann_mean_log_ret_pct,
       ROUND(STDDEV_SAMP(log_ret) * SQRT(252) * 100, 1) AS ann_vol_pct,
       ROUND(MIN(ret) * 100, 1)                         AS worst_day_pct,
       ROUND(MAX(ret) * 100, 1)                         AS best_day_pct
FROM prices_clean
WHERE NOT is_suspect
GROUP BY ticker
ORDER BY ann_vol_pct DESC;
