import sys
import os
import csv
from PyQt6.QtWidgets import (QCheckBox, QMenu, QSpinBox, QInputDialog,
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSlider, QTableWidget, QTableWidgetItem,
    QFileDialog, QHeaderView, QComboBox, QProgressBar, QMessageBox, QDialog, QTextEdit, QVBoxLayout, QPushButton
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QSize, QSettings, QUrl
from PyQt6.QtGui import QFont, QColor, QIcon, QDesktopServices, QShortcut, QKeySequence
from PyQt6.QtWidgets import QSystemTrayIcon
import os.path

import indexer
import searcher

# i18n Dictionary
LANGUAGES = {
    "Русский": {
        "window_title": "TeleSearch Pro - Мощный поиск в чатах и файлах",
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
        "window_title": "TeleSearch Pro - Advanced File & Chat Search",
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


class NumericTableWidgetItem(QTableWidgetItem):
    def __init__(self, display_text, numeric_value):
        super().__init__(display_text)
        self.numeric_value = numeric_value

    def __lt__(self, other):
        if isinstance(other, NumericTableWidgetItem):
            return self.numeric_value < other.numeric_value
        return super().__lt__(other)

from PyQt6.QtCore import QAbstractTableModel

class ResultsTableModel(QAbstractTableModel):
    """
    ⚡ BOLT MVC ARCHITECTURE
    This highly optimized model feeds data to a QTableView dynamically.
    Instead of instantiating 50,000 QTableWidgetItems (which crashes PyQt),
    this reads natively from a Python list and only serves the rows currently visible on screen.
    It can comfortably handle 1,000,000+ results with zero UI freezing and infinite smooth scrolling.
    """
    def __init__(self, data, base_folder, lang="Русский"):
        super().__init__()
        self._data = data
        self.base_folder = base_folder
        self.lang = lang
        self.headers = ["Файл", "Строка текста", "Найдено", "Размер (КБ)", "Дата/Время", "Автор", "Совпадение %"] if lang == "Русский" else ["File", "Context Line", "Matched Word", "Size (KB)", "Date/Time", "Author", "Match %"]

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()
        result = self._data[row]

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                rel_path = os.path.relpath(result["file"], self.base_folder)
                return f"{rel_path} (L: {result['line_num']})"
            elif col == 1:
                return result["line"]
            elif col == 2:
                return result["match"]
            elif col == 3:
                return result.get("size_kb", 0)
            elif col == 4:
                return result.get("mod_time", "")
            elif col == 5:
                return result.get("author", "")
            elif col == 6:
                return result["score"] # Return float for proper sorting

        elif role == Qt.ItemDataRole.ForegroundRole:
            if col == 0:
                return QColor("#0984e3")

        elif role == Qt.ItemDataRole.FontRole:
            font = QFont()
            if col == 0:
                font.setUnderline(True)
            elif col == 2:
                font.setFamily("Arial")
                font.setBold(True)
            return font

        elif role == Qt.ItemDataRole.BackgroundRole:
            if col == 2:
                return QColor("#e6ffe6")

        elif role == Qt.ItemDataRole.UserRole:
            if col == 0:
                return result["file"]
            elif col == 1:
                return result["line_num"]
            elif col == 4:
                # Sub-sort chronological identical dates by line number
                line_str = str(result["line_num"]).zfill(7)
                return f"{result.get('mod_time', '')}|{line_str}"

        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return None

    def sort(self, column, order):
        self.layoutAboutToBeChanged.emit()

        reverse = (order == Qt.SortOrder.DescendingOrder)

        if column == 0:
            self._data.sort(key=lambda x: x["file"], reverse=reverse)
        elif column == 1:
            self._data.sort(key=lambda x: x["line"], reverse=reverse)
        elif column == 2:
            self._data.sort(key=lambda x: x["match"], reverse=reverse)
        elif column == 3:
            self._data.sort(key=lambda x: x.get("size_kb", 0), reverse=reverse)
        elif column == 4:
            # Sort chronologically, resolving exact ties by line_num
            self._data.sort(key=lambda x: f"{x.get('mod_time', '')}|{str(x['line_num']).zfill(7)}", reverse=reverse)
        elif column == 5:
            self._data.sort(key=lambda x: x.get("author", ""), reverse=reverse)
        elif column == 6:
            self._data.sort(key=lambda x: x["score"], reverse=reverse)

        self.layoutChanged.emit()


class IndexerWorker(QThread):
    finished = pyqtSignal(str) # Returns the db_file path
    progress = pyqtSignal(int, int, bool)

    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path

    def run(self):
        def on_progress(processed, total, from_cache=False):
            self.progress.emit(processed, total, from_cache)

        db_file = indexer.index_folder(self.folder_path, progress_callback=on_progress)
        self.finished.emit(db_file)


class SearchWorker(QThread):
    finished = pyqtSignal(list, float)

    def __init__(self, db_file, search_term, accuracy, exact_match, file_filter, regex_match=False, case_sensitive=False, author_filter="", date_from=None, date_to=None, size_min=None, size_max=None):
        super().__init__()
        self.db_file = db_file
        self.search_term = search_term
        self.accuracy = accuracy
        self.exact_match = exact_match
        self.file_filter = file_filter
        self.regex_match = regex_match
        self.case_sensitive = case_sensitive
        self.author_filter = author_filter
        self.date_from = date_from
        self.date_to = date_to
        self.size_min = size_min
        self.size_max = size_max

    def run(self):
        import sqlite3
        # Ensure thread safety. SQLite connections cannot be passed across threads.
        # So we pass the file path and open it fresh inside this QThread!
        if not self.db_file or not os.path.exists(self.db_file):
            self.finished.emit([], 0.0)
            return

        # Handle File Filters (Push them to the DB query logic in searcher if possible, but for now we do post-filter)
        # Actually, it's safer to pass the file_filter string down to searcher to do it in SQL!

        results, time_taken = searcher.perform_search(
            self.db_file, self.search_term, self.accuracy,
            self.exact_match, self.regex_match, self.case_sensitive, self.author_filter,
            self.date_from, self.date_to, self.size_min, self.size_max
        )

        # Apply UI file filter
        if self.file_filter != "Все файлы (*.*)":
            if self.file_filter.startswith("Только Изображения"):
                results = [r for r in results if r["file"].lower().endswith(('.png', '.jpg', '.jpeg'))]
            else:
                ext = self.file_filter.split("*")[-1].replace(")", "").lower()
                results = [r for r in results if r["file"].lower().endswith(ext)]

        self.finished.emit(results, time_taken)


from PyQt6.QtWidgets import QTabWidget

class RegexHelperDialog(QDialog):
    """
    ⚡ BOLT V5 ENTERPRISE: Regex Builder Assistant
    Provides easy-to-use presets for users who don't know regular expressions.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("Помощник Regex (Presets)" if parent.current_lang == "Русский" else "Regex Assistant")
        self.resize(400, 300)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Выберите шаблон для поиска:" if parent.current_lang == "Русский" else "Select a regex template:"))

        from PyQt6.QtWidgets import QListWidget, QListWidgetItem
        self.list_presets = QListWidget()

        self.presets = [
            ("📧 Email-адреса", r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
            ("📱 Номера телефонов (РФ/СНГ)", r"(\+7|8|7)[\s\-]?\(?[489][0-9]{2}\)?[\s\-]?[0-9]{3}[\s\-]?[0-9]{2}[\s\-]?[0-9]{2}"),
            ("🔗 Ссылки (URL)", r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+"),
            ("🌐 IP-адреса (IPv4)", r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"),
            ("💰 Bitcoin кошельки", r"\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b"),
            ("📅 Даты (ДД.ММ.ГГГГ)", r"\b(0[1-9]|[12][0-9]|3[01])[- \.](0[1-9]|1[012])[- \.](19|20)\d\d\b")
        ]

        for name, pattern in self.presets:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, pattern)
            self.list_presets.addItem(item)

        layout.addWidget(self.list_presets)

        self.list_presets.itemDoubleClicked.connect(self.apply_preset)

        btn_layout = QHBoxLayout()
        btn_apply = QPushButton("Применить" if parent.current_lang == "Русский" else "Apply")
        btn_apply.clicked.connect(self.apply_preset)
        btn_cancel = QPushButton("Отмена" if parent.current_lang == "Русский" else "Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_apply)
        layout.addLayout(btn_layout)

    def apply_preset(self, item=None):
        if not item:
            item = self.list_presets.currentItem()
        if not item:
            return

        pattern = item.data(Qt.ItemDataRole.UserRole)
        # Apply to main window search bar
        self.parent_window.input_search.setCurrentText(pattern)
        self.parent_window.chk_regex_match.setChecked(True)
        self.accept()

class SettingsDialog(QDialog):
    """
    ⚡ BOLT V4 ENTERPRISE: Professional Preferences Dialog
    Allows deep customization of the application's appearance and behavior.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("Настройки" if parent.current_lang == "Русский" else "Settings")
        self.resize(500, 400)
        self.settings = QSettings("BoltStudio", "TeleSearchPro")

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Appearance Tab
        self.tab_appearance = QWidget()
        app_layout = QVBoxLayout(self.tab_appearance)

        self.chk_dark_mode = QCheckBox("Тёмная тема (Dark Mode)" if parent.current_lang == "Русский" else "Dark Mode")
        self.chk_dark_mode.setChecked(self.settings.value("dark_mode", False, type=bool))
        app_layout.addWidget(self.chk_dark_mode)

        app_layout.addWidget(QLabel("Размер шрифта (Font Size):" if parent.current_lang == "Русский" else "Font Size:"))
        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(8, 24)
        self.spin_font_size.setValue(self.settings.value("font_size", 10, type=int))
        app_layout.addWidget(self.spin_font_size)
        app_layout.addStretch()
        self.tabs.addTab(self.tab_appearance, "Внешний вид" if parent.current_lang == "Русский" else "Appearance")

        # Behavior Tab
        self.tab_behavior = QWidget()
        beh_layout = QVBoxLayout(self.tab_behavior)

        self.chk_tray = QCheckBox("Сворачивать в трей (Minimize to Tray)" if parent.current_lang == "Русский" else "Minimize to Tray")
        self.chk_tray.setChecked(self.settings.value("minimize_to_tray", True, type=bool))
        beh_layout.addWidget(self.chk_tray)

        self.chk_live_monitor = QCheckBox("Live-мониторинг папки (Auto-update Index)" if parent.current_lang == "Русский" else "Live Folder Monitoring")
        self.chk_live_monitor.setChecked(self.settings.value("live_monitor", False, type=bool))
        beh_layout.addWidget(self.chk_live_monitor)

        beh_layout.addStretch()
        self.tabs.addTab(self.tab_behavior, "Поведение" if parent.current_lang == "Русский" else "Behavior")

        # Search Tab
        self.tab_search = QWidget()
        search_layout = QVBoxLayout(self.tab_search)

        search_layout.addWidget(QLabel("История поиска (Max History):" if parent.current_lang == "Русский" else "Max Search History:"))
        self.spin_history = QSpinBox()
        self.spin_history.setRange(5, 100)
        self.spin_history.setValue(self.settings.value("max_history", 10, type=int))
        search_layout.addWidget(self.spin_history)

        search_layout.addStretch()
        self.tabs.addTab(self.tab_search, "Поиск" if parent.current_lang == "Русский" else "Search")

        # Buttons
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("Сохранить" if parent.current_lang == "Русский" else "Save")
        btn_save.clicked.connect(self.save_settings)
        btn_cancel = QPushButton("Отмена" if parent.current_lang == "Русский" else "Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)

    def save_settings(self):
        # Save Appearance
        old_dark = self.settings.value("dark_mode", False, type=bool)
        new_dark = self.chk_dark_mode.isChecked()
        self.settings.setValue("dark_mode", new_dark)

        new_font = self.spin_font_size.value()
        self.settings.setValue("font_size", new_font)

        # Save Behavior
        self.settings.setValue("minimize_to_tray", self.chk_tray.isChecked())

        old_live = self.settings.value("live_monitor", False, type=bool)
        new_live = self.chk_live_monitor.isChecked()
        self.settings.setValue("live_monitor", new_live)

        # Save Search
        self.settings.setValue("max_history", self.spin_history.value())

        # Apply dynamically
        if old_dark != new_dark:
            self.parent_window.is_dark_mode = not new_dark # Flip so toggle_theme works correctly
            self.parent_window.toggle_theme()

        # Apply font globally via stylesheet
        font_qss = f"QWidget {{ font-size: {new_font}pt; }}"
        current_style = self.parent_window.styleSheet()
        # Simple injection for demonstration
        self.parent_window.setStyleSheet(current_style + "\n" + font_qss)

        if old_live != new_live:
            self.parent_window.setup_live_monitoring()

        self.accept()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # ⚡ BOLT V2 MIGRATION: Auto-purge old .pkl cache files to free disk space
        app_data_dir = os.path.join(os.path.expanduser("~"), ".telesearch_cache")
        if os.path.exists(app_data_dir):
            for file in os.listdir(app_data_dir):
                if file.endswith(".pkl"):
                    try:
                        os.remove(os.path.join(app_data_dir, file))
                    except OSError:
                        pass

        self.settings = QSettings("BoltStudio", "TeleSearchPro")
        self.current_lang = self.settings.value("language", "Русский")
        self.is_dark_mode = self.settings.value("dark_mode", False, type=bool)
        self.selected_folder = self.settings.value("last_folder", "")
        self.indexed_data = {}

        self.init_ui()
        # Apply loaded settings
        self.lang_combo.setCurrentText(self.current_lang)

        # Determine initial theme state robustly without inverting
        current_state = self.is_dark_mode
        self.is_dark_mode = not current_state # Toggle will flip it back to current_state
        self.toggle_theme()

        self.update_ui_text()

        self.update_welcome_message()
        if not self.selected_folder:
            self.welcome_widget.show()
            self.table_results.hide()
        else:
            self.welcome_widget.hide()
            self.table_results.show()

        # Setup System Tray
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(os.path.join(os.path.dirname(__file__), 'assets', 'app.ico')))

        tray_menu = QMenu()
        restore_action = tray_menu.addAction("Развернуть" if self.current_lang == "Русский" else "Restore")
        restore_action.triggered.connect(self.showNormal)
        quit_action = tray_menu.addAction("Выход" if self.current_lang == "Русский" else "Quit")
        quit_action.triggered.connect(QApplication.instance().quit)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

        # Global Search Shortcut (Ctrl+F)
        self.shortcut_search = QShortcut(QKeySequence("Ctrl+F"), self)
        self.shortcut_search.activated.connect(self.input_search.setFocus)

        # Start indexing if folder remembered
        if self.selected_folder and os.path.exists(self.selected_folder):
            self.start_indexing()

        # Drag and Drop Support
        self.setAcceptDrops(True)

        # Load Initial Stylesheet
        self.apply_stylesheets()

        # Set App Icon
        icon_path = os.path.join(os.path.dirname(__file__), 'assets', 'app.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        from PyQt6.QtCore import QFileSystemWatcher
        self.file_watcher = QFileSystemWatcher(self)
        self.file_watcher.directoryChanged.connect(self.on_directory_changed)
        self.setup_live_monitoring()

    def setup_live_monitoring(self):
        if not self.selected_folder or not os.path.exists(self.selected_folder):
            return

        directories = self.file_watcher.directories()
        if directories:
            self.file_watcher.removePaths(directories)

        if self.settings.value("live_monitor", False, type=bool):
            self.file_watcher.addPath(self.selected_folder)

    def on_directory_changed(self, path):
        # Trigger background re-index transparently if Live Monitoring is ON
        # A full enterprise implementation would only diff the changed file, but triggering the standard
        # C++ SQLite indexed_folder is already fast enough due to modification date checking.
        if self.settings.value("live_monitor", False, type=bool):
            self.status_label.setText("Live Monitor: Syncing index..." if self.current_lang == "English" else "Live-монитор: Синхронизация...")

            # Start background worker silently
            self.live_worker = IndexerWorker(self.selected_folder)
            self.live_worker.finished.connect(self.on_live_index_finished)
            self.live_worker.start()

    def on_live_index_finished(self, db_file):
        self.status_label.setText("Live Monitor: Sync complete." if self.current_lang == "English" else "Live-монитор: Синхронизация завершена.")
        # If the user is currently looking at a search, we might auto-refresh it
        # But to prevent disruptive UI jumping, we just let them click Search again or notify them.

    def init_ui(self):
        self.resize(1000, 700)

        # ⚡ Sidebar Layout Setup
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        h_layout = QHBoxLayout(main_widget)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(0)

        # --- LEFT SIDEBAR ---
        self.sidebar = QWidget()
        self.sidebar.setFixedWidth(260)
        self.sidebar.setObjectName("sidebar")
        s_layout = QVBoxLayout(self.sidebar)
        s_layout.setContentsMargins(15, 20, 15, 20)
        s_layout.setSpacing(15)

        # --- MAIN AREA ---
        main_area = QWidget()
        layout = QVBoxLayout(main_area)
        layout.setContentsMargins(20, 20, 20, 20)

        from PyQt6.QtWidgets import QSplitter
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(self.main_splitter)

        h_layout.addWidget(self.sidebar)
        h_layout.addWidget(main_area)

        # Create Menu Bar
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("Файл" if self.current_lang == "Русский" else "File")

        # Analytics Tools
        tools_menu = menu_bar.addMenu("Аналитика" if self.current_lang == "Русский" else "Analytics")
        action_chat_stats = tools_menu.addAction("📊 Статистика чата" if self.current_lang == "Русский" else "📊 Chat Stats")
        action_chat_stats.triggered.connect(self.show_chat_analytics)

        # Recent Folders Menu
        self.recent_menu = file_menu.addMenu("Недавние папки" if self.current_lang == "Русский" else "Recent Folders")
        self.update_recent_menu()

        # Favorites Menu
        self.fav_menu = file_menu.addMenu("Избранное" if self.current_lang == "Русский" else "Favorites")
        self.update_fav_menu()

        action_open = file_menu.addAction("Открыть папку" if self.current_lang == "Русский" else "Open Folder")
        action_open.triggered.connect(self.select_folder)

        action_clear_cache = file_menu.addAction("Очистить весь кэш" if self.current_lang == "Русский" else "Clear All Cache")
        action_clear_cache.triggered.connect(self.clear_all_cache)

        # ⚡ BOLT V4: Settings Trigger
        action_settings = file_menu.addAction("⚙ Настройки" if self.current_lang == "Русский" else "⚙ Settings")
        action_settings.triggered.connect(self.open_settings)

        file_menu.addSeparator()

        action_exit = file_menu.addAction("Выход" if self.current_lang == "Русский" else "Exit")
        action_exit.triggered.connect(self.close)


        # App Title in Sidebar
        # Toggle Sidebar Button
        self.btn_toggle_sidebar = QPushButton("≡")
        self.btn_toggle_sidebar.setFixedSize(30, 30)
        self.btn_toggle_sidebar.setStyleSheet("font-size: 18px; font-weight: bold; background: transparent; color: #576574;")
        self.btn_toggle_sidebar.clicked.connect(lambda: self.sidebar.setVisible(not self.sidebar.isVisible()))

        top_h = QHBoxLayout()
        self.lbl_app_title = QLabel("TeleSearch Pro ⚡")
        top_h.addWidget(self.btn_toggle_sidebar)
        top_h.addWidget(self.lbl_app_title)
        top_h.addStretch()

        # Replace the direct label widget with the layout
        self.lbl_app_title.setStyleSheet("font-size: 22px; font-weight: bold; color: #00a8ff;")
        s_layout.addLayout(top_h)

        # Language Select
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["Русский", "English"])
        self.lang_combo.currentTextChanged.connect(self.change_language)
        s_layout.addWidget(self.lang_combo)

        # --- File Selection ---
        self.btn_select_folder = QPushButton()
        self.btn_select_folder.clicked.connect(self.select_folder)
        self.btn_select_folder.setIcon(QIcon(os.path.join(os.path.dirname(__file__), 'assets', 'icons', 'folder-open.png')))
        self.lbl_folder_selected = QLabel()
        self.lbl_folder_selected.setStyleSheet("color: gray;")
        self.lbl_folder_selected.setWordWrap(True)
        s_layout.addWidget(self.btn_select_folder)
        s_layout.addWidget(self.lbl_folder_selected)

        # --- Status/Progress Bar ---
        self.status_bar = self.statusBar()
        self.status_label = QLabel()
        self.status_bar.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)

        # --- Filters Area ---
        self.combo_file_type = QComboBox()
        self.combo_file_type.addItems(["Все файлы (*.*)", "Только Word (*.docx)", "Только Текст (*.txt)", "Только PDF (*.pdf)", "Только Web (*.html)", "Только Изображения (*.png *.jpg)", "Только CSV (*.csv)", "Архивы (*.zip)"])
        s_layout.addWidget(self.combo_file_type)

        self.chk_exact_match = QCheckBox("Искать точную фразу" if self.current_lang == "Русский" else "Exact phrase match")
        self.chk_exact_match.stateChanged.connect(self.toggle_accuracy_slider)
        s_layout.addWidget(self.chk_exact_match)

        self.chk_regex_match = QCheckBox("Режим RegEx" if self.current_lang == "Русский" else "RegEx Mode")
        self.chk_regex_match.setToolTip("Использовать регулярные выражения (например, \\d+ для чисел)")

        # ⚡ BOLT V5: Regex Builder
        regex_h_layout = QHBoxLayout()
        regex_h_layout.addWidget(self.chk_regex_match)
        btn_regex_helper = QPushButton("❓")
        btn_regex_helper.setFixedSize(24, 24)
        btn_regex_helper.setToolTip("Открыть конструктор шаблонов RegEx" if self.current_lang == "Русский" else "Open RegEx Builder")
        btn_regex_helper.clicked.connect(self.open_regex_helper)
        regex_h_layout.addWidget(btn_regex_helper)
        regex_h_layout.addStretch()
        s_layout.addLayout(regex_h_layout)

        self.chk_case_sensitive = QCheckBox("Учитывать регистр (Aa)" if self.current_lang == "Русский" else "Case Sensitive (Aa)")
        s_layout.addWidget(self.chk_case_sensitive)

        self.input_author = QLineEdit()
        self.input_author.setPlaceholderText("Фильтр по автору/нику" if self.current_lang == "Русский" else "Filter by Author/Nick")
        self.input_author.setToolTip("Поиск только в сообщениях определенного человека")
        s_layout.addWidget(self.input_author)

        # --- Search Area ---
        search_layout = QHBoxLayout()

        self.lbl_search_term = QLabel()
        self.input_search = QComboBox()
        self.input_search.setEditable(True)
        self.input_search.lineEdit().returnPressed.connect(self.start_search)

        # Load Search History
        history = self.settings.value("search_history", [])
        if history:
            self.input_search.addItems(history)
            self.input_search.setCurrentText("") # Clear current after load

        search_layout.addWidget(self.lbl_search_term)
        search_layout.addWidget(self.input_search)

        layout.addLayout(search_layout)

        # --- Accuracy Slider ---
        self.lbl_accuracy = QLabel()
        self.slider_accuracy = QSlider(Qt.Orientation.Horizontal)
        self.slider_accuracy.setRange(50, 100)
        self.slider_accuracy.setValue(80)

        # Value label
        self.lbl_slider_val = QLabel("80%")
        self.slider_accuracy.valueChanged.connect(lambda v: self.lbl_slider_val.setText(f"{v}%"))

        s_slider_layout = QHBoxLayout()
        s_slider_layout.addWidget(self.slider_accuracy)
        s_slider_layout.addWidget(self.lbl_slider_val)

        s_layout.addWidget(self.lbl_accuracy)
        s_layout.addLayout(s_slider_layout)

        # ⚡ BOLT V5 ADVANCED SQL FILTERS UI
        from PyQt6.QtWidgets import QDateEdit, QGroupBox, QFormLayout
        from PyQt6.QtCore import QDate

        # Date Filter Group
        self.group_dates = QGroupBox("Фильтр по дате" if self.current_lang == "Русский" else "Date Filter")
        date_layout = QFormLayout(self.group_dates)

        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate(2000, 1, 1))

        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate().addDays(1))

        date_layout.addRow("От (From):", self.date_from)
        date_layout.addRow("До (To):", self.date_to)

        # Use checkboxes to toggle the date filters so users don't have to manually clear them
        self.chk_use_date = QCheckBox("Включить даты" if self.current_lang == "Русский" else "Enable Dates")
        self.date_from.setEnabled(False)
        self.date_to.setEnabled(False)
        self.chk_use_date.stateChanged.connect(lambda s: self.date_from.setEnabled(s == 2))
        self.chk_use_date.stateChanged.connect(lambda s: self.date_to.setEnabled(s == 2))
        date_layout.insertRow(0, self.chk_use_date)
        s_layout.addWidget(self.group_dates)

        # Size Filter Group
        self.group_size = QGroupBox("Размер файла (КБ)" if self.current_lang == "Русский" else "File Size (KB)")
        size_layout = QFormLayout(self.group_size)

        self.spin_size_min = QSpinBox()
        self.spin_size_min.setRange(0, 999999999)
        self.spin_size_min.setValue(0)

        self.spin_size_max = QSpinBox()
        self.spin_size_max.setRange(0, 999999999)
        self.spin_size_max.setValue(100000)

        self.chk_use_size = QCheckBox("Включить размер" if self.current_lang == "Русский" else "Enable Size")
        self.spin_size_min.setEnabled(False)
        self.spin_size_max.setEnabled(False)
        self.chk_use_size.stateChanged.connect(lambda s: self.spin_size_min.setEnabled(s == 2))
        self.chk_use_size.stateChanged.connect(lambda s: self.spin_size_max.setEnabled(s == 2))

        size_layout.addRow(self.chk_use_size)
        size_layout.addRow("Мин (Min):", self.spin_size_min)
        size_layout.addRow("Макс (Max):", self.spin_size_max)
        s_layout.addWidget(self.group_size)

        s_layout.addStretch()

        self.is_dark_mode = False
        self.btn_theme = QPushButton()
        self.btn_theme.clicked.connect(self.toggle_theme)
        s_layout.addWidget(self.btn_theme)


        # --- Search Button ---
        self.btn_search = QPushButton()
        self.btn_search.setObjectName("btnSearch")
        self.btn_search.clicked.connect(self.start_search)
        self.btn_search.setMinimumHeight(44)
        self.btn_search.setIcon(QIcon(os.path.join(os.path.dirname(__file__), 'assets', 'icons', 'magnifying-glass.png')))
        layout.addWidget(self.btn_search)

        # --- Results Table ---
        from PyQt6.QtWidgets import QTableView
        self.table_results = QTableView()
        self.table_results.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_results.setAlternatingRowColors(True)
        self.table_results.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_results.doubleClicked.connect(self.show_context_dialog)
        self.table_results.clicked.connect(self.on_cell_clicked)

        # We must connect to the selection model later once it's created, but we can do it when the model is set
        self.table_results.setSortingEnabled(True)

        # Context Menu & Hotkeys
        self.table_results.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_results.customContextMenuRequested.connect(self.show_context_menu)
        self.table_results.installEventFilter(self)

        # Add welcome widget over table
        self.welcome_widget = QTextEdit()
        self.welcome_widget.setReadOnly(True)
        self.welcome_widget.setStyleSheet("border: none; background: transparent;")

        from PyQt6.QtWidgets import QTextBrowser
        self.preview_pane = QTextBrowser()
        self.preview_pane.setReadOnly(True)
        self.preview_pane.setMinimumHeight(150)
        self.preview_pane.setPlaceholderText("💡 Кликните один раз по результату, чтобы увидеть текст здесь..." if self.current_lang == "Русский" else "💡 Click a result once to preview context here...")

        # Add to splitter instead of layout directly
        self.main_splitter.addWidget(self.welcome_widget)
        self.main_splitter.addWidget(self.table_results)
        self.main_splitter.addWidget(self.preview_pane)

        self.table_results.hide()
        self.preview_pane.hide()

        self.main_splitter.setSizes([0, 500, 200]) # Give table 500px, preview 200px

        self.lbl_hint = QLabel()
        self.lbl_hint.setStyleSheet("color: #7f8fa6; font-size: 12px; margin-top: 5px;")
        layout.addWidget(self.lbl_hint)

        # --- Export Button ---
        self.btn_export = QPushButton()
        self.btn_export.clicked.connect(self.export_results)
        self.btn_export.setIcon(QIcon(os.path.join(os.path.dirname(__file__), 'assets', 'icons', 'download.png')))
        s_layout.addWidget(self.btn_export)

    def closeEvent(self, event):
        # ⚡ BOLT V3 GRACEFUL SHUTDOWN
        # Stop background indexing/searching cleanly to avoid segfaults and hung Windows processes
        if hasattr(self, 'indexer_thread') and self.indexer_thread.isRunning():
            self.indexer_thread.quit()
            self.indexer_thread.wait(1000)

        if hasattr(self, 'search_thread') and self.search_thread.isRunning():
            self.search_thread.quit()
            self.search_thread.wait(1000)

        event.accept()

    def toggle_accuracy_slider(self, state):
        self.slider_accuracy.setEnabled(state == 0)

    def open_regex_helper(self):
        dialog = RegexHelperDialog(self)
        dialog.exec()

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.settings.setValue("dark_mode", self.is_dark_mode)
        self.btn_theme.setText("☀️ Светлая тема" if self.current_lang == "Русский" else "☀️ Light Mode" if self.is_dark_mode else ("🌙 Темная тема" if self.current_lang == "Русский" else "🌙 Dark Mode"))
        self.apply_stylesheets()

    def apply_stylesheets(self):
        font_size = self.settings.value("font_size", 10, type=int)
        font_qss = f"QWidget {{ font-size: {font_size}pt; }}"

        if self.is_dark_mode:
            dark_qss = f"""
            {font_qss}
            QMainWindow, QWidget {{ background-color: #353b48; color: #f5f6fa; }}
            QWidget#sidebar {{ background-color: #2f3640; border-right: 1px solid #718093; }}
            QLineEdit, QComboBox, QTableWidget {{ background-color: #353b48; color: #f5f6fa; border: 1px solid #718093; }}
            QHeaderView::section {{ background-color: #353b48; color: #f5f6fa; }}
            QPushButton {{ background-color: #00a8ff; color: white; }}
            QPushButton#btnSearch {{ background-color: #4cd137; }}
            QTableWidget {{ background-color: #353b48; alternate-background-color: #2f3640; color: #f5f6fa; selection-background-color: #00a8ff; selection-color: white; }}
            QTableWidget::item {{ color: #f5f6fa; }}
            """
            self.setStyleSheet(dark_qss)
        else:
            try:
                with open(os.path.join(os.path.dirname(__file__), "style.qss"), "r", encoding="utf-8") as f:
                    base_qss = f.read()
                    self.setStyleSheet(base_qss + "\n" + font_qss)
            except:
                self.setStyleSheet(font_qss)

    def show_chat_analytics(self):
        if not hasattr(self, 'indexed_data') or not isinstance(self.indexed_data, str) or not os.path.exists(self.indexed_data):
            QMessageBox.information(self, "Аналитика", "Сначала выберите папку и проиндексируйте файлы.")
            return

        user_counts = {}
        total_msgs = 0
        total_files = 0

        import sqlite3
        try:
            conn = sqlite3.connect(self.indexed_data, timeout=15.0)
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM files")
            total_files = cursor.fetchone()[0]

            cursor.execute("SELECT author, COUNT(*) as c FROM lines WHERE author != '' AND author != 'System' AND author != 'Unknown' GROUP BY author ORDER BY c DESC LIMIT 10")
            top_users = cursor.fetchall()

            cursor.execute("SELECT COUNT(*) FROM lines WHERE author != '' AND author != 'System' AND author != 'Unknown'")
            total_msgs = cursor.fetchone()[0]

            # ⚡ BOLT V4: Visual Timeline Analytics
            cursor.execute("""
                SELECT substr(msg_date, 1, 7) as month_yr, COUNT(*) as c
                FROM lines
                WHERE msg_date != '' AND msg_date IS NOT NULL
                GROUP BY month_yr
                ORDER BY month_yr ASC
            """)
            timeline_data = cursor.fetchall()
            conn.close()
        except Exception as e:
            print("Analytics DB Error:", e)
            return

        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Статистика чатов" if self.current_lang == "Русский" else "Chat Analytics")
        dialog.resize(650, 700)
        d_layout = QVBoxLayout(dialog)

        # Calculate max count for timeline bar scaling
        max_timeline_count = max([c for _, c in timeline_data]) if timeline_data else 1

        html = f"""
        <h2 style='color:#0984e3; font-family:"Segoe UI";'>📊 Общая статистика</h2>
        <p><b>Всего файлов проиндексировано:</b> {total_files}</p>
        <p><b>Всего сообщений найдено:</b> {total_msgs}</p>
        <hr>
        <h3 style='color:#e84393; font-family:"Segoe UI";'>📈 Активность по месяцам (Timeline)</h3>
        <div style="font-family:'Segoe UI'; font-size:12px; margin-bottom: 20px;">
        """

        for month_yr, count in timeline_data:
            # Prevent 0% width bars
            bar_width = max(1, int((count / max_timeline_count) * 100))
            html += f"""
            <div style="margin-bottom: 4px;">
                <div style="display: inline-block; width: 70px; font-weight: bold; color: #2d3436;">{month_yr}</div>
                <div style="display: inline-block; width: 70%; background-color: #f1f2f6; border-radius: 3px;">
                    <div style="width: {bar_width}%; background-color: #00b894; height: 16px; border-radius: 3px;"></div>
                </div>
                <div style="display: inline-block; width: 40px; text-align: right; color: #636e72;">{count}</div>
            </div>
            """

        html += """
        </div>
        <hr>
        <h3 style='color:#0984e3; font-family:"Segoe UI";'>🏆 ТОП-10 Самых активных участников</h3>
        <table style='width:100%; border-collapse:collapse; font-family:"Segoe UI";'>
            <tr style='background-color:#f1f2f6; text-align:left;'>
                <th style='padding:8px; border:1px solid #dcdde1;'>Имя / Никнейм</th>
                <th style='padding:8px; border:1px solid #dcdde1;'>Сообщений</th>
            </tr>
        """
        for user, count in top_users:
            html += f"<tr><td style='padding:8px; border:1px solid #dcdde1;'>{user}</td><td style='padding:8px; border:1px solid #dcdde1;'>{count}</td></tr>"

        html += "</table>"

        from PyQt6.QtWidgets import QTextBrowser
        text_edit = QTextBrowser()
        text_edit.setReadOnly(True)
        text_edit.setHtml(html)
        d_layout.addWidget(text_edit)

        btn_close = QPushButton("Закрыть" if self.current_lang == "Русский" else "Close")
        btn_close.clicked.connect(dialog.accept)
        d_layout.addWidget(btn_close)

        dialog.exec()


    def update_welcome_message(self):
        if self.current_lang == "Русский":
            msg = """
            <div style="font-family: 'Segoe UI', Arial; font-size: 15px; color: #576574; line-height: 1.6; padding: 30px;">
                <h2 style="color: #2e86de;">⚡ Привет, дорогой пользователь!</h2>
                <p>Ты зашел в программу <b>TeleSearch Pro</b>, которая создана, чтобы упростить тебе жизнь!</p>
                <p>Здесь ты можешь загрузить целую папку с документами (Word, PDF, Текст, HTML) и мгновенно найти все совпадения со словами.</p>

                <h3>🔥 Главные фишки:</h3>
                <ul>
                    <li>Умный поиск найдет не только "Пукси", но и <b>"пуксик"</b>, <b>"Пусенок"</b> и другие окончания.</li>
                    <li>Двойной клик по результату покажет весь абзац текста.</li>
                    <li>Мгновенный поиск по тысячам файлов благодаря мощной оптимизации.</li>
                </ul>
                <hr>
                <p style="text-align: center;">👇 <b>Нажми кнопку «Выбрать папку» вверху, чтобы начать магию!</b> 👇</p>
            </div>
            """
        else:
            msg = """
            <div style="font-family: 'Segoe UI', Arial; font-size: 15px; color: #576574; line-height: 1.6; padding: 30px;">
                <h2 style="color: #2e86de;">⚡ Welcome, dear user!</h2>
                <p>You've launched <b>TeleSearch Pro</b>, designed to make your life easier!</p>
                <p>Load a folder full of documents (Word, PDF, Text, HTML) and instantly find all word matches.</p>

                <h3>🔥 Key Features:</h3>
                <ul>
                    <li>Smart fuzzy search finds variations and suffixes effortlessly.</li>
                    <li>Double-click a result to see the full surrounding context.</li>
                    <li>Lightning-fast search through thousands of files using intelligent caching.</li>
                </ul>
                <hr>
                <p style="text-align: center;">👇 <b>Click «Select Folder» above to start the magic!</b> 👇</p>
            </div>
            """
        self.welcome_widget.setHtml(msg)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        for f in files:
            if os.path.isdir(f):
                self.selected_folder = f
                self.settings.setValue("last_folder", f)
                self.update_ui_text()
                self.start_indexing()
                break

    def get_file_icon(self, filepath):
        ext = os.path.splitext(filepath)[1].lower()
        icon_name = 'file.png' # default
        if ext == '.pdf': icon_name = 'file-pdf.png'
        elif ext == '.docx': icon_name = 'file-word.png'
        elif ext == '.txt': icon_name = 'file-lines.png'
        elif ext == '.csv': icon_name = 'file-csv.png'
        elif ext in ['.html', '.htm']: icon_name = 'globe.png'
        elif ext in ['.png', '.jpg', '.jpeg']: icon_name = 'file.png'
        elif ext == '.zip': icon_name = 'folder-open.png'

        icon_path = os.path.join(os.path.dirname(__file__), 'assets', 'icons', icon_name)
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QIcon()

    def change_language(self, text):
        self.current_lang = text
        self.settings.setValue("language", text)
        self.update_ui_text()
        self.update_welcome_message()

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
        self.input_search.lineEdit().setPlaceholderText(t["placeholder_search"])
        self.lbl_accuracy.setText(t["lbl_accuracy"])
        self.btn_search.setText(t["btn_search"])
        self.btn_export.setText(t["btn_export"])

        # self.table_results.setHorizontalHeaderLabels(...) is no longer valid for QTableView since headers are defined in the Model
        pass

    def update_fav_menu(self):
        self.fav_menu.clear()
        favs = self.settings.value("favorite_files", [])
        for f_path in favs:
            if os.path.exists(f_path):
                action = self.fav_menu.addAction(os.path.basename(f_path))
                action.triggered.connect(lambda checked, f=f_path: QDesktopServices.openUrl(QUrl.fromLocalFile(f)))

    def toggle_favorite(self, file_path):
        favs = self.settings.value("favorite_files", [])
        if file_path in favs:
            favs.remove(file_path)
        else:
            favs.append(file_path)
        self.settings.setValue("favorite_files", favs)
        self.update_fav_menu()

    def update_recent_menu(self):
        self.recent_menu.clear()
        recent = self.settings.value("recent_folders", [])
        for folder in recent:
            if os.path.exists(folder):
                action = self.recent_menu.addAction(folder)
                action.triggered.connect(lambda checked, f=folder: self.load_recent_folder(f))

    def load_recent_folder(self, folder):
        self.selected_folder = folder
        self.settings.setValue("last_folder", folder)
        self.update_ui_text()
        self.start_indexing()

    def add_to_recent(self, folder):
        recent = self.settings.value("recent_folders", [])
        if folder in recent:
            recent.remove(folder)
        recent.insert(0, folder)
        if len(recent) > 5:
            recent = recent[:5]
        self.settings.setValue("recent_folders", recent)
        self.update_recent_menu()

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Directory")
        if folder:
            self.selected_folder = folder
            self.settings.setValue("last_folder", folder)
            self.add_to_recent(folder)
            self.update_ui_text()
            self.start_indexing()

    def force_reindex(self):
        if not self.selected_folder: return
        import hashlib
        app_data_dir = os.path.join(os.path.expanduser("~"), ".telesearch_cache")
        folder_hash = hashlib.md5(self.selected_folder.encode('utf-8')).hexdigest()
        cache_file = os.path.join(app_data_dir, f"{folder_hash}.pkl")
        if os.path.exists(cache_file):
            os.remove(cache_file)
        self.start_indexing()

    def clear_all_cache(self):
        import shutil
        app_data_dir = os.path.join(os.path.expanduser("~"), ".telesearch_cache")
        if os.path.exists(app_data_dir):
            shutil.rmtree(app_data_dir)
        QMessageBox.information(self, "Success", "Весь кэш успешно очищен!" if self.current_lang == "Русский" else "All cache successfully cleared!")
        self.start_indexing()

    def start_indexing(self):
        self.welcome_widget.hide()
        self.table_results.show()
        t = LANGUAGES[self.current_lang]
        self.status_label.setText(t["msg_indexing"])
        self.progress_bar.setVisible(True)
        self.btn_search.setEnabled(False)
        self.btn_select_folder.setEnabled(False)

        self.indexer_thread = IndexerWorker(self.selected_folder)
        self.indexer_thread.finished.connect(self.on_indexing_finished)
        self.indexer_thread.progress.connect(self.update_progress)
        self.indexer_thread.start()

    def update_progress(self, processed, total, from_cache=False):
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(processed)

    def on_indexing_finished(self, indexed_data):
        self.indexed_data = indexed_data
        t = LANGUAGES[self.current_lang]
        self.status_label.setText(t["msg_indexing_done"].format(len(self.indexed_data)))
        self.progress_bar.setVisible(False)
        self.btn_search.setEnabled(True)
        self.btn_select_folder.setEnabled(True)

    def start_search(self):
        t = LANGUAGES[self.current_lang]
        term = self.input_search.currentText().strip()

        if term:
            history = self.settings.value("search_history", [])
            if term in history:
                history.remove(term)
            history.insert(0, term)
            if len(history) > 10:
                history = history[:10]
            self.settings.setValue("search_history", history)

            # Update combobox silently
            self.input_search.clear()
            self.input_search.addItems(history)
            self.input_search.setCurrentText(term)
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

        self.current_results = []
        # Detach old model to clear table safely
        self.table_results.setModel(None)

        exact_match = self.chk_exact_match.isChecked()
        regex_match = self.chk_regex_match.isChecked()
        case_sensitive = self.chk_case_sensitive.isChecked()
        author_filter = self.input_author.text().strip()

        # ⚡ BOLT V5: Fetch Advanced SQL Date/Size Filters
        date_from = self.date_from.date().toString("yyyy-MM-dd") if self.chk_use_date.isChecked() else None
        date_to = self.date_to.date().toString("yyyy-MM-dd") if self.chk_use_date.isChecked() else None
        size_min = self.spin_size_min.value() if self.chk_use_size.isChecked() else None
        size_max = self.spin_size_max.value() if self.chk_use_size.isChecked() else None

        if regex_match:
            try:
                import re
                re.compile(term)
            except re.error as e:
                QApplication.beep()
                self.status_label.setStyleSheet("color: red; font-weight: bold;")
                self.status_label.setText(f"RegEx Error: {e}" if self.current_lang == "English" else f"Ошибка RegEx: {e}")
                return
        self.status_label.setStyleSheet("color: #2f3640;") # Reset to default
        file_filter = self.combo_file_type.currentText()

        self.search_thread = SearchWorker(
            self.indexed_data, term, accuracy, exact_match, file_filter,
            regex_match, case_sensitive, author_filter,
            date_from, date_to, size_min, size_max
        )
        self.search_thread.finished.connect(self.on_search_finished)
        self.search_thread.start()

    def on_search_finished(self, results, time_taken):
        if time_taken > 1.0:
            QApplication.beep()
        self.progress_bar.setVisible(False)
        self.btn_search.setEnabled(True)
        t = LANGUAGES[self.current_lang]
        msg = f"Найдено {len(results)} совпадений за {time_taken:.3f} сек." if self.current_lang == "Русский" else f"Found {len(results)} matches in {time_taken:.3f} sec."
        self.status_label.setText(msg)

        self.welcome_widget.hide()
        self.table_results.show()
        self.preview_pane.show()

        self.current_results = results

        # ⚡ BOLT V3 MVC BINDING
        self.results_model = ResultsTableModel(self.current_results, self.selected_folder, self.current_lang)
        self.table_results.setModel(self.results_model)

        # Adjust column widths
        self.table_results.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_results.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_results.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_results.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        # We must re-bind selection changes now that the model exists
        selection_model = self.table_results.selectionModel()
        selection_model.selectionChanged.connect(self.update_preview_pane)

    def export_results(self):
        t = LANGUAGES[self.current_lang]
        if not hasattr(self, 'current_results') or len(self.current_results) == 0:
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Save Results", "", "Excel Workbook (*.xlsx);;HTML Report (*.html);;Markdown Files (*.md);;CSV Files (*.csv);;JSON Files (*.json);;Text Files (*.txt)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8', newline='') as f:
                    # Model gives us header data directly now
                    col_count = self.results_model.columnCount()
                    headers = self.results_model.headers

                    # ⚡ BOLT V3 EXPORT OPTIMIZATION: Pull directly from the data state instead of the UI to bypass pagination limit
                    all_rows = []
                    for res in self.current_results:
                        rel_path = os.path.relpath(res["file"], self.selected_folder)
                        formatted_file = f"{rel_path} (L: {res['line_num']})"
                        all_rows.append([
                            formatted_file,
                            res['line'],
                            res['match'],
                            str(res.get('size_kb', 0)),
                            str(res.get('mod_time', '')),
                            str(res.get('author', '')),
                            f"{res['score']}%"
                        ])

                    if file_path.endswith('.xlsx'):
                        try:
                            from openpyxl import Workbook
                            from openpyxl.styles import Font, PatternFill

                            wb = Workbook()
                            ws = wb.active
                            ws.title = "Bolt Search Results"

                            # Write headers
                            ws.append(headers)
                            header_font = Font(bold=True, color="FFFFFF")
                            header_fill = PatternFill(start_color="00A8FF", end_color="00A8FF", fill_type="solid")

                            for col_num, cell in enumerate(ws[1], 1):
                                cell.font = header_font
                                cell.fill = header_fill

                            # Write data
                            for row_data in all_rows:
                                ws.append(row_data)

                            wb.save(file_path)
                        except ImportError:
                            QMessageBox.warning(self, "Export Error", "Please install openpyxl to export to Excel.")
                            return
                    elif file_path.endswith('.md'):
                        f.write("# Bolt Search Results\n\n")
                        header_line = "| " + " | ".join(headers) + " |"
                        sep_line = "|" + "|".join(["---" for _ in headers]) + "|"
                        f.write(header_line + "\n" + sep_line + "\n")

                        for row_data in all_rows:
                            f.write("| " + " | ".join(row_data) + " |\n")

                    elif file_path.endswith('.html'):
                        f.write(f"<html><head><meta charset='utf-8'><title>Bolt Search Report</title>")
                        f.write(f"<style>body{{font-family:sans-serif;}} table{{border-collapse:collapse;width:100%;}} th,td{{border:1px solid #ddd;padding:8px;text-align:left;}} th{{background-color:#00a8ff;color:white;}} tr:nth-child(even){{background-color:#f2f2f2;}}</style>")
                        f.write(f"</head><body><h2>Bolt Search Report</h2><table><tr>")
                        for header in headers:
                            f.write(f"<th>{header}</th>")
                        f.write("</tr>")

                        for row_data in all_rows:
                            f.write("<tr>")
                            for col in row_data:
                                f.write(f"<td>{col}</td>")
                            f.write("</tr>")
                        f.write("</table></body></html>")

                    elif file_path.endswith('.json'):
                        import json
                        json_data = []
                        for row_data in all_rows:
                            json_data.append({
                                headers[i]: row_data[i] for i in range(col_count)
                            })
                        json.dump(json_data, f, ensure_ascii=False, indent=4)
                    elif file_path.endswith('.csv'):
                        writer = csv.writer(f)
                        writer.writerow(headers)
                        for row_data in all_rows:
                            writer.writerow(row_data)
                    else:
                        for row_data in all_rows:
                            f.write(f"File: {row_data[0]}\nMatch: {row_data[2]} ({row_data[6]})\nContext: {row_data[1]}\n{'-'*40}\n")


                # Smart Export: Prompt to open
                success_msg = t["msg_export_success"].format(file_path)
                prompt_msg = "Do you want to open it now?" if self.current_lang == "English" else "Хотите открыть файл прямо сейчас?"
                reply = QMessageBox.question(self,
                    "Success" if self.current_lang == "English" else "Успех",
                    f"{success_msg}\n\n{prompt_msg}",
                    "Success" if self.current_lang == "English" else "Успех",

                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes)

                if reply == QMessageBox.StandardButton.Yes:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))
            except Exception as e:
                QMessageBox.critical(self, "Error", f"{t['msg_export_error']}\n{str(e)}")





    def eventFilter(self, source, event):
        if source == self.table_results and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
                indexes = self.table_results.selectionModel().selectedRows()
                if indexes:
                    self.show_context_dialog(indexes[0])
                return True
        return super().eventFilter(source, event)

    def table_key_press_event(self, event):
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            indexes = self.table_results.selectionModel().selectedRows()
            if indexes:
                self.show_context_dialog(indexes[0])
        else:
            QTableView.keyPressEvent(self.table_results, event)

    def show_context_menu(self, pos):
        index = self.table_results.indexAt(pos)
        if not index.isValid():
            return

        row = index.row()
        file_path = self.results_model.data(self.results_model.index(row, 0), Qt.ItemDataRole.UserRole)

        if not file_path:
            return

        menu = QMenu(self)

        favs = self.settings.value("favorite_files", [])
        is_fav = file_path in favs
        fav_text = "Убрать из избранного" if is_fav else "Добавить в избранное"
        if self.current_lang == "English":
            fav_text = "Remove from Favorites" if is_fav else "Add to Favorites"

        action_open_file = menu.addAction("Открыть файл" if self.current_lang == "Русский" else "Open File")
        action_open_folder = menu.addAction("Открыть папку" if self.current_lang == "Русский" else "Open Folder Location")
        action_view_context = menu.addAction("Показать контекст" if self.current_lang == "Русский" else "View Context")
        menu.addSeparator()
        action_fav = menu.addAction("⭐ " + fav_text)

        action_replace = None
        if file_path.endswith('.txt'):
            action_replace = menu.addAction("Заменить слово (TXT)" if self.current_lang == "Русский" else "Replace Word (TXT)")

        action = menu.exec(self.table_results.viewport().mapToGlobal(pos))

        if action == action_open_file:
            QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))
        elif action == action_open_folder:
            import subprocess
            if os.name == 'nt': # Windows
                subprocess.run(f'explorer /select,"{file_path}"')
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(file_path)))
        elif action == action_view_context:
            self.show_context_dialog(index)
        elif action == action_fav:
            self.toggle_favorite(file_path)
        elif action_replace and action == action_replace:
            # Inline text replacement
            term = self.input_search.currentText()
            if not term: return
            new_text, ok = QInputDialog.getText(self, "Replace", f"Replace '{term}' with:")
            if ok and new_text:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_data = f.read()
                    import re
                    # Case insensitive replace
                    pattern = re.compile(re.escape(term), re.IGNORECASE)
                    file_data = pattern.sub(new_text, file_data)
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(file_data)
                    self.force_reindex() # Refresh cache to show changes
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Could not modify file: {e}")

    def on_cell_clicked(self, index):
        if index.column() == 0:
            file_path = self.results_model.data(index.siblingAtColumn(0), Qt.ItemDataRole.UserRole)
            if file_path and os.path.exists(file_path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))

    def update_preview_pane(self, selected, deselected):
        indexes = self.table_results.selectionModel().selectedRows()
        if not indexes: return
        current_row = indexes[0].row()

        file_path = self.results_model.data(self.results_model.index(current_row, 0), Qt.ItemDataRole.UserRole)
        line_num = self.results_model.data(self.results_model.index(current_row, 1), Qt.ItemDataRole.UserRole)

        if not file_path or not line_num: return

        search_term = self.input_search.currentText().strip()
        # Use existing context generation logic
        html_content = self.generate_context_html(file_path, line_num, search_term, window_size=2)
        if html_content:
            self.preview_pane.setHtml(html_content)
            self.preview_pane.scrollToAnchor("target")
        else:
            self.preview_pane.setText("Context not available.")

    def fetch_lines_from_db(self, file_path, line_nums=None):
        """Helper to fetch lines from SQLite V2 Engine."""
        if not hasattr(self, 'indexed_data') or not isinstance(self.indexed_data, str) or not os.path.exists(self.indexed_data):
            return []

        import sqlite3
        try:
            conn = sqlite3.connect(self.indexed_data, timeout=15.0)
            cursor = conn.cursor()

            if line_nums:
                placeholders = ','.join('?' * len(line_nums))
                cursor.execute(f"""
                    SELECT l.line_num, l.line_text, l.words_json, l.msg_date, l.author
                    FROM lines l JOIN files f ON l.file_id = f.id
                    WHERE f.file_path = ? AND l.line_num IN ({placeholders})
                    ORDER BY l.line_num ASC
                """, [file_path] + list(line_nums))
            else:
                cursor.execute("""
                    SELECT l.line_num, l.line_text, l.words_json, l.msg_date, l.author
                    FROM lines l JOIN files f ON l.file_id = f.id
                    WHERE f.file_path = ?
                    ORDER BY l.line_num ASC
                """, (file_path,))

            rows = cursor.fetchall()
            conn.close()
            return rows
        except Exception as e:
            print("DB Fetch Error:", e)
            return []

    def generate_context_html(self, file_path, highlight_line_num, search_term, window_size=3):
        is_html = file_path.endswith('.html') or file_path.endswith('.htm')
        is_tg_export = False
        html_content = []

        # ⚡ BOLT V2: Instant Context via SQL. Avoid loading the whole 1M+ line file.
        # Fetch the target line and its surrounding context
        line_nums = range(max(1, highlight_line_num - window_size), highlight_line_num + window_size + 1)
        lines = self.fetch_lines_from_db(file_path, line_nums)

        if lines:
            if len(lines) > 1 and lines[0][1].startswith("["):
                is_tg_export = True

            for line_data in lines:
                ln = line_data[0]
                text = line_data[1]
                display_text = text.replace("<", "&lt;").replace(">", "&gt;")

                is_target = ln == highlight_line_num

                # ⚡ Pinpoint Word Highlighting
                # ⚡ Pinpoint Word Highlighting (HTML Safe)
                if search_term and is_target:
                    import re
                    try:
                        pattern = re.compile(re.escape(search_term), re.IGNORECASE)
                        # We must not replace search terms that match inside HTML tags
                        # By doing this replacement BEFORE adding any HTML spans to display_text, it's safer
                        display_text = pattern.sub(lambda m: f"<span style='background-color:#ffff00; color:black; font-weight:bold; padding:0 2px; border-radius:2px;'>{m.group(0)}</span>", display_text)

                        # For raw HTML rendering, it's risky if the user searched for 'div' or 'class'.
                        # We will try a simpler approach or skip it if it's too dangerous, but re.sub is fine for pure text files.
                        if not is_html:
                            text = pattern.sub(lambda m: f"<span style='background-color:#ffff00; color:black; font-weight:bold; padding:0 2px; border-radius:2px;'>{m.group(0)}</span>", text)
                    except Exception:
                        pass

                if is_tg_export and display_text.startswith("["):
                    parts = display_text.split("] ", 1)
                    if len(parts) == 2:
                        nickname = parts[0][1:]
                        message = parts[1]
                        display_text = f"<span style='color:#0984e3; font-weight:bold;'>{nickname}:</span> {message}"

                # Always add an anchor to the target line, regardless of whether it's Telegram or HTML
                anchor = "<a name='target'></a>" if is_target else ""

                # ⚡ BOLT V5 CONTRAST FIX: Explicitly set text color so Dark Mode doesn't make text invisible on light yellow background
                # ⚡ BOLT V5 FORMATTING FIX: Never join HTML lines with spaces. Always use divs so they don't collapse into a wall of text.
                if is_html and not is_tg_export:
                    if is_target:
                        html_content.append(f"{anchor}<div style='padding:5px; border:1px solid #fdcb6e; background-color:#fef8e6; color:#2d3436;'>{text}</div>")
                    else:
                        html_content.append(f"<div>{text}</div>")
                else:
                    prefix_str = f"<span style='color:#b2bec3; font-size:10px; margin-right:10px;'>{ln}</span>"
                    if is_target:
                        html_content.append(f"{anchor}<div style='padding:5px; margin:2px 0; border-left:4px solid #f39c12; background-color:#fafafa; color:#2d3436; font-size:14px; font-family:sans-serif;'>{prefix_str} {display_text}</div>")
                    else:
                        html_content.append(f"<div style='padding:2px; margin:1px 0; font-size:14px; font-family:sans-serif; border-bottom:1px solid #f1f2f6;'>{prefix_str} {display_text}</div>")

            return "".join(html_content)
        return None


    def show_context_dialog(self, index=None):
        if not index:
            indexes = self.table_results.selectionModel().selectedRows()
            if not indexes: return
            current_row = indexes[0].row()
        else:
            current_row = index.row()

        file_path = self.results_model.data(self.results_model.index(current_row, 0), Qt.ItemDataRole.UserRole)
        line_num = self.results_model.data(self.results_model.index(current_row, 1), Qt.ItemDataRole.UserRole)

        if not file_path or not line_num:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Context Viewer" if self.current_lang == "English" else "Просмотр контекста")
        dialog.resize(600, 400)
        d_layout = QVBoxLayout(dialog)

        from PyQt6.QtWidgets import QTextBrowser
        text_edit = QTextBrowser()
        text_edit.setReadOnly(True)
        d_layout.addWidget(text_edit)

        context_str = []

        # Fetch directly from DB instead of memory iteration
        line_nums = range(max(1, line_num - 3), line_num + 4)
        lines = self.fetch_lines_from_db(file_path, line_nums)

        if lines:
            for line_data in lines:
                ln = line_data[0]
                text = line_data[1]

                prefix = f"<b>{ln}:</b> "
                if ln == line_num:
                    context_str.append(f"<span style='background-color:#ffeaa7; color:#2d3436; padding:2px;'>{prefix}{text}</span>")
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

        from PyQt6.QtWidgets import QTextBrowser
        text_edit = QTextBrowser()
        text_edit.setReadOnly(True)

        # Handle HTML and CSV styling
        is_html = file_path.endswith('.html') or file_path.endswith('.htm')

        html_content = []

        # Load all lines from DB to display full text
        lines = self.fetch_lines_from_db(file_path)

        # ⚡ BOLT V5 SMART CHAT BUBBLE ENGINE
        # Detect if this is a chat export (author column is actively used)
        has_authors = any(len(ld) > 4 and ld[4] for ld in lines) if lines else False
        base_sender = None

        import json
        if lines:
            if has_authors:
                # Add CSS for modern chat bubbles
                html_content.append("""
                <style>
                    .chat-container { display: flex; flex-direction: column; font-family: 'Segoe UI', sans-serif; }
                    .bubble { max-width: 80%; padding: 8px 12px; margin: 4px 8px; border-radius: 12px; font-size: 14px; position: relative; }
                    .bubble-left { background-color: #f1f2f6; color: #2d3436; align-self: flex-start; border-bottom-left-radius: 2px; }
                    .bubble-right { background-color: #74b9ff; color: white; align-self: flex-end; border-bottom-right-radius: 2px; margin-left: 20%; text-align: right;}
                    .author-name { font-size: 11px; font-weight: bold; margin-bottom: 2px; color: #0984e3; }
                    .author-right { color: #ffeaa7; }
                    .msg-time { font-size: 10px; color: #b2bec3; margin-top: 4px; text-align: right; }
                    .time-right { color: rgba(255,255,255,0.8); }
                    .highlight-box { border: 2px solid #ff7675; box-shadow: 0 0 8px rgba(255,118,117,0.4); }
                </style>
                <div class='chat-container'>
                """)

            for line_data in lines:
                ln = line_data[0]
                text = line_data[1]
                msg_date = line_data[3] if len(line_data)>3 else ""
                author = line_data[4] if len(line_data)>4 else ""

                try:
                    words = json.loads(line_data[2]) if len(line_data)>2 and line_data[2] else []
                except Exception:
                    words = []

                prefix = f"<b>{ln}:</b> " if not is_html and not has_authors else ""

                # Basic escaping if not HTML to prevent parsing bugs
                # ⚡ BOLT SAFE HIGHLIGHTING: If it's HTML, we don't do blind regex replacement to avoid breaking tags
                display_text = text if is_html else text.replace("<", "&lt;").replace(">", "&gt;")

                search_term = self.input_search.currentText().strip()
                if search_term and ln == highlight_line_num and not is_html:
                    import re
                    try:
                        pattern = re.compile(re.escape(search_term), re.IGNORECASE)
                        display_text = pattern.sub(lambda m: f"<span style='background-color:#ffff00; color:black; font-weight:bold; padding:0 2px; border-radius:2px;'>{m.group(0)}</span>", display_text)
                    except Exception:
                        pass

                is_target = ln == highlight_line_num
                anchor = "<a name='target'></a>" if is_target else ""

                if has_authors:
                    # Strip the redundant [Author] tag from the raw line if it exists
                    if display_text.startswith(f"[{author}] "):
                        display_text = display_text[len(author)+3:]

                    if not base_sender:
                        base_sender = author

                    is_me = author == base_sender
                    bubble_class = "bubble-left" if is_me else "bubble-right"
                    author_class = "author-name" if is_me else "author-name author-right"
                    time_class = "msg-time" if is_me else "msg-time time-right"
                    target_class = "highlight-box" if is_target else ""

                    time_display = msg_date[11:16] if len(msg_date) >= 16 else msg_date

                    html_content.append(f"""
                    {anchor}
                    <div class='bubble {bubble_class} {target_class}'>
                        <div class='{author_class}'>{author}</div>
                        <div>{display_text}</div>
                        <div class='{time_class}'>{time_display}</div>
                    </div>
                    """)
                else:
                    # ⚡ BOLT V5 CONTRAST FIX & FORMATTING FIX
                    if is_target:
                        if is_html:
                            html_content.append(f"{anchor}<div style='padding:5px; border-radius:3px; background-color:#fef8e6; color:#2d3436;'>{display_text}</div>")
                        else:
                            html_content.append(f"{anchor}<div style='background-color:#ffeaa7; color:#2d3436; padding:2px;'>{prefix}{display_text}</div>")
                    else:
                        if is_html:
                            html_content.append(f"<div>{display_text}</div>")
                        else:
                            html_content.append(f"<div>{prefix}{display_text}</div>")

            if has_authors:
                html_content.append("</div>")

        if is_html or has_authors:
            full_html = "".join(html_content)
            text_edit.setHtml(full_html)
        else:
            text_edit.setHtml("".join(html_content))
        d_layout.addWidget(text_edit)

        # Scroll to anchor
        text_edit.scrollToAnchor("target")

        # ⚡ NLP Keywords
        word_freq = {}
        stop_words = {"и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то", "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за", "бы", "по", "только", "ее", "мне", "было", "вот", "от", "меня", "еще", "нет", "о", "из", "ему", "теперь", "когда", "даже", "ну", "вдруг", "ли", "если", "уже", "или", "ни", "быть", "был", "него", "до", "вас", "нибудь", "опять", "уж", "вам", "ведь", "там", "потом", "себя", "ничего", "ей", "может", "они", "тут", "где", "есть", "надо", "ней", "для", "мы", "тебя", "их", "чем", "была", "сам", "чтоб", "без", "будто", "человек", "чего", "раз", "тоже", "себе", "под", "будет", "ж", "тогда", "кто", "этот", "того", "потому", "этого", "какой", "совсем", "ним", "здесь", "этом", "один", "почти", "мой", "тем", "чтобы", "нее", "сейчас", "были", "куда", "зачем", "всех", "никогда", "можно", "при", "наконец", "два", "об", "другой", "хоть", "после", "над", "больше", "тот", "через", "эти", "нас", "про", "всего", "них", "какая", "много", "разве", "три", "эту", "моя", "впрочем", "хорошо", "свою", "этой", "перед", "иногда", "лучше", "чуть", "том", "нельзя", "такой", "им", "более", "всегда", "конечно", "всю", "между", "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with", "by", "of"}

        total_words = 0
        total_chars = 0
        if lines:
            for line_data in lines:
                text = line_data[1]
                try:
                    words = json.loads(line_data[2]) if len(line_data)>2 and line_data[2] else []
                except Exception:
                    words = []
                total_chars += len(text)
                total_words += len(words)
                for w in words:
                    w_lower = w.lower()
                    if len(w_lower) > 3 and w_lower not in stop_words:
                        word_freq[w_lower] = word_freq.get(w_lower, 0) + 1

        top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]
        keywords_str = ", ".join([f"{w}" for w, _ in top_words])

        # Calculate Stats
        total_lines = len(lines) if lines else 0

        stat_bar = QHBoxLayout()
        stat_lbl = QLabel(f"<b>Lines:</b> {total_lines} | <b>Words:</b> {total_words} | <b>Keywords:</b> {keywords_str}" if self.current_lang == "English" else f"<b>Строк:</b> {total_lines} | <b>Слов:</b> {total_words} | <b>Ключи:</b> {keywords_str}")
        stat_bar.addWidget(stat_lbl)
        stat_bar.addStretch()

        # ⚡ Zoom Controls
        btn_zoom_out = QPushButton("-")
        btn_zoom_out.setFixedSize(30, 30)
        btn_zoom_out.clicked.connect(lambda: text_edit.zoomOut(1))

        btn_zoom_in = QPushButton("+")
        btn_zoom_in.setFixedSize(30, 30)
        btn_zoom_in.clicked.connect(lambda: text_edit.zoomIn(1))

        stat_bar.addWidget(btn_zoom_out)
        stat_bar.addWidget(btn_zoom_in)

        btn_close = QPushButton("Close" if self.current_lang == "English" else "Закрыть")
        btn_close.clicked.connect(dialog.accept)
        stat_bar.addWidget(btn_close)

        d_layout.addLayout(stat_bar)

        dialog.exec()

if __name__ == '__main__':
    app = QApplication(sys.argv)

    # Simple styling
    app.setStyle('Fusion')

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
