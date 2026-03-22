from fuzzy_search_app.indexer import index_folder
from fuzzy_search_app.searcher import perform_search
import os
import sqlite3
from PyQt6.QtWidgets import QApplication, QDialog
import sys

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from fuzzy_search_app.main import MainWindow

os.makedirs("test_data_dir", exist_ok=True)
with open("test_data_dir/test1.html", "w", encoding="utf-8") as f:
    f.write("<html><body><div class='message'><div class='from_name'>BoltUser</div><div class='text'>My text here</div><div class='date' title='12.12.2023 15:30:00'></div></div></body></html>")

db_file = index_folder("test_data_dir")

win = MainWindow()
win.indexed_data = db_file

# Call context generation to test Chat Bubble Engine logic without blocking the main event loop
html = win.generate_context_html("test_data_dir/test1.html", 1, "text", window_size=3)
if "chat-container" in html and "bubble-left" in html:
    print("SUCCESS: Chat Bubbles UI engine successfully rendered!")
else:
    print("FAILED: Chat Bubbles not found in HTML.")

# Call regex dialog to test it instantiates
from fuzzy_search_app.main import RegexHelperDialog
diag = RegexHelperDialog(win)
print(f"SUCCESS: Regex Dialog instantiated with {diag.list_presets.count()} presets.")

import shutil
shutil.rmtree("test_data_dir")
os.remove(db_file)
