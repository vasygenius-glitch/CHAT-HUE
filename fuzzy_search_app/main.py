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

    def __init__(self, db_file, search_term, accuracy, exact_match, file_filter, regex_match=False, case_sensitive=False, author_filter=""):
        super().__init__()
        self.db_file = db_file
        self.search_term = search_term
        self.accuracy = accuracy
        self.exact_match = exact_match
        self.file_filter = file_filter
        self.regex_match = regex_match
        self.case_sensitive = case_sensitive
        self.author_filter = author_filter

    def run(self):
        import sqlite3
        # Ensure thread safety. SQLite connections cannot be passed across threads.
        # So we pass the file path and open it fresh inside this QThread!
        if not self.db_file or not os.path.exists(self.db_file):
            self.finished.emit([], 0.0)
            return

        # Handle File Filters (Push them to the DB query logic in searcher if possible, but for now we do post-filter)
        # Actually, it's safer to pass the file_filter string down to searcher to do it in SQL!

        results, time_taken = searcher.perform_search(self.db_file, self.search_term, self.accuracy, self.exact_match, self.regex_match, self.case_sensitive, self.author_filter)

        # Apply UI file filter
        if self.file_filter != "Все файлы (*.*)":
            if self.file_filter.startswith("Только Изображения"):
                results = [r for r in results if r["file"].lower().endswith(('.png', '.jpg', '.jpeg'))]
            else:
                ext = self.file_filter.split("*")[-1].replace(")", "").lower()
                results = [r for r in results if r["file"].lower().endswith(ext)]

        self.finished.emit(results, time_taken)


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

        # Load Stylesheet
        try:
            with open(os.path.join(os.path.dirname(__file__), "style.qss"), "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        except Exception:
            pass

        # Set App Icon
        icon_path = os.path.join(os.path.dirname(__file__), 'assets', 'app.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

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
        s_layout.addWidget(self.chk_regex_match)

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
        self.table_results = QTableWidget()
        self.table_results.setColumnCount(7)
        self.table_results.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_results.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_results.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_results.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table_results.setAlternatingRowColors(True)
        self.table_results.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_results.cellDoubleClicked.connect(self.show_context_dialog)
        self.table_results.cellClicked.connect(self.on_cell_clicked)
        self.table_results.itemSelectionChanged.connect(self.update_preview_pane)

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

    def toggle_accuracy_slider(self, state):
        self.slider_accuracy.setEnabled(state == 0)

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.settings.setValue("dark_mode", self.is_dark_mode)
        self.btn_theme.setText("☀️ Светлая тема" if self.current_lang == "Русский" else "☀️ Light Mode" if self.is_dark_mode else ("🌙 Темная тема" if self.current_lang == "Русский" else "🌙 Dark Mode"))

        if self.is_dark_mode:
            dark_qss = """
            QMainWindow, QWidget { background-color: #353b48; color: #f5f6fa; }
            QWidget#sidebar { background-color: #2f3640; border-right: 1px solid #718093; }
            QLineEdit, QComboBox, QTableWidget { background-color: #353b48; color: #f5f6fa; border: 1px solid #718093; }
            QHeaderView::section { background-color: #353b48; color: #f5f6fa; }
            QPushButton { background-color: #00a8ff; color: white; }
            QPushButton#btnSearch { background-color: #4cd137; }
            QTableWidget { background-color: #353b48; alternate-background-color: #2f3640; color: #f5f6fa; selection-background-color: #00a8ff; selection-color: white; }
            QTableWidget::item { color: #f5f6fa; }
            """
            self.setStyleSheet(dark_qss)
        else:
            try:
                with open(os.path.join(os.path.dirname(__file__), "style.qss"), "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())
            except:
                self.setStyleSheet("")

    def show_chat_analytics(self):
        if not hasattr(self, 'indexed_data') or not isinstance(self.indexed_data, str) or not os.path.exists(self.indexed_data):
            QMessageBox.information(self, "Аналитика", "Сначала выберите папку и проиндексируйте файлы.")
            return

        user_counts = {}
        total_msgs = 0
        total_files = 0

        import sqlite3
        try:
            conn = sqlite3.connect(self.indexed_data)
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM files")
            total_files = cursor.fetchone()[0]

            cursor.execute("SELECT author, COUNT(*) as c FROM lines WHERE author != '' AND author != 'System' AND author != 'Unknown' GROUP BY author ORDER BY c DESC LIMIT 10")
            top_users = cursor.fetchall()

            cursor.execute("SELECT COUNT(*) FROM lines WHERE author != '' AND author != 'System' AND author != 'Unknown'")
            total_msgs = cursor.fetchone()[0]
            conn.close()
        except Exception as e:
            print("Analytics DB Error:", e)
            return

        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Статистика чатов" if self.current_lang == "Русский" else "Chat Analytics")
        dialog.resize(500, 400)
        d_layout = QVBoxLayout(dialog)

        html = f"""
        <h2 style='color:#0984e3; font-family:"Segoe UI";'>📊 Общая статистика</h2>
        <p><b>Всего файлов проиндексировано:</b> {total_files}</p>
        <p><b>Всего сообщений найдено:</b> {total_msgs}</p>
        <hr>
        <h3 style='color:#e84393; font-family:"Segoe UI";'>🏆 ТОП-10 Самых активных участников</h3>
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

        col_size = "Размер (КБ)" if self.current_lang == "Русский" else "Size (KB)"
        col_date = "Дата/Время" if self.current_lang == "Русский" else "Date/Time"
        col_author = "Автор" if self.current_lang == "Русский" else "Author"
        self.table_results.setHorizontalHeaderLabels([t["col_file"], t["col_line"], t["col_match"], col_size, col_date, col_author, t["col_score"]])

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
        self.table_results.setRowCount(0) # Clear previous

        exact_match = self.chk_exact_match.isChecked()
        regex_match = self.chk_regex_match.isChecked()
        case_sensitive = self.chk_case_sensitive.isChecked()
        author_filter = self.input_author.text().strip()

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

        self.search_thread = SearchWorker(self.indexed_data, term, accuracy, exact_match, file_filter, regex_match, case_sensitive, author_filter)
        self.search_thread.finished.connect(self.on_search_finished)
        self.search_thread.start()

    def load_table_batch(self, start_idx, batch_size):
        if not hasattr(self, 'current_results') or not self.current_results:
            return

        end_idx = min(start_idx + batch_size, len(self.current_results))
        if start_idx >= end_idx:
            return

        for row in range(start_idx, end_idx):
            result = self.current_results[row]
            rel_path = os.path.relpath(result["file"], self.selected_folder)

            item_file = QTableWidgetItem(f"{rel_path} (L: {result['line_num']})")
            item_file.setForeground(QColor("#0984e3"))
            item_file.setIcon(self.get_file_icon(result["file"]))
            font = QFont()
            font.setUnderline(True)
            item_file.setFont(font)
            item_line = QTableWidgetItem(result["line"])
            item_match = QTableWidgetItem(result["match"])
            item_size = QTableWidgetItem(str(result.get("size_kb", 0)))
            item_date = QTableWidgetItem(result.get("mod_time", ""))
            item_author = QTableWidgetItem(result.get("author", ""))
            item_score = QTableWidgetItem(f"{result['score']}%")

            for item in [item_file, item_line, item_match, item_size, item_date, item_author, item_score]:
                item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)

            item_match.setBackground(QColor("#e6ffe6"))
            item_match.setFont(QFont("Arial", weight=QFont.Weight.Bold))

            item_size.setData(Qt.ItemDataRole.DisplayRole, int(result.get("size_kb", 0)))
            item_score.setData(Qt.ItemDataRole.DisplayRole, float(result["score"]))

            line_str = str(result["line_num"]).zfill(7)
            item_date.setData(Qt.ItemDataRole.UserRole, f"{result.get('mod_time', '')}|{line_str}")

            self.table_results.setItem(row, 0, item_file)
            self.table_results.setItem(row, 1, item_line)
            self.table_results.setItem(row, 2, item_match)
            self.table_results.setItem(row, 3, item_size)
            self.table_results.setItem(row, 4, item_date)
            self.table_results.setItem(row, 5, item_author)
            self.table_results.setItem(row, 6, item_score)

            item_file.setData(Qt.ItemDataRole.UserRole, result["file"])
            item_file.setData(Qt.ItemDataRole.UserRole + 1, result["line_num"])

        self.loaded_rows = end_idx

    def on_table_scrolled(self, value):
        if not hasattr(self, 'current_results') or not self.current_results:
            return

        scrollbar = self.table_results.verticalScrollBar()
        if value == scrollbar.maximum():
            # User scrolled to the bottom, load the next batch seamlessly
            self.load_table_batch(self.loaded_rows, 100)

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

        # Disable sorting while populating to prevent crashes
        self.table_results.setSortingEnabled(False)
        self.table_results.setRowCount(len(results))

        # Store results and setup lazy loading
        self.current_results = results
        self.loaded_rows = 0

        # Load the first 100 instantly, the rest load when user scrolls
        self.load_table_batch(0, 100)

        # Connect scroll event if not already connected
        try:
            self.table_results.verticalScrollBar().valueChanged.disconnect(self.on_table_scrolled)
        except Exception:
            pass
        self.table_results.verticalScrollBar().valueChanged.connect(self.on_table_scrolled)

        # Allow user to sort after initial load
        self.table_results.setSortingEnabled(True)

    def export_results(self):
        t = LANGUAGES[self.current_lang]
        if self.table_results.rowCount() == 0:
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Save Results", "", "Excel Workbook (*.xlsx);;HTML Report (*.html);;Markdown Files (*.md);;CSV Files (*.csv);;JSON Files (*.json);;Text Files (*.txt)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8', newline='') as f:
                    col_count = self.table_results.columnCount()
                    headers = [self.table_results.horizontalHeaderItem(i).text() for i in range(col_count)]

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
                            for row in range(self.table_results.rowCount()):
                                row_data = [self.table_results.item(row, i).text() for i in range(col_count)]
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

                        for row in range(self.table_results.rowCount()):
                            row_data = [self.table_results.item(row, i).text() for i in range(col_count)]
                            f.write("| " + " | ".join(row_data) + " |\n")

                    elif file_path.endswith('.html'):
                        f.write(f"<html><head><meta charset='utf-8'><title>Bolt Search Report</title>")
                        f.write(f"<style>body{{font-family:sans-serif;}} table{{border-collapse:collapse;width:100%;}} th,td{{border:1px solid #ddd;padding:8px;text-align:left;}} th{{background-color:#00a8ff;color:white;}} tr:nth-child(even){{background-color:#f2f2f2;}}</style>")
                        f.write(f"</head><body><h2>Bolt Search Report</h2><table><tr>")
                        for header in headers:
                            f.write(f"<th>{header}</th>")
                        f.write("</tr>")

                        for row in range(self.table_results.rowCount()):
                            f.write("<tr>")
                            for col in range(col_count):
                                f.write(f"<td>{self.table_results.item(row, col).text()}</td>")
                            f.write("</tr>")
                        f.write("</table></body></html>")

                    elif file_path.endswith('.json'):
                        import json
                        json_data = []
                        for row in range(self.table_results.rowCount()):
                            json_data.append({
                                headers[i]: self.table_results.item(row, i).text() for i in range(col_count)
                            })
                        json.dump(json_data, f, ensure_ascii=False, indent=4)
                    elif file_path.endswith('.csv'):
                        writer = csv.writer(f)
                        writer.writerow(headers)
                        for row in range(self.table_results.rowCount()):
                            writer.writerow([self.table_results.item(row, i).text() for i in range(col_count)])
                    else:
                        for row in range(self.table_results.rowCount()):
                            file_txt = self.table_results.item(row, 0).text()
                            line_txt = self.table_results.item(row, 1).text()
                            match_txt = self.table_results.item(row, 2).text()
                            score_txt = self.table_results.item(row, 6).text()
                            f.write(f"File: {file_txt}\nMatch: {match_txt} ({score_txt})\nContext: {line_txt}\n{'-'*40}\n")


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
                current_row = self.table_results.currentRow()
                if current_row >= 0:
                    self.show_context_dialog(current_row, 0)
                return True
        return super().eventFilter(source, event)

    def table_key_press_event(self, event):
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            current_row = self.table_results.currentRow()
            if current_row >= 0:
                self.show_context_dialog(current_row, 0)
        else:
            QTableWidget.keyPressEvent(self.table_results, event)

    def show_context_menu(self, pos):
        item = self.table_results.itemAt(pos)
        if not item:
            return

        row = item.row()
        file_item = self.table_results.item(row, 0)
        file_path = file_item.data(Qt.ItemDataRole.UserRole)

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
            self.show_context_dialog(row, 0)
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

    def on_cell_clicked(self, row, column):
        if column == 0:
            file_item = self.table_results.item(row, 0)
            file_path = file_item.data(Qt.ItemDataRole.UserRole)
            if file_path and os.path.exists(file_path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))

    def update_preview_pane(self):
        current_row = self.table_results.currentRow()
        if current_row < 0: return

        file_item = self.table_results.item(current_row, 0)
        file_path = file_item.data(Qt.ItemDataRole.UserRole)
        line_num = file_item.data(Qt.ItemDataRole.UserRole + 1)

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
            conn = sqlite3.connect(self.indexed_data)
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

                if is_html and not is_tg_export:
                    if is_target:
                        html_content.append(f"{anchor}<div style='padding:5px; border:1px solid #fdcb6e; background-color:#fef8e6;'>{text}</div>")
                    else:
                        html_content.append(text)
                else:
                    prefix_str = f"<span style='color:#b2bec3; font-size:10px; margin-right:10px;'>{ln}</span>"
                    if is_target:
                        # Light orange border to show it's the target line, but rely on yellow span for exact word
                        html_content.append(f"{anchor}<div style='padding:5px; margin:2px 0; border-left:4px solid #f39c12; background-color:#fafafa; font-size:14px; font-family:sans-serif;'>{prefix_str} {display_text}</div>")
                    else:
                        html_content.append(f"<div style='padding:2px; margin:1px 0; font-size:14px; font-family:sans-serif; border-bottom:1px solid #f1f2f6;'>{prefix_str} {display_text}</div>")

            if is_html and not is_tg_export:
                return " ".join(html_content)
            else:
                return "".join(html_content)
        return None


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

        from PyQt6.QtWidgets import QTextBrowser
        text_edit = QTextBrowser()
        text_edit.setReadOnly(True)

        # Handle HTML and CSV styling
        is_html = file_path.endswith('.html') or file_path.endswith('.htm')

        html_content = []

        # Load all lines from DB to display full text
        lines = self.fetch_lines_from_db(file_path)

        if lines:
            for line_data in lines:
                ln = line_data[0]
                text = line_data[1]
                words = json.loads(line_data[2]) if len(line_data)>2 and line_data[2] else []

                prefix = f"<b>{ln}:</b> " if not is_html else ""

                # Basic escaping if not HTML to prevent parsing bugs
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

                if ln == highlight_line_num:
                    if is_html:
                        html_content.append(f"<a name='target'></a><div style='padding:5px; border-radius:3px; background-color:#fef8e6;'>{display_text}</div>")
                    else:
                        html_content.append(f"<a name='target'></a><span>{prefix}{display_text}</span>")
                else:
                    if is_html:
                        html_content.append(display_text)
                    else:
                        html_content.append(f"{prefix}{display_text}")

        if is_html:
            # Wrap all HTML lines so it renders properly in Qt
            full_html = " ".join(html_content)
            text_edit.setHtml(full_html)
        else:
            text_edit.setHtml("<br>".join(html_content))
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
                words = json.loads(line_data[2]) if len(line_data)>2 and line_data[2] else []
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
