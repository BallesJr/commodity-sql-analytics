SELECT date, ticker, open, high, low, close, volume
FROM prices_clean
WHERE is_suspect
ORDER BY ticker, date;
