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

def tokenize_line(line):
    return re.findall(r'\w+', line)



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
            # ⚡ TELESEARCH PRO: Use lxml for 10x faster parsing of massive Telegram exports
            soup = BeautifulSoup(f, 'lxml')

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
                        timestamp = 0.0
                        if raw_date:
                            try:
                                import datetime
                                dt = datetime.datetime.strptime(raw_date, "%d.%m.%Y %H:%M:%S")
                                parsed_date = dt.strftime("%Y-%m-%d %H:%M:%S")
                                timestamp = dt.timestamp()
                            except ValueError:
                                try:
                                    dt = datetime.datetime.strptime(raw_date, "%d.%m.%Y %H:%M")
                                    parsed_date = dt.strftime("%Y-%m-%d %H:%M:%S")
                                    timestamp = dt.timestamp()
                                except ValueError:
                                    parsed_date = raw_date
                                    timestamp = 0.0

                        clean_line = f"[{sender}] {full_text}"

                        # Append 5 items: line_num, formatted text, tokens, ISO date, author name
                        # Since we want mathematical sorting, we will pass timestamp via ISO string format which sorts lexicographically perfectly
                        # But wait, ISO format "YYYY-MM-DD" sorts perfectly as string! The problem was the user's date was "DD.MM.YYYY"
                        # This happens if the parsed_date fallback hit or the strftime failed.
                        # We will strictly enforce ISO string sorting.
                        lines.append((line_num, clean_line, tokenize_line(clean_line), parsed_date, sender))
                        line_num += 1
            else:
                # Standard HTML fallback
                text = soup.get_text(separator='\n')
                for line_num, line in enumerate(text.split('\n'), 1):
                    clean_line = line.strip()
                    lines.append((line_num, clean_line, tokenize_line(clean_line) if clean_line else [], "", ""))
    except Exception as e:
        print("HTML Parse Error:", e)
    return lines

def parse_docx(file_path):
    lines = []
    try:
        import zipfile
        # Often corrupted docx will fail in python-docx, try to catch zip errors
        try:
            zipfile.ZipFile(file_path).testzip()
        except zipfile.BadZipFile:
            return lines

        doc = docx.Document(file_path)
        for line_num, para in enumerate(doc.paragraphs, 1):
            try:
                clean_line = para.text.strip()
                lines.append((line_num, clean_line, tokenize_line(clean_line) if clean_line else [], ""))
            except Exception:
                pass
    except Exception:
        pass
    return lines

def parse_pdf(file_path):
    lines = []
    try:
        import fitz # PyMuPDF
        with fitz.open(file_path) as doc:
            line_num = 1
            for page in doc:
                try:
                    text = page.get_text("text")
                    for line in text.split('\n'):
                        clean_line = line.strip()
                        lines.append((line_num, clean_line, tokenize_line(clean_line) if clean_line else [], ""))
                        line_num += 1
                except Exception:
                    pass # Ignore unreadable pages
    except Exception as e:
        pass
    return lines

def process_file(file_path, ext):
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
            stat = os.stat(file_path)
            size_kb = max(1, stat.st_size // 1024)
            mod_time = datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            size_kb = 0
            mod_time = ""

        lines = parser_func(file_path)
        if lines:
            # We also add the filename itself as line 0 so it can be searched
            file_name = os.path.basename(file_path)
            lines.insert(0, (0, f"[FILENAME] {file_name}", tokenize_line(file_name), "", "System"))

            return file_path, {"lines": lines, "size_kb": size_kb, "mod_time": mod_time}
    return None, None

def index_folder(folder_path, progress_callback=None):
    indexed_data = {}
    supported_extensions = ['.txt', '.html', '.htm', '.docx', '.pdf', '.csv', '.png', '.jpg', '.jpeg', '.zip']

    files_to_process = []
    for root, _, files in os.walk(folder_path):
        for file in files:
            ext = Path(file).suffix.lower()
            if ext in supported_extensions:
                files_to_process.append((os.path.join(root, file), ext))

    # ⚡ BOLT OPTIMIZATION: Secure Disk Caching via SQLite (FTS5)
    app_data_dir = os.path.join(os.path.expanduser("~"), ".telesearch_cache")
    if not os.path.exists(app_data_dir):
        os.makedirs(app_data_dir)

    folder_hash = hashlib.md5(folder_path.encode('utf-8')).hexdigest()
    db_file = os.path.join(app_data_dir, f"{folder_hash}.db")

    # We will still return `indexed_data` dict for compatibility in parts of main.py,
    # but the primary search engine will use the db. We can populate indexed_data with just
    # file metadata, not the heavy lines arrays, to save RAM. Wait, for full transition, we will
    # return the db_file path to the SearchWorker instead of `indexed_data`.
    # Let's adjust main.py to handle db_file instead of dict. For now, let's build the db.

    conn = sqlite3.connect(db_file, timeout=15.0)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')

    # Check if DB exists and is fresh
    db_fresh = False
    try:
        conn.execute('SELECT 1 FROM files LIMIT 1')
        folder_mtime = os.path.getmtime(folder_path)
        db_mtime = os.path.getmtime(db_file)
        if db_mtime > folder_mtime:
            db_fresh = True
    except sqlite3.OperationalError:
        pass

    if db_fresh:
        if progress_callback:
            progress_callback(len(files_to_process), len(files_to_process), True)
        conn.close()
        return db_file

    conn.execute('DROP TABLE IF EXISTS lines')
    conn.execute('DROP TABLE IF EXISTS files')
    conn.execute('DROP TABLE IF EXISTS lines_fts')

    conn.execute('''
        CREATE TABLE files (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE,
            size_kb INTEGER,
            mod_time TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE lines (
            id INTEGER PRIMARY KEY,
            file_id INTEGER,
            line_num INTEGER,
            line_text TEXT,
            words_json TEXT,
            msg_date TEXT,
            author TEXT,
            FOREIGN KEY(file_id) REFERENCES files(id)
        )
    ''')
    conn.execute('''
        CREATE VIRTUAL TABLE lines_fts USING fts5(
            line_text,
            author,
            content='lines',
            content_rowid='id'
        )
    ''')

    total_files = len(files_to_process)
    if progress_callback:
        progress_callback(0, total_files, False)

    processed_files = 0

    # We serialize inserts to avoid DB locks, but process files in parallel
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_file = {executor.submit(process_file, fp, ext): fp for fp, ext in files_to_process}
        for future in concurrent.futures.as_completed(future_to_file):
            file_path, file_meta = future.result()
            processed_files += 1

            if file_path and file_meta:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO files (path, size_kb, mod_time) VALUES (?, ?, ?)',
                               (file_path, file_meta['size_kb'], file_meta['mod_time']))
                file_id = cursor.lastrowid

                lines_data = []
                for line_data in file_meta['lines']:
                    if len(line_data) >= 5:
                        l_num, l_text, words, msg_date, author = line_data[:5]
                    elif len(line_data) == 4:
                        l_num, l_text, words, msg_date = line_data
                        author = ""
                    else:
                        l_num, l_text, words = line_data
                        msg_date = ""
                        author = ""

                    lines_data.append((file_id, l_num, l_text, json.dumps(words), msg_date, author))

                cursor.executemany('INSERT INTO lines (file_id, line_num, line_text, words_json, msg_date, author) VALUES (?, ?, ?, ?, ?, ?)', lines_data)

                # Update FTS
                cursor.executemany('INSERT INTO lines_fts (rowid, line_text, author) VALUES (last_insert_rowid() - ? + 1, ?, ?)',
                                   [(len(lines_data) - i, row[2], row[5]) for i, row in enumerate(lines_data)])

                conn.commit()

            if progress_callback:
                progress_callback(processed_files, total_files)

    conn.close()
    return db_file
