from pathlib import Path

import duckdb

DATABASE = "data/commodities.duckdb"
VIEWS_DIR = Path("sql/views")

# Open the database in write mode (views are created inside it)
con = duckdb.connect(DATABASE)

# Run every .sql file in sql/views/ in alphabetical order
for sql_file in sorted(VIEWS_DIR.glob("*.sql")):
    print(f"Running {sql_file.as_posix()}")
    con.execute(sql_file.read_text(encoding="utf-8"))

con.close()
