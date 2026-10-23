WITH rv AS (
    SELECT date, ticker,
           STDDEV_SAMP(log_ret) OVER w * SQRT(252) AS vol_21d,
           COUNT(log_ret)       OVER w             AS n_obs
    FROM prices_clean
    WHERE NOT is_suspect
    WINDOW w AS (PARTITION BY ticker ORDER BY date
                 ROWS BETWEEN 20 PRECEDING AND CURRENT ROW)
),
ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY vol_21d DESC) AS rn
    FROM rv
    WHERE n_obs = 21
)
SELECT ticker, date AS peak_date,
       ROUND(vol_21d, 4) AS peak_vol_21d
FROM ranked
WHERE rn = 1
ORDER BY peak_vol_21d DESC;
