"""Create/upgrade the lead schema in the configured PostgreSQL database."""

import argparse
from pathlib import Path
import sys

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.settings import get_settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-sample-data", action="store_true")
    args = parser.parse_args()

    dsn = get_settings().AWS_POSTGRES_DSN
    if not dsn:
        raise SystemExit("AWS_POSTGRES_DSN is not configured in .env")

    files = [ROOT / "sql" / "001_create_lead_database.sql"]
    if args.with_sample_data:
        files.append(ROOT / "sql" / "002_sample_data.sql")

    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            for sql_file in files:
                cursor.execute(sql_file.read_text(encoding="utf-8"))
                print(f"Applied {sql_file.name}")
        connection.commit()


if __name__ == "__main__":
    main()
