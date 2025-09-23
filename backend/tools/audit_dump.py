import os
import psycopg2
import csv
from datetime import datetime

# Database connection details (replace with your actual details or environment variables)
DB_NAME = os.getenv("DB_NAME", "your_db_name")
DB_USER = os.getenv("DB_USER", "your_db_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "your_db_password")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

OUTPUT_DIR = "/tmp/db_reform_audit"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def run_sql_and_dump_to_csv(sql_file_path, output_csv_name):
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        cur = conn.cursor()

        with open(sql_file_path, 'r') as f:
            sql_query = f.read()

        cur.execute(sql_query)
        rows = cur.fetchall()
        colnames = [desc[0] for desc in cur.description]

        output_csv_path = os.path.join(OUTPUT_DIR, output_csv_name)
        with open(output_csv_path, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(colnames)
            csv_writer.writerows(rows)

        print(f"Successfully dumped {sql_file_path} to {output_csv_path}")

    except Exception as e:
        print(f"Error processing {sql_file_path}: {e}")
    finally:
        if conn:
            cur.close()
            conn.close()

if __name__ == "__main__":
    # Run audit_overlaps.sql
    run_sql_and_dump_to_csv(
        "backend/scripts/audit_overlaps.sql",
        f"audit_overlaps_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    )

    # Run audit_codes.sql
    run_sql_and_dump_to_csv(
        "backend/scripts/audit_codes.sql",
        f"audit_codes_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    )
