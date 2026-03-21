import os
import re
from pathlib import Path
from bs4 import BeautifulSoup
import docx

def parse_txt(file_path):
    lines = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                clean_line = line.strip()
                if clean_line:
                    lines.append((line_num, clean_line))
    except UnicodeDecodeError:
        # Fallback if not utf-8
        try:
            with open(file_path, 'r', encoding='cp1251') as f:
                for line_num, line in enumerate(f, 1):
                    clean_line = line.strip()
                    if clean_line:
                        lines.append((line_num, clean_line))
        except Exception as e:
            print(f"Error parsing txt {file_path}: {e}")
    except Exception as e:
        print(f"Error parsing txt {file_path}: {e}")
    return lines

def parse_html(file_path):
    lines = []
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            soup = BeautifulSoup(f, 'html.parser')
            # get text and split by newlines, cleaning up empty space
            text = soup.get_text(separator='\n')
            for line_num, line in enumerate(text.split('\n'), 1):
                clean_line = line.strip()
                if clean_line:
                    lines.append((line_num, clean_line))
    except Exception as e:
        print(f"Error parsing html {file_path}: {e}")
    return lines

def parse_docx(file_path):
    lines = []
    try:
        doc = docx.Document(file_path)
        for line_num, para in enumerate(doc.paragraphs, 1):
            clean_line = para.text.strip()
            if clean_line:
                lines.append((line_num, clean_line))
    except Exception as e:
        print(f"Error parsing docx {file_path}: {e}")
    return lines

def index_folder(folder_path):
    """
    Scans a folder and its subfolders for supported files.
    Returns a dictionary mapping file paths to their parsed lines.
    { "path/to/file.txt": [(1, "Hello world"), (2, "Another line")], ... }
    """
    indexed_data = {}
    supported_extensions = {
        '.txt': parse_txt,
        '.html': parse_html,
        '.htm': parse_html,
        '.docx': parse_docx
    }

    for root, _, files in os.walk(folder_path):
        for file in files:
            ext = Path(file).suffix.lower()
            if ext in supported_extensions:
                file_path = os.path.join(root, file)
                parser_func = supported_extensions[ext]
                lines = parser_func(file_path)
                if lines:
                    indexed_data[file_path] = lines

    return indexed_data
