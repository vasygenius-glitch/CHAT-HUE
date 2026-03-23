import time
import concurrent.futures
from rapidfuzz import fuzz
import re
import sqlite3
import json

def regexp(expr, item):
    if item is None:
        return False
    try:
        reg = re.compile(expr, re.IGNORECASE)
        return reg.search(item) is not None
    except Exception:
        return False

def parse_search_syntax(search_term):
    # Extracts tokens like +required, -excluded, "exact phrase", and normal words
    import shlex
    try:
        tokens = shlex.split(search_term)
    except ValueError:
        tokens = search_term.split()

    required = []
    excluded = []
    normal = []

    for token in tokens:
        if token.startswith('+') and len(token) > 1:
            required.append(token[1:])
        elif token.startswith('-') and len(token) > 1:
            excluded.append(token[1:])
        else:
            normal.append(token)

    return required, excluded, normal

def search_chunk_db(db_file, search_term, accuracy_threshold, exact_match, regex_match, case_sensitive, author_filter, file_filter_exts, date_from, date_to, size_from, size_to, offset, limit):
    results = []

    conn = sqlite3.connect(db_file, timeout=15.0)
    conn.create_function('REGEXP', 2, regexp)
    conn.execute('PRAGMA query_only = ON')

    query_parts = []
    params = []

    base_query = '''
        SELECT f.path, f.size_kb, f.mod_time, l.line_num, l.line_text, l.words_json, l.msg_date, l.author
        FROM lines l
        JOIN files f ON l.file_id = f.id
    '''

    where_clauses = []

    if file_filter_exts:
        # Just use LIKE for simplicity since sqlite doesn't easily substring dynamically in IN
        ext_clauses = " OR ".join([f"f.path LIKE ?" for _ in file_filter_exts])
        where_clauses.append(f"({ext_clauses})")
        params.extend([f"%{ext}" for ext in file_filter_exts])

    if author_filter:
        where_clauses.append("l.author LIKE ?")
        params.append(f"%{author_filter}%")

    if size_from is not None:
        where_clauses.append("f.size_kb >= ?")
        params.append(size_from)

    if size_to is not None:
        where_clauses.append("f.size_kb <= ?")
        params.append(size_to)

    if date_from:
        where_clauses.append("f.mod_time >= ?")
        params.append(date_from)

    if date_to:
        where_clauses.append("f.mod_time <= ?")
        params.append(date_to)

    req_terms, exc_terms, norm_terms = [], [], []

    if exact_match:
        if case_sensitive:
            where_clauses.append("l.line_text LIKE ?")
            params.append(f"%{search_term}%")
        else:
            where_clauses.append("lower(l.line_text) LIKE ?")
            params.append(f"%{search_term.lower()}%")
    elif regex_match:
        where_clauses.append("l.line_text REGEXP ?")
        params.append(search_term)
    else:
        # Advanced Syntax Parser
        req_terms, exc_terms, norm_terms = parse_search_syntax(search_term)

        for req in req_terms:
            where_clauses.append("lower(l.line_text) LIKE ?")
            params.append(f"%{req.lower()}%")

        for exc in exc_terms:
            where_clauses.append("lower(l.line_text) NOT LIKE ?")
            params.append(f"%{exc.lower()}%")

        if norm_terms:
            norm_clause = " OR ".join(["lower(l.line_text) LIKE ?" for _ in norm_terms])
            where_clauses.append(f"({norm_clause})")
            params.extend([f"%{t.lower()}%" for t in norm_terms])

    if where_clauses:
        base_query += " WHERE " + " AND ".join(where_clauses)

    base_query += f" LIMIT {limit} OFFSET {offset}"

    cursor = conn.cursor()
    cursor.execute(base_query, params)

    search_term_processed = search_term if case_sensitive else search_term.lower()
    search_len = len(search_term_processed)

    for row in cursor.fetchall():
        path, size_kb, mod_time, line_num, line_text, words_json, msg_date, author = row

        best_match = None
        best_score = 0

        if regex_match:
            try:
                matches = re.findall(search_term, line_text, 0 if case_sensitive else re.IGNORECASE)
                if matches:
                    best_match = str(matches[0])
                    best_score = 100
            except:
                pass
        else:
            try:
                words = json.loads(words_json) if words_json else []
            except:
                words = []

            for word in words:
                word_proc = word if case_sensitive else word.lower()

                if exact_match:
                    if search_term_processed == word_proc:
                        score = 100
                        best_match = word
                    else:
                        continue
                else:
                    score = fuzz.WRatio(search_term_processed, word_proc)

                if not exact_match and search_term_processed in word_proc:
                    length_ratio = search_len / max(len(word_proc), 1)
                    if length_ratio >= 0.3:
                        score = max(score, 85 + (15 * length_ratio))

                if score > best_score:
                    best_score = score
                    best_match = word

        if best_score >= accuracy_threshold:
            final_date = msg_date if msg_date else mod_time
            if final_date and len(final_date.split('.')) == 3:
                try:
                    import datetime
                    dt = datetime.datetime.strptime(final_date, "%d.%m.%Y %H:%M")
                    final_date = dt.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass

            results.append({
                "file": path,
                "size_kb": size_kb,
                "mod_time": final_date,
                "line_num": line_num,
                "line": line_text,
                "match": best_match,
                "score": round(best_score, 2),
                "author": author
            })

    conn.close()
    return results

def perform_search(db_file, search_term, accuracy_threshold, exact_match=False, regex_match=False, case_sensitive=False, author_filter="", file_filter="Все файлы (*.*)", date_from=None, date_to=None, size_from=None, size_to=None):
    start_time = time.time()
    results = []

    # Check if we should fallback
    if isinstance(db_file, dict):
        return [], 0 # Backward compatibility not fully supported after massive change, but safely return empty

    file_filter_exts = []
    if file_filter != "Все файлы (*.*)":
        if file_filter.startswith("Только Изображения"):
            file_filter_exts = ['.png', '.jpg', '.jpeg']
        else:
            ext = file_filter.split("*")[-1].replace(")", "")
            file_filter_exts = [ext]

    # Count total lines to process in chunks
    conn = sqlite3.connect(db_file, timeout=15.0)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM lines')
    total_lines = cursor.fetchone()[0]
    conn.close()

    chunk_size = 50000
    offsets = range(0, total_lines, chunk_size)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(search_chunk_db, db_file, search_term, accuracy_threshold, exact_match, regex_match, case_sensitive, author_filter, file_filter_exts, date_from, date_to, size_from, size_to, offset, chunk_size) for offset in offsets]
        for future in concurrent.futures.as_completed(futures):
            results.extend(future.result())

    results.sort(key=lambda x: x['score'], reverse=True)

    if len(results) > 1000:
        results = results[:1000]

    end_time = time.time()
    return results, round(end_time - start_time, 4)
