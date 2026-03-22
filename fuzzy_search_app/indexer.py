import os
import re
from pathlib import Path
from bs4 import BeautifulSoup
import docx
import concurrent.futures

def tokenize_line(line):
    return re.findall(r'\w+', line)



import csv

def parse_csv(file_path):
    lines = []
    try:
        with open(file_path, 'r', encoding='utf-8', newline='') as f:
            reader = csv.reader(f)
            for line_num, row in enumerate(reader, 1):
                clean_line = " | ".join(row).strip()
                if clean_line:
                    lines.append((line_num, clean_line, tokenize_line(clean_line)))
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='cp1251', newline='') as f:
                reader = csv.reader(f)
                for line_num, row in enumerate(reader, 1):
                    clean_line = " | ".join(row).strip()
                    if clean_line:
                        lines.append((line_num, clean_line, tokenize_line(clean_line)))
        except Exception:
            pass
    except Exception:
        pass
    return lines

def parse_txt(file_path):
    lines = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                clean_line = line.strip()
                if clean_line:
                    lines.append((line_num, clean_line, tokenize_line(clean_line)))
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='cp1251') as f:
                for line_num, line in enumerate(f, 1):
                    clean_line = line.strip()
                    if clean_line:
                        lines.append((line_num, clean_line, tokenize_line(clean_line)))
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
            text = soup.get_text(separator='\n')
            for line_num, line in enumerate(text.split('\n'), 1):
                clean_line = line.strip()
                if clean_line:
                    lines.append((line_num, clean_line, tokenize_line(clean_line)))
    except Exception:
        pass
    return lines

def parse_docx(file_path):
    lines = []
    try:
        doc = docx.Document(file_path)
        for line_num, para in enumerate(doc.paragraphs, 1):
            clean_line = para.text.strip()
            if clean_line:
                lines.append((line_num, clean_line, tokenize_line(clean_line)))
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
                if clean_line:
                    lines.append((line_num, clean_line, tokenize_line(clean_line)))
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
        '.pdf': parse_pdf
    }

    parser_func = supported_extensions.get(ext)
    if parser_func:
        lines = parser_func(file_path)
        if lines:
            return file_path, lines
    return None, None

def index_folder(folder_path, progress_callback=None):
    indexed_data = {}
    supported_extensions = ['.txt', '.html', '.htm', '.docx', '.pdf', '.csv']

    files_to_process = []
    for root, _, files in os.walk(folder_path):
        for file in files:
            ext = Path(file).suffix.lower()
            if ext in supported_extensions:
                files_to_process.append((os.path.join(root, file), ext))

    total_files = len(files_to_process)
    if progress_callback:
        progress_callback(0, total_files)

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

    return indexed_data
