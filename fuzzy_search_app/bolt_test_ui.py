from indexer import index_folder
from searcher import perform_search
import os
import sqlite3
from PyQt6.QtWidgets import QApplication, QDialog
import sys

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from main import MainWindow, RegexHelperDialog

os.makedirs("test_data_dir", exist_ok=True)
with open("test_data_dir/test1.html", "w", encoding="utf-8") as f:
    f.write("<html><body><div class='message'><div class='from_name'>BoltUser</div><div class='text'>My text here</div><div class='date' title='12.12.2023 15:30:00'></div></div></body></html>")

db_file = index_folder("test_data_dir")

win = MainWindow()
win.indexed_data = db_file
win.input_search.setCurrentText("text")

# Test Context HTML generation
html = win.generate_context_html("test_data_dir/test1.html", 1, "text", window_size=3)
if html and "chat-container" in html and "bubble-left" in html:
    print("SUCCESS: Chat Bubbles UI engine successfully rendered!")
else:
    print(f"FAILED: Chat Bubbles not found. Rendered HTML: {html}")

# Test Regex
diag = RegexHelperDialog(win)
print(f"SUCCESS: Regex Dialog instantiated with {diag.list_presets.count()} presets.")

import shutil
shutil.rmtree("test_data_dir")
os.remove(db_file)
