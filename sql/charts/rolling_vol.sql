WITH rv AS (
    SELECT date, ticker,
           STDDEV_SAMP(log_ret) OVER w * SQRT(252) AS vol_21d,
           COUNT(log_ret)       OVER w             AS n_obs
    FROM prices_clean
    WHERE NOT is_suspect
    WINDOW w AS (PARTITION BY ticker ORDER BY date
                 ROWS BETWEEN 20 PRECEDING AND CURRENT ROW)
)
SELECT date, ticker, vol_21d
FROM rv
WHERE n_obs = 21
ORDER BY ticker, date;
