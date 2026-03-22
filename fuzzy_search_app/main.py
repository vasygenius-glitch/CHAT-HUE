import sys
import os
import csv
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSlider, QTableWidget, QTableWidgetItem,
    QFileDialog, QHeaderView, QComboBox, QProgressBar, QMessageBox, QDialog, QTextEdit, QVBoxLayout, QPushButton
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QSize
from PyQt6.QtGui import QFont, QColor, QIcon, QDesktopServices
from PyQt6.QtCore import QUrl
import os.path

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
    finished = pyqtSignal(list, float)

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

        # Load Stylesheet
        try:
            with open("style.qss", "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        except Exception:
            pass

        # Set App Icon
        icon_path = os.path.join(os.path.dirname(__file__), 'assets', 'app.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

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
        self.btn_search.setObjectName("btnSearch")
        self.btn_search.clicked.connect(self.start_search)
        self.btn_search.setMinimumHeight(44)
        layout.addWidget(self.btn_search)

        # --- Results Table ---
        self.table_results = QTableWidget()
        self.table_results.setColumnCount(4)
        self.table_results.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_results.setAlternatingRowColors(True)
        self.table_results.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_results.cellDoubleClicked.connect(self.show_context_dialog)
        layout.addWidget(self.table_results)

        self.lbl_hint = QLabel()
        self.lbl_hint.setStyleSheet("color: #7f8fa6; font-size: 12px; margin-top: 5px;")
        layout.addWidget(self.lbl_hint)

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
        if hasattr(self, 'lbl_hint'):
            self.lbl_hint.setText("💡 Double-click a row to see full context." if self.current_lang == "English" else "💡 Дважды кликните по строке, чтобы посмотреть весь контекст.")
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

    def on_search_finished(self, results, time_taken):
        self.progress_bar.setVisible(False)
        self.btn_search.setEnabled(True)
        t = LANGUAGES[self.current_lang]
        msg = f"Найдено {len(results)} совпадений за {time_taken:.3f} сек." if self.current_lang == "Русский" else f"Found {len(results)} matches in {time_taken:.3f} sec."
        self.status_label.setText(msg)

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
            item_file.setData(Qt.ItemDataRole.UserRole, result["file"])
            item_file.setData(Qt.ItemDataRole.UserRole + 1, result["line_num"])

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





    def show_context_dialog(self, row, column):
        file_item = self.table_results.item(row, 0)
        file_path = file_item.data(Qt.ItemDataRole.UserRole)
        line_num = file_item.data(Qt.ItemDataRole.UserRole + 1)

        if not file_path or not line_num:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Context Viewer" if self.current_lang == "English" else "Просмотр контекста")
        dialog.resize(600, 400)
        d_layout = QVBoxLayout(dialog)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        d_layout.addWidget(text_edit)

        context_str = []
        if hasattr(self, 'indexed_data') and file_path in self.indexed_data:
            lines = self.indexed_data[file_path]
            start_idx = max(0, line_num - 1 - 3)
            end_idx = min(len(lines), line_num - 1 + 4)

            for i in range(start_idx, end_idx):
                ln, text, _ = lines[i]
                prefix = f"<b>{ln}:</b> "
                if ln == line_num:
                    context_str.append(f"<span style='background-color:#ffeaa7'>{prefix}{text}</span>")
                else:
                    context_str.append(f"{prefix}{text}")

            text_edit.setHtml("<br>".join(context_str))
        else:
            text_edit.setText("Context not available.")

        btn_layout = QHBoxLayout()
        btn_open_internal = QPushButton("Open Full Text" if self.current_lang == "English" else "Открыть весь текст")
        btn_open_internal.clicked.connect(lambda: self.show_full_text(file_path, line_num, dialog))

        btn_open_external = QPushButton("Open File" if self.current_lang == "English" else "Открыть файл")
        btn_open_external.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(file_path)))

        btn_close = QPushButton("Close" if self.current_lang == "English" else "Закрыть")
        btn_close.clicked.connect(dialog.accept)

        btn_layout.addWidget(btn_open_internal)
        btn_layout.addWidget(btn_open_external)
        btn_layout.addWidget(btn_close)

        d_layout.addLayout(btn_layout)

        dialog.exec()



    def show_full_text(self, file_path, highlight_line_num, parent_dialog):
        dialog = QDialog(parent_dialog)
        dialog.setWindowTitle(f"Full Text: {os.path.basename(file_path)}")
        dialog.resize(800, 600)
        d_layout = QVBoxLayout(dialog)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)

        # Build full text HTML with anchor
        html_content = []
        if file_path in self.indexed_data:
            lines = self.indexed_data[file_path]
            for ln, text, _ in lines:
                prefix = f"<b>{ln}:</b> "
                if ln == highlight_line_num:
                    html_content.append(f"<a name='target'></a><span style='background-color:#ffeaa7'>{prefix}{text}</span>")
                else:
                    html_content.append(f"{prefix}{text}")

        text_edit.setHtml("<br>".join(html_content))
        d_layout.addWidget(text_edit)

        # Scroll to anchor
        text_edit.scrollToAnchor("target")

        btn_close = QPushButton("Close" if self.current_lang == "English" else "Закрыть")
        btn_close.clicked.connect(dialog.accept)
        d_layout.addWidget(btn_close)

        dialog.exec()

if __name__ == '__main__':
    app = QApplication(sys.argv)

    # Simple styling
    app.setStyle('Fusion')

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
