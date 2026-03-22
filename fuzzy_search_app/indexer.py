import os
import re
from pathlib import Path
from bs4 import BeautifulSoup
try:
    import lxml
except ImportError:
    pass
import docx
import concurrent.futures
from PIL import Image
import datetime
import time
import pickle
import zipfile
import tempfile
import hashlib
import sqlite3
import json
from bs4 import SoupStrainer

# ⚡ BOLT PRECOMPILED REGEX: Don't compile this for every single line of text!
TOKEN_PATTERN = re.compile(r'\w+')

def tokenize_line(line):
    return TOKEN_PATTERN.findall(line)



import csv


def parse_zip(file_path):
    lines = []
    try:
        with zipfile.ZipFile(file_path, 'r') as z:
            for zip_info in z.infolist():
                if zip_info.is_dir(): continue
                ext = os.path.splitext(zip_info.filename)[1].lower()

                # Only read text-based files from zip to prevent huge unzipping costs
                if ext in ['.txt', '.csv']:
                    with z.open(zip_info) as f:
                        content = f.read().decode('utf-8', errors='ignore')
                        line_num = 1
                        for line in content.split('\n'):
                            clean_line = line.strip()
                            # Prepend filename so user knows which zip file it's from
                            full_line = f"[{zip_info.filename}] {clean_line}"
                            lines.append((line_num, full_line, tokenize_line(clean_line) if clean_line else [], ''))
                            line_num += 1
    except Exception:
        pass
    return lines

def parse_csv(file_path):
    lines = []
    encodings = ['utf-8', 'cp1251', 'cp866', 'latin-1']
    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc, newline='') as f:
                reader = csv.reader(f)
                for line_num, row in enumerate(reader, 1):
                    clean_line = " | ".join(row).strip()
                    lines.append((line_num, clean_line, tokenize_line(clean_line) if clean_line else [], "", ""))
            break # Success
        except UnicodeDecodeError:
            lines = [] # Clear and try next
        except Exception:
            break
    return lines


def parse_image(file_path):
    lines = []
    try:
        import pytesseract
        text = pytesseract.image_to_string(Image.open(file_path), lang='eng+rus')
        for line_num, line in enumerate(text.split('\n'), 1):
            clean_line = line.strip()
            lines.append((line_num, clean_line, tokenize_line(clean_line) if clean_line else [], ""))
    except Exception as e:
        pass # Ignore if tesseract isn't installed
    return lines

def parse_txt(file_path):
    lines = []
    encodings = ['utf-8', 'cp1251', 'cp866', 'latin-1']
    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                for line_num, line in enumerate(f, 1):
                    clean_line = line.strip()
                    lines.append((line_num, clean_line, tokenize_line(clean_line) if clean_line else [], "", ""))
            break # Successfully read, stop trying encodings
        except UnicodeDecodeError:
            lines = [] # Clear any partial reads and try next encoding
        except Exception:
            break
    return lines

def parse_html(file_path):
    lines = []
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            # ⚡ BOLT MEMORY OPTIMIZATION: Only parse relevant HTML sections
            # This uses SoupStrainer to throw away 90% of massive Telegram HTML files (headers, styles, empty layout divs)
            # before they are even built into BeautifulSoup's DOM memory tree.
            strainer = SoupStrainer('div', class_='message')
            soup = BeautifulSoup(f, 'lxml', parse_only=strainer)

            messages = soup.find_all('div', class_='message')
            if messages:
                line_num = 1
                last_sender = "Unknown"

                for msg in messages:
                    # 1. Скрытие сервисных сообщений (Service messages)
                    if 'service' in msg.get('class', []):
                        continue

                    sender_div = msg.find('div', class_='from_name')
                    text_div = msg.find('div', class_='text')
                    date_div = msg.find('div', class_='date')

                    # 2. Парсинг Ответов (Replies) и Пересланных (Forwards)
                    reply_div = msg.find('div', class_='reply_to')
                    forward_div = msg.find('div', class_='forwarded')

                    # 3. Парсинг Медиа (Фото, Видео, Голосовые)
                    media_wrap = msg.find('div', class_='media_wrap')
                    media_text = ""
                    if media_wrap:
                        if media_wrap.find(class_='photo'): media_text = "[📷 Фото] "
                        elif media_wrap.find(class_='video'): media_text = "[📹 Видео] "
                        elif media_wrap.find(class_='voice_message'): media_text = "[🎤 Голосовое] "
                        elif msg.find(class_='sticker'): media_text = "[😊 Стикер] "
                        else: media_text = "[📎 Медиа] "

                    # Some messages only have media and no text_div
                    if text_div or media_text:
                        if sender_div:
                            sender = sender_div.get_text(strip=True)
                            # ⚡ BOLT FEATURE: Advanced Nickname System
                            sender = " ".join(sender.split())
                            if not sender:
                                sender = "Unknown"
                            last_sender = sender
                        else:
                            sender = last_sender

                        # Extract text
                        text = text_div.get_text(separator=' ', strip=True) if text_div else ""

                        # Combine text with media tag
                        full_text = media_text + text

                        # Add forward/reply context if exists
                        if reply_div:
                            reply_name = reply_div.find(class_='details')
                            if reply_name:
                                full_text = f"[↩️ Ответ: {reply_name.get_text(strip=True)}] {full_text}"
                        if forward_div:
                            fwd_name = forward_div.find(class_='from_name')
                            if fwd_name:
                                full_text = f"[↪️ Переслано от: {fwd_name.get_text(strip=True)}] {full_text}"

                        raw_date = date_div.get('title') if date_div else ""
                        parsed_date = ""
                        if raw_date:
                            # ⚡ BOLT FAST PATH: O(1) string slicing instead of expensive datetime.strptime inside huge loops
                            # Telegram format: DD.MM.YYYY HH:MM:SS or DD.MM.YYYY HH:MM
                            if len(raw_date) >= 10 and raw_date[2] == '.' and raw_date[5] == '.':
                                day = raw_date[0:2]
                                month = raw_date[3:5]
                                year = raw_date[6:10]
                                time_part = raw_date[11:] if len(raw_date) > 10 else "00:00:00"
                                if len(time_part) == 5: # HH:MM
                                    time_part += ":00"
                                parsed_date = f"{year}-{month}-{day} {time_part}"
                            else:
                                parsed_date = raw_date

                        clean_line = f"[{sender}] {full_text}"

                        # Append 5 items: line_num, formatted text, tokens, ISO date, author name
                        # We strictly enforce ISO string sorting (YYYY-MM-DD HH:MM:SS) which sorts lexicographically perfectly
                        lines.append((line_num, clean_line, tokenize_line(clean_line), parsed_date, sender))
                        line_num += 1
            else:
                # Standard HTML fallback (re-read file entirely since strainer filtered it out)
                f.seek(0)
                full_soup = BeautifulSoup(f, 'lxml')
                text = full_soup.get_text(separator='\n')
                for line_num, line in enumerate(text.split('\n'), 1):
                    clean_line = line.strip()
                    lines.append((line_num, clean_line, tokenize_line(clean_line) if clean_line else [], "", ""))
    except Exception as e:
        print("HTML Parse Error:", e)
    return lines

def parse_docx(file_path):
    lines = []
    try:
        doc = docx.Document(file_path)
        for line_num, para in enumerate(doc.paragraphs, 1):
            clean_line = para.text.strip()
            lines.append((line_num, clean_line, tokenize_line(clean_line) if clean_line else [], ""))
    except Exception:
        pass
    return lines

def parse_pdf(file_path):
    lines = []
    try:
        import fitz # PyMuPDF
        doc = fitz.open(file_path)
        line_num = 1
        for page in doc:
            text = page.get_text("text")
            for line in text.split('\n'):
                clean_line = line.strip()
                lines.append((line_num, clean_line, tokenize_line(clean_line) if clean_line else [], ""))
                line_num += 1
    except Exception as e:
        print(f"Error reading PDF {file_path}: {e}")
    return lines

def process_file(file_info):
    file_path, ext, size_kb, mod_time = file_info
    supported_extensions = {
        '.txt': parse_txt,
        '.html': parse_html,
        '.htm': parse_html,
        '.docx': parse_docx,
        '.csv': parse_csv,
        '.png': parse_image,
        '.jpg': parse_image,
        '.jpeg': parse_image,
        '.zip': parse_zip,
        '.pdf': parse_pdf
    }

    parser_func = supported_extensions.get(ext)
    if parser_func:
        try:
            lines = parser_func(file_path)
            if lines:
                # We also add the filename itself as line 0 so it can be searched
                file_name = os.path.basename(file_path)
                lines.insert(0, (0, f"[FILENAME] {file_name}", tokenize_line(file_name), "", "System"))

                return file_path, {"lines": lines, "size_kb": size_kb, "mod_time": mod_time}
        except Exception as e:
            # ⚡ BOLT V3 CRASH PREVENTION: Never let a single corrupt file crash the ThreadPoolExecutor
            print(f"Skipping corrupt or unreadable file: {file_path}. Error: {e}")
            pass
    return None, None

def fast_scandir(folder):
    """Recursively yield (path, ext, size_kb, mod_time) using fast os.scandir."""
    try:
        with os.scandir(folder) as it:
            for entry in it:
                if entry.is_symlink():
                    continue
                if entry.is_dir():
                    yield from fast_scandir(entry.path)
                else:
                    try:
                        stat = entry.stat()
                        size_kb = max(1, stat.st_size // 1024)
                        mod_time = datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                        ext = os.path.splitext(entry.name)[1].lower()
                        yield (entry.path, ext, size_kb, mod_time)
                    except OSError:
                        pass
    except OSError:
        pass

def index_folder(folder_path, progress_callback=None):
    indexed_data = {}
    supported_extensions = {'.txt', '.html', '.htm', '.docx', '.pdf', '.csv', '.png', '.jpg', '.jpeg', '.zip'}

    files_to_process = []
    # ⚡ BOLT I/O OPTIMIZATION: Use fast os.scandir instead of os.walk to retrieve metadata and paths simultaneously
    for path, ext, size_kb, mod_time in fast_scandir(folder_path):
        if ext in supported_extensions:
            files_to_process.append((path, ext, size_kb, mod_time))

    # ⚡ BOLT ENGINE V2: C++ SQLite Core Database Migration
    app_data_dir = os.path.join(os.path.expanduser("~"), ".telesearch_cache")
    if not os.path.exists(app_data_dir):
        os.makedirs(app_data_dir)

    folder_hash = hashlib.md5(folder_path.encode('utf-8')).hexdigest()
    db_file = os.path.join(app_data_dir, f"{folder_hash}.db")

    # Connect to SQLite
    # ⚡ BOLT V3: Add 15 second timeout to prevent 'database is locked' errors during simultaneous reads
    conn = sqlite3.connect(db_file, timeout=15.0)
    cursor = conn.cursor()

    # ⚡ PRAGMA TUNING FOR MASSIVE SPEED
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.execute("PRAGMA temp_store = MEMORY")

    # Create Tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            file_path TEXT UNIQUE,
            size_kb INTEGER,
            mod_time TEXT,
            last_indexed REAL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lines (
            id INTEGER PRIMARY KEY,
            file_id INTEGER,
            line_num INTEGER,
            line_text TEXT,
            words_json TEXT,
            msg_date TEXT,
            author TEXT,
            FOREIGN KEY(file_id) REFERENCES files(id)
        )
    """)

    # FTS5 Virtual Table for Instant Search
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS fts_lines USING fts5(
            line_text,
            author,
            content='lines',
            content_rowid='id'
        )
    """)

    conn.commit()

    # Check what needs indexing
    folder_mtime = os.path.getmtime(folder_path) if os.path.exists(folder_path) else time.time()

    # We will just do a fresh DB for now to guarantee structural integrity of the V2 migration,
    # but normally we'd check timestamps against `last_indexed`.
    # To keep it bulletproof, if the DB exists and the folder hasn't changed, we skip indexing.
    needs_indexing = True
    try:
        db_mtime = os.path.getmtime(db_file)
        if db_mtime > folder_mtime:
            cursor.execute("SELECT COUNT(*) FROM files")
            if cursor.fetchone()[0] > 0:
                needs_indexing = False
    except OSError:
        pass

    total_files = len(files_to_process)

    if needs_indexing:
        if progress_callback:
            progress_callback(0, total_files, False)

        # Clear old data to prevent duplication during a fresh re-index
        cursor.execute("DELETE FROM files")
        cursor.execute("DELETE FROM lines")
        cursor.execute("DELETE FROM fts_lines")
        conn.commit()

        processed_files = 0
        current_time = time.time()

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_file = {executor.submit(process_file, file_info): file_info for file_info in files_to_process}
            for future in concurrent.futures.as_completed(future_to_file):
                file_path, file_data = future.result()
                processed_files += 1
                if progress_callback:
                    progress_callback(processed_files, total_files)

                if file_path and file_data:
                    # Insert File
                    cursor.execute("""
                        INSERT INTO files (file_path, size_kb, mod_time, last_indexed)
                        VALUES (?, ?, ?, ?)
                    """, (file_path, file_data['size_kb'], file_data['mod_time'], current_time))

                    file_id = cursor.lastrowid

                    # Insert Lines
                    lines_to_insert = []
                    fts_lines_to_insert = []

                    for line_tuple in file_data['lines']:
                        # line_tuple format: (line_num, line_text, words_list, msg_date, author)
                        # Ensure we always have 5 elements
                        lt = list(line_tuple)
                        while len(lt) < 5:
                            lt.append("")

                        line_num, line_text, words_list, msg_date, author = lt[:5]
                        words_json = json.dumps(words_list)

                        lines_to_insert.append((file_id, line_num, line_text, words_json, msg_date, author))

                    cursor.executemany("""
                        INSERT INTO lines (file_id, line_num, line_text, words_json, msg_date, author)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, lines_to_insert)

                    # We must trigger the FTS5 table updates manually when using external content
                    # But since we use simple FTS5 without external content syncing triggers, we insert directly
                    # Actually, using content='lines' requires triggers. Let's just create a standard FTS table for simplicity and max speed.
                    # Wait, we already created the table. Let's recreate it cleanly without external content to avoid trigger complexities.

        # Build the FTS5 index directly from the populated lines table
        cursor.execute("DROP TABLE IF EXISTS fts_lines")
        cursor.execute("""
            CREATE VIRTUAL TABLE fts_lines USING fts5(
                line_text,
                author
            )
        """)
        cursor.execute("""
            INSERT INTO fts_lines(rowid, line_text, author)
            SELECT id, line_text, author FROM lines
        """)
        conn.commit()
    else:
        if progress_callback:
            progress_callback(total_files, total_files, True)

    conn.close()

    # Return the db_file path instead of the giant dictionary.
    # Searcher will connect to this SQLite DB.
    return db_file
