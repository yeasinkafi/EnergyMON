import sqlite3
import csv
import os
from datetime import datetime

DB_PATH = "power.db"
OUT_DIR = "export_csv"

def convert_ts(unix_ts):
    """Convert UNIX timestamp to 12-hour format with AM/PM."""
    try:
        return datetime.fromtimestamp(int(unix_ts)).strftime("%Y-%m-%d %I:%M:%S %p")
    except:
        return ""

def export_sqlite_to_csv():
    if not os.path.exists(OUT_DIR):
        os.makedirs(OUT_DIR)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Fetch all table names
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [t[0] for t in cur.fetchall()]

    if not tables:
        print("No tables found in the database.")
        return

    for table in tables:
        print(f"\n[Reading Table] {table}")

        cur.execute(f"SELECT * FROM {table}")
        rows = cur.fetchall()
        col_names = [desc[0] for desc in cur.description]

        # Add readable timestamp column if ts exists
        if "ts" in col_names:
            updated_rows = []
            readable_col_name = "readable_time"
            col_names.append(readable_col_name)
            
            ts_index = col_names.index("ts") if "ts" in col_names else None

            for row in rows:
                row = list(row)
                unix_ts = row[ts_index]
                row.append(convert_ts(unix_ts))
                updated_rows.append(row)

            rows = updated_rows

        csv_path = os.path.join(OUT_DIR, f"{table}.csv")

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(col_names)
            writer.writerows(rows)

        print(f"[OK] Exported: {csv_path}  ({len(rows)} rows)")

    conn.close()
    print("\nExport completed successfully!")

if __name__ == "__main__":
    export_sqlite_to_csv()
