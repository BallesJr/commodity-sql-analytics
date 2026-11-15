from pathlib import Path

import duckdb

DATABASE = "data/commodities.duckdb"
VIEWS_DIR = Path("sql/views")


def build_views(con, views_dir=VIEWS_DIR):
    """Run every .sql file in `views_dir` in alphabetical order."""
    for sql_file in sorted(Path(views_dir).glob("*.sql")):
        print(f"Running {sql_file.as_posix()}")
        con.execute(sql_file.read_text(encoding="utf-8"))


def main(database=DATABASE, views_dir=VIEWS_DIR):
    # Open the database in write mode (views are created inside it)
    con = duckdb.connect(database)
    build_views(con, views_dir)
    con.close()


if __name__ == "__main__":
    main()
