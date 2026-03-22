from fuzzy_search_app.indexer import index_folder
import os

os.makedirs("test_data_dir", exist_ok=True)
with open("test_data_dir/test.txt", "w", encoding="utf-8") as f:
    f.write("Hello world!\nThis is a rapid FTS5 test for SQLite.\nAuthor: Bolt")

db_file = index_folder("test_data_dir")
print("Generated DB File:", db_file)

import sqlite3
conn = sqlite3.connect(db_file)
cursor = conn.cursor()
cursor.execute("SELECT rowid, line_text FROM fts_lines WHERE line_text MATCH 'rapid'")
print("FTS5 Match:", cursor.fetchall())

import shutil
shutil.rmtree("test_data_dir")
os.remove(db_file)
