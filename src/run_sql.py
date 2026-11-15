import sys

import duckdb
import pandas as pd

DATABASE = "data/commodities.duckdb"


def run_sql_file(con, path):
    """Run the query in a .sql file and return the result as a pandas DataFrame."""
    with open(path, encoding="utf-8") as f:
        query = f.read()
    return con.sql(query).df()


def main(argv=None, database=DATABASE):
    if argv is None:
        argv = sys.argv

    # Always show every row and column, never truncate with "..."
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", None)

    # Usage: python src/run_sql.py path/to/query.sql
    if len(argv) != 2:
        sys.exit("Usage: python src/run_sql.py path/to/query.sql")

    # Run it (read-only, so the database is never modified) and print as a pandas table
    con = duckdb.connect(database, read_only=True)
    print(run_sql_file(con, argv[1]))
    con.close()


if __name__ == "__main__":
    main()
