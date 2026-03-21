import sys
import os
import csv
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSlider, QTableWidget, QTableWidgetItem,
    QFileDialog, QHeaderView, QComboBox, QProgressBar, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QColor

import indexer
import searcher

# i18n Dictionary
LANGUAGES = {
    "Русский": {
        "window_title": "Fuzzy Search App - Поиск похожих слов",
        "btn_select_folder": "Выбрать папку",
        "lbl_folder_selected": "Папка: Не выбрана",
        "lbl_search_term": "Что искать:",
        "placeholder_search": "Например: Пукси",
        "lbl_accuracy": "Точность поиска:",
        "lbl_accuracy_exact": "Точно",
        "lbl_accuracy_loose": "Примерно",
        "btn_search": "Искать",
        "btn_export": "Сохранить результаты",
        "col_file": "Файл",
        "col_line": "Строка текста",
        "col_match": "Найдено",
        "col_score": "Совпадение %",
        "msg_no_folder": "Пожалуйста, выберите папку для поиска.",
        "msg_no_term": "Пожалуйста, введите слово для поиска.",
        "msg_indexing": "Индексация файлов... Пожалуйста, подождите.",
        "msg_indexing_done": "Индексация завершена. Найдено {} файлов.",
        "msg_export_success": "Результаты успешно сохранены в:\n{}",
        "msg_export_error": "Ошибка при сохранении файла."
    },
    "English": {
        "window_title": "Fuzzy Search App - Similar Word Search",
        "btn_select_folder": "Select Folder",
        "lbl_folder_selected": "Folder: Not selected",
        "lbl_search_term": "Search for:",
        "placeholder_search": "e.g., Puxi",
        "lbl_accuracy": "Search Accuracy:",
        "lbl_accuracy_exact": "Exact",
        "lbl_accuracy_loose": "Loose",
        "btn_search": "Search",
        "btn_export": "Export Results",
        "col_file": "File",
        "col_line": "Context Line",
        "col_match": "Matched Word",
        "col_score": "Match %",
        "msg_no_folder": "Please select a folder to search in.",
        "msg_no_term": "Please enter a search term.",
        "msg_indexing": "Indexing files... Please wait.",
        "msg_indexing_done": "Indexing complete. Found {} files.",
        "msg_export_success": "Results successfully saved to:\n{}",
        "msg_export_error": "Error saving file."
    }
}

class IndexerWorker(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path

    def run(self):
        indexed_data = indexer.index_folder(self.folder_path)
        self.finished.emit(indexed_data)


class SearchWorker(QThread):
    finished = pyqtSignal(list)

    def __init__(self, indexed_data, search_term, accuracy):
        super().__init__()
        self.indexed_data = indexed_data
        self.search_term = search_term
        self.accuracy = accuracy

    def run(self):
        results = searcher.perform_search(self.indexed_data, self.search_term, self.accuracy)
        self.finished.emit(results)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_lang = "Русский"
        self.indexed_data = {}
        self.selected_folder = ""
        self.init_ui()
        self.update_ui_text()

    def init_ui(self):
        self.resize(1000, 700)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # --- Top Bar (Language) ---
        top_bar = QHBoxLayout()
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["Русский", "English"])
        self.lang_combo.currentTextChanged.connect(self.change_language)
        top_bar.addStretch()
        top_bar.addWidget(self.lang_combo)
        layout.addLayout(top_bar)

        # --- File Selection ---
        file_bar = QHBoxLayout()
        self.btn_select_folder = QPushButton()
        self.btn_select_folder.clicked.connect(self.select_folder)
        self.lbl_folder_selected = QLabel()
        self.lbl_folder_selected.setStyleSheet("color: gray;")
        file_bar.addWidget(self.btn_select_folder)
        file_bar.addWidget(self.lbl_folder_selected)
        file_bar.addStretch()
        layout.addLayout(file_bar)

        # --- Status/Progress Bar ---
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: blue;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0) # Indeterminate initially
        self.progress_bar.setVisible(False)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)

        # --- Search Area ---
        search_layout = QHBoxLayout()

        self.lbl_search_term = QLabel()
        self.input_search = QLineEdit()

        search_layout.addWidget(self.lbl_search_term)
        search_layout.addWidget(self.input_search)

        layout.addLayout(search_layout)

        # --- Accuracy Slider ---
        slider_layout = QHBoxLayout()
        self.lbl_accuracy = QLabel()
        self.lbl_loose = QLabel()
        self.slider_accuracy = QSlider(Qt.Orientation.Horizontal)
        self.slider_accuracy.setRange(50, 100) # Minimum 50% match
        self.slider_accuracy.setValue(80) # Default to 80% (reasonable fuzziness)
        self.slider_accuracy.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider_accuracy.setTickInterval(10)
        self.lbl_exact = QLabel()

        # Value label
        self.lbl_slider_val = QLabel("80%")
        self.slider_accuracy.valueChanged.connect(lambda v: self.lbl_slider_val.setText(f"{v}%"))

        slider_layout.addWidget(self.lbl_accuracy)
        slider_layout.addWidget(self.lbl_loose)
        slider_layout.addWidget(self.slider_accuracy)
        slider_layout.addWidget(self.lbl_exact)
        slider_layout.addWidget(self.lbl_slider_val)

        layout.addLayout(slider_layout)

        # --- Search Button ---
        self.btn_search = QPushButton()
        self.btn_search.clicked.connect(self.start_search)
        self.btn_search.setMinimumHeight(40)
        self.btn_search.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.btn_search)

        # --- Results Table ---
        self.table_results = QTableWidget()
        self.table_results.setColumnCount(4)
        self.table_results.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table_results)

        # --- Export Button ---
        self.btn_export = QPushButton()
        self.btn_export.clicked.connect(self.export_results)
        layout.addWidget(self.btn_export)

    def change_language(self, text):
        self.current_lang = text
        self.update_ui_text()

    def update_ui_text(self):
        t = LANGUAGES[self.current_lang]
        self.setWindowTitle(t["window_title"])
        self.btn_select_folder.setText(t["btn_select_folder"])
        if not self.selected_folder:
            self.lbl_folder_selected.setText(t["lbl_folder_selected"])
        else:
            self.lbl_folder_selected.setText(f"Folder: {self.selected_folder}" if self.current_lang == "English" else f"Папка: {self.selected_folder}")

        self.lbl_search_term.setText(t["lbl_search_term"])
        self.input_search.setPlaceholderText(t["placeholder_search"])
        self.lbl_accuracy.setText(t["lbl_accuracy"])
        self.lbl_exact.setText(t["lbl_accuracy_exact"])
        self.lbl_loose.setText(t["lbl_accuracy_loose"])
        self.btn_search.setText(t["btn_search"])
        self.btn_export.setText(t["btn_export"])

        self.table_results.setHorizontalHeaderLabels([t["col_file"], t["col_line"], t["col_match"], t["col_score"]])

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Directory")
        if folder:
            self.selected_folder = folder
            self.update_ui_text()
            self.start_indexing()

    def start_indexing(self):
        t = LANGUAGES[self.current_lang]
        self.status_label.setText(t["msg_indexing"])
        self.progress_bar.setVisible(True)
        self.btn_search.setEnabled(False)
        self.btn_select_folder.setEnabled(False)

        self.indexer_thread = IndexerWorker(self.selected_folder)
        self.indexer_thread.finished.connect(self.on_indexing_finished)
        self.indexer_thread.start()

    def on_indexing_finished(self, indexed_data):
        self.indexed_data = indexed_data
        t = LANGUAGES[self.current_lang]
        self.status_label.setText(t["msg_indexing_done"].format(len(self.indexed_data)))
        self.progress_bar.setVisible(False)
        self.btn_search.setEnabled(True)
        self.btn_select_folder.setEnabled(True)

    def start_search(self):
        t = LANGUAGES[self.current_lang]
        term = self.input_search.text().strip()
        if not self.indexed_data:
            QMessageBox.warning(self, "Warning", t["msg_no_folder"])
            return
        if not term:
            QMessageBox.warning(self, "Warning", t["msg_no_term"])
            return

        accuracy = self.slider_accuracy.value()
        self.btn_search.setEnabled(False)
        self.status_label.setText("Searching...")
        self.progress_bar.setVisible(True)
        self.table_results.setRowCount(0) # Clear previous

        self.search_thread = SearchWorker(self.indexed_data, term, accuracy)
        self.search_thread.finished.connect(self.on_search_finished)
        self.search_thread.start()

    def on_search_finished(self, results):
        self.progress_bar.setVisible(False)
        self.btn_search.setEnabled(True)
        self.status_label.setText(f"Found {len(results)} matches.")

        self.table_results.setRowCount(len(results))
        for row, result in enumerate(results):
            # Format file name relative to selected folder for better readability
            rel_path = os.path.relpath(result["file"], self.selected_folder)

            item_file = QTableWidgetItem(f"{rel_path} (L: {result['line_num']})")
            item_line = QTableWidgetItem(result["line"])
            item_match = QTableWidgetItem(result["match"])
            item_score = QTableWidgetItem(f"{result['score']}%")

            # Make items read-only
            for item in [item_file, item_line, item_match, item_score]:
                item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)

            # Highlight match slightly
            item_match.setBackground(QColor("#e6ffe6"))
            item_match.setFont(QFont("Arial", weight=QFont.Weight.Bold))

            self.table_results.setItem(row, 0, item_file)
            self.table_results.setItem(row, 1, item_line)
            self.table_results.setItem(row, 2, item_match)
            self.table_results.setItem(row, 3, item_score)

    def export_results(self):
        t = LANGUAGES[self.current_lang]
        if self.table_results.rowCount() == 0:
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Save Results", "", "CSV Files (*.csv);;Text Files (*.txt)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8', newline='') as f:
                    if file_path.endswith('.csv'):
                        writer = csv.writer(f)
                        # Header
                        writer.writerow([self.table_results.horizontalHeaderItem(i).text() for i in range(4)])
                        # Data
                        for row in range(self.table_results.rowCount()):
                            writer.writerow([
                                self.table_results.item(row, i).text() for i in range(4)
                            ])
                    else:
                        for row in range(self.table_results.rowCount()):
                            file_txt = self.table_results.item(row, 0).text()
                            line_txt = self.table_results.item(row, 1).text()
                            match_txt = self.table_results.item(row, 2).text()
                            score_txt = self.table_results.item(row, 3).text()
                            f.write(f"File: {file_txt}\nMatch: {match_txt} ({score_txt})\nContext: {line_txt}\n{'-'*40}\n")

                QMessageBox.information(self, "Success", t["msg_export_success"].format(file_path))
            except Exception as e:
                QMessageBox.critical(self, "Error", f"{t['msg_export_error']}\n{str(e)}")


if __name__ == '__main__':
    app = QApplication(sys.argv)

    # Simple styling
    app.setStyle('Fusion')

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
