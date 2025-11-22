import subprocess
import sys

try:
    import pandas as pd
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pandas"])
    import pandas as pd  
import sqlite3

DB_PATH = "power.db"

conn = sqlite3.connect(DB_PATH)
df = pd.read_sql_query("SELECT * FROM readings ORDER BY ts", conn)
conn.close()

print(df)
