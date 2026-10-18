SELECT date,
       dayname(date) AS weekday,
       COUNT(*)::INTEGER AS n_tickers,
       STRING_AGG(ticker, ', ' ORDER BY ticker) AS tickers
FROM prices
WHERE volume = 0
  AND year(date) IN (2023, 2025)
GROUP BY date
ORDER BY date;
