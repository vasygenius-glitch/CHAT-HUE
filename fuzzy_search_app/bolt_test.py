from indexer import index_folder
from searcher import perform_search
import os
import sqlite3
from PyQt6.QtWidgets import QApplication, QDialog
import sys

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from main import MainWindow

os.makedirs("test_data_dir", exist_ok=True)
with open("test_data_dir/test1.txt", "w", encoding="utf-8") as f:
    f.write("Line 1 test\nLine 2 test\nAuthor message here")

db_file = index_folder("test_data_dir")

conn = sqlite3.connect(db_file)
cursor = conn.cursor()

# Clear everything so UNIQUE constraint doesn't fail on second run
cursor.execute("DELETE FROM files")
cursor.execute("DELETE FROM lines")

# Manually insert a malformed JSON line to test the json.loads crash fix
cursor.execute("INSERT INTO files (file_path, size_kb, mod_time, last_indexed) VALUES ('test_data_dir/corrupt_new.txt', 1, '2024', 0)")
file_id = cursor.lastrowid
cursor.execute("INSERT INTO lines (file_id, line_num, line_text, words_json, msg_date, author) VALUES (?, 1, 'bad data', 'BAD_JSON_HERE', '', '')", (file_id,))
conn.commit()
conn.close()

class FakeWin(MainWindow):
    def show_full_text(self, file_path, highlight_line_num, parent_dialog):
        # Do not call dialog.exec() so we don't block
        pass

win = MainWindow()
win.indexed_data = db_file
win.input_search.setCurrentText("test")

# Call the method that was crashing
dialog = QDialog()
win.show_full_text('test_data_dir/corrupt_new.txt', 1, dialog)

print("SUCCESS: show_full_text survived corrupt JSON data!")

import shutil
shutil.rmtree("test_data_dir")
os.remove(db_file)
