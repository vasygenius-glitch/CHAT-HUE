import os
import re
from pathlib import Path
from bs4 import BeautifulSoup
import docx
import concurrent.futures
from PIL import Image
import datetime
import time
import pickle
import zipfile
import tempfile
import hashlib

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
                            lines.append((line_num, full_line, tokenize_line(clean_line) if clean_line else []))
                            line_num += 1
    except Exception:
        pass
    return lines

def parse_csv(file_path):
    lines = []
    try:
        with open(file_path, 'r', encoding='utf-8', newline='') as f:
            reader = csv.reader(f)
            for line_num, row in enumerate(reader, 1):
                clean_line = " | ".join(row).strip()
                lines.append((line_num, clean_line, tokenize_line(clean_line) if clean_line else []))
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='cp1251', newline='') as f:
                reader = csv.reader(f)
                for line_num, row in enumerate(reader, 1):
                    clean_line = " | ".join(row).strip()
                    lines.append((line_num, clean_line, tokenize_line(clean_line) if clean_line else []))
        except Exception:
            pass
    except Exception:
        pass
    return lines


def parse_image(file_path):
    lines = []
    try:
        import pytesseract
        text = pytesseract.image_to_string(Image.open(file_path), lang='eng+rus')
        for line_num, line in enumerate(text.split('\n'), 1):
            clean_line = line.strip()
            lines.append((line_num, clean_line, tokenize_line(clean_line) if clean_line else []))
    except Exception as e:
        pass # Ignore if tesseract isn't installed
    return lines

def parse_txt(file_path):
    lines = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                clean_line = line.strip()
                lines.append((line_num, clean_line, tokenize_line(clean_line) if clean_line else []))
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='cp1251') as f:
                for line_num, line in enumerate(f, 1):
                    clean_line = line.strip()
                    lines.append((line_num, clean_line, tokenize_line(clean_line) if clean_line else []))
        except Exception:
            pass
    except Exception:
        pass
    return lines

def parse_html(file_path):
    lines = []
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            soup = BeautifulSoup(f, 'html.parser')

            # ⚡ BOLT FEATURE: Telegram Chat Export Support
            messages = soup.find_all('div', class_='message')
            if messages:
                line_num = 1
                last_sender = "Unknown"

                for msg in messages:
                    # Skip service messages like "Channel created"
                    if 'service' in msg.get('class', []):
                        continue

                    sender_div = msg.find('div', class_='from_name')
                    text_div = msg.find('div', class_='text')
                    date_div = msg.find('div', class_='date')

                    if text_div:
                        # Telegram omits from_name for consecutive messages from the same user
                        if sender_div:
                            sender = sender_div.get_text(strip=True)
                            last_sender = sender
                        else:
                            sender = last_sender

                        text = text_div.get_text(separator=' ', strip=True)
                        date = date_div.get('title') if date_div else ""

                        clean_line = f"[{sender}] {text}"
                        if date:
                            clean_line += f" ({date})"

                        lines.append((line_num, clean_line, tokenize_line(clean_line)))
                        line_num += 1
            else:
                # Standard HTML fallback
                text = soup.get_text(separator='\n')
                for line_num, line in enumerate(text.split('\n'), 1):
                    clean_line = line.strip()
                    lines.append((line_num, clean_line, tokenize_line(clean_line) if clean_line else []))
    except Exception:
        pass
    return lines

def parse_docx(file_path):
    lines = []
    try:
        doc = docx.Document(file_path)
        for line_num, para in enumerate(doc.paragraphs, 1):
            clean_line = para.text.strip()
            lines.append((line_num, clean_line, tokenize_line(clean_line) if clean_line else []))
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
                lines.append((line_num, clean_line, tokenize_line(clean_line) if clean_line else []))
                line_num += 1
    except Exception as e:
        print(f"Error reading PDF {file_path}: {e}")
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
            mod_time = datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
        except Exception:
            size_kb = 0
            mod_time = "Unknown"

        lines = parser_func(file_path)
        if lines:
            # We also add the filename itself as line 0 so it can be searched
            file_name = os.path.basename(file_path)
            lines.insert(0, (0, f"[FILENAME] {file_name}", tokenize_line(file_name)))

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

    # ⚡ BOLT OPTIMIZATION: Secure Disk Caching
    # We store the cache in the user's safe app data directory to prevent RCE from malicious folders
    app_data_dir = os.path.join(os.path.expanduser("~"), ".fuzzy_search_cache")
    if not os.path.exists(app_data_dir):
        os.makedirs(app_data_dir)

    folder_hash = hashlib.md5(folder_path.encode('utf-8')).hexdigest()
    cache_file = os.path.join(app_data_dir, f"{folder_hash}.pkl")
    cache_valid = False

    # Check if cache exists and is newer than the folder's last modification
    if os.path.exists(cache_file):
        try:
            folder_mtime = os.path.getmtime(folder_path)
            cache_mtime = os.path.getmtime(cache_file)

            # If cache is newer than the folder, we load it instantly
            if cache_mtime > folder_mtime:
                with open(cache_file, 'rb') as f:
                    indexed_data = pickle.load(f)
                cache_valid = True
                if progress_callback:
                    progress_callback(len(files_to_process), len(files_to_process), True) # True flag means loaded from cache
                return indexed_data
        except Exception:
            pass # Fallback to normal indexing if cache fails

    total_files = len(files_to_process)
    if progress_callback:
        progress_callback(0, total_files, False)

    processed_files = 0
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_file = {executor.submit(process_file, fp, ext): fp for fp, ext in files_to_process}
        for future in concurrent.futures.as_completed(future_to_file):
            file_path, lines = future.result()
            processed_files += 1
            if progress_callback:
                progress_callback(processed_files, total_files)
            if file_path and lines:
                indexed_data[file_path] = lines


    # Save to disk cache silently
    try:
        with open(cache_file, 'wb') as f:
            pickle.dump(indexed_data, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:
        pass

    return indexed_data
