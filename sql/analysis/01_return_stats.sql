SELECT ticker,
       COUNT(log_ret)::INTEGER                       AS n_returns,
       ROUND(AVG(log_ret) * 252, 4)                  AS ann_mean_log_ret,
       ROUND(STDDEV_SAMP(log_ret) * SQRT(252), 4)    AS ann_vol,
       ROUND(MIN(ret), 4)                            AS worst_day,
       ROUND(MAX(ret), 4)                            AS best_day
FROM prices_clean
WHERE NOT is_suspect
GROUP BY ticker
ORDER BY ann_vol DESC;
