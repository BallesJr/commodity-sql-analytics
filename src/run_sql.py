import sys

import duckdb

DATABASE = "data/commodities.duckdb"

# Usage: python src/run_sql.py path/to/query.sql
if len(sys.argv) != 2:
    sys.exit("Usage: python src/run_sql.py path/to/query.sql")

# Read the SQL file
with open(sys.argv[1], encoding="utf-8") as f:
    query = f.read()

# Run it (read-only, so the database is never modified) and print as a pandas table
con = duckdb.connect(DATABASE, read_only=True)
print(con.sql(query).df())
con.close()
