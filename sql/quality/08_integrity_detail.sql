SELECT date, ticker, open, high, low, close, volume,
       CASE
           WHEN LEAST(open, high, low, close) <= 0 THEN 'non_positive'
           WHEN open > high OR open < low          THEN 'open_outside'
       END AS issue,
       GREATEST(open - high, low - open, 0) AS open_gap
FROM prices
WHERE LEAST(open, high, low, close) <= 0
   OR open > high
   OR open < low
ORDER BY date;
