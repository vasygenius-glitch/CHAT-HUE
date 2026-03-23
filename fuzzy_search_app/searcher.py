import time
import concurrent.futures
from rapidfuzz import fuzz
import re

# ⚡ BOLT MEMORY OPTIMIZATION: Cache global set once so GC doesn't thrash rebuilding this during consecutive searches.
STOP_WORDS = frozenset({"и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то", "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за", "бы", "по", "только", "ее", "мне", "было", "вот", "от", "меня", "еще", "нет", "о", "из", "ему", "теперь", "когда", "даже", "ну", "вдруг", "ли", "если", "уже", "или", "ни", "быть", "был", "него", "до", "вас", "нибудь", "опять", "уж", "вам", "ведь", "там", "потом", "себя", "ничего", "ей", "может", "они", "тут", "где", "есть", "надо", "ней", "для", "мы", "тебя", "их", "чем", "была", "сам", "чтоб", "без", "будто", "человек", "чего", "раз", "тоже", "себе", "под", "будет", "ж", "тогда", "кто", "этот", "того", "потому", "этого", "какой", "совсем", "ним", "здесь", "этом", "один", "почти", "мой", "тем", "чтобы", "нее", "сейчас", "были", "куда", "зачем", "всех", "никогда", "можно", "при", "наконец", "два", "об", "другой", "хоть", "после", "над", "больше", "тот", "через", "эти", "нас", "про", "всего", "них", "какая", "много", "разве", "три", "эту", "моя", "впрочем", "хорошо", "свою", "этой", "перед", "иногда", "лучше", "чуть", "том", "нельзя", "такой", "им", "более", "всегда", "конечно", "всю", "между", "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with", "by", "of"})

def search_chunk(file_paths_chunk, indexed_data, search_term_processed, search_len, accuracy_threshold, exact_match, regex_match=False, search_pattern=None, case_sensitive=False, author_filter=""):
    author_filter_proc = author_filter if case_sensitive else author_filter.lower()
    chunk_results = []
    for file_path in file_paths_chunk:
        file_metadata = indexed_data[file_path]
        lines = file_metadata.get("lines", []) if isinstance(file_metadata, dict) else file_metadata
        size_kb = file_metadata.get("size_kb", 0) if isinstance(file_metadata, dict) else 0
        mod_time = file_metadata.get("mod_time", "Unknown") if isinstance(file_metadata, dict) else "Unknown"

        for line_data in lines:
            if len(line_data) >= 5:
                line_num, line_text, words, msg_date, author = line_data[:5]
            elif len(line_data) == 4:
                line_num, line_text, words, msg_date = line_data
                author = ""
            else:
                line_num, line_text, words = line_data
                msg_date = ""
                author = ""

            # ⚡ FAST PATH: Author/Nickname Filter (O(1) line rejection)
            if author_filter_proc:
                # If author exists (e.g., Telegram export), use it. Otherwise, fallback to scanning the whole line text for txt/docx/pdf files.
                if author:
                    author_check = author if case_sensitive else author.lower()
                    if author_filter_proc not in author_check:
                        continue
                else:
                    line_check = line_text if case_sensitive else line_text.lower()
                    if author_filter_proc not in line_check:
                        continue

            best_match = None
            best_score = 0

            if regex_match and search_pattern:
                matches = search_pattern.findall(line_text)
                if matches:
                    best_match = str(matches[0])
                    best_score = 100
            else:
                for word in words:
                    word_proc = word if case_sensitive else word.lower()

                    if not exact_match and not case_sensitive and word_proc in STOP_WORDS:
                        continue

                    word_len = len(word_proc)

                    max_diff = max(3, int(search_len * 0.7))
                    if abs(word_len - search_len) > max_diff:
                        if search_term_processed not in word_proc:
                            continue

                    if word_len < 2 and search_len > 2:
                        continue

                    if exact_match:
                        if search_term_processed == word_proc:
                            score = 100
                        else:
                            continue
                    else:
                        # ⚡ BOLT C++ OPTIMIZATION: Early early abort algorithm natively in RapidFuzz!
                        # The function stops comparing immediately if it mathematically cannot reach accuracy_threshold.
                        score = fuzz.WRatio(search_term_processed, word_proc, score_cutoff=accuracy_threshold)
                        if score == 0:
                            # It got aborted or just didn't match. But wait! There is a manual substring boost below.
                            # So if there's a chance the substring boost could save it, we must still allow that check.
                            pass

                    if not exact_match and search_term_processed in word_proc:
                        length_ratio = search_len / max(word_len, 1)
                        if length_ratio >= 0.3:
                            score = max(score, 85 + (15 * length_ratio))

                    if score > best_score:
                        best_score = score
                        best_match = word

            if best_score >= accuracy_threshold:
                # We expect the indexer to already provide perfectly formatted ISO 8601 strings (YYYY-MM-DD HH:MM:SS)
                # Fallback to mod_time which is also pre-formatted as ISO 8601 string during index_folder
                final_date = msg_date if msg_date else mod_time

                chunk_results.append({
                    "file": file_path,
                    "size_kb": size_kb,
                    "mod_time": final_date,
                    "line_num": line_num,
                    "line": line_text,
                    "match": best_match,
                    "score": round(best_score, 2),
                    "author": author
                })
    return chunk_results

import sqlite3
import json
import os

def perform_search(db_path, search_term, accuracy_threshold, exact_match=False, regex_match=False, case_sensitive=False, author_filter="", date_from=None, date_to=None, size_min=None, size_max=None):
    start_time = time.time()
    results = []

    # ⚡ Puxxzz FF: Double Validation System, Length Threshold, Typos
    # Connect to SQLite
    conn = sqlite3.connect(db_path, timeout=30.0)
    # Enable REGEXP
    def regexp(expr, item):
        try:
            reg = re.compile(expr, re.IGNORECASE if not case_sensitive else 0)
            return reg.search(item) is not None
        except Exception:
            return False

    conn.create_function("REGEXP", 2, regexp)
    cursor = conn.cursor()

    search_term_processed = search_term if case_sensitive else search_term.lower()
    search_len = len(search_term_processed)

    # ⚡ BOLT V4 ENTERPRISE: Advanced Query Parser (Google-style Syntax)
    # Extracts exactly required words (+word), excluded words (-word), and exact phrases ("multi word")
    where_clauses = []
    params = []

    required_words = []
    excluded_words = []
    exact_phrases = []
    base_search_terms = []

    if exact_match and not regex_match:
        # If the GUI exact match checkbox is used, force the whole string into an exact phrase
        exact_phrases.append(search_term)
        base_search_terms.append(search_term)
    elif regex_match:
        where_clauses.append("l.line_text REGEXP ?")
        params.append(search_term)
        base_search_terms.append(search_term)
    else:
        # Parse Syntax
        import shlex
        try:
            tokens = shlex.split(search_term)
        except ValueError:
            tokens = search_term.split() # Fallback if quotes are mismatched

        for token in tokens:
            if token.startswith('+') and len(token) > 1:
                required_words.append(token[1:])
                base_search_terms.append(token[1:])
            elif token.startswith('-') and len(token) > 1:
                excluded_words.append(token[1:])
            elif " " in token:
                exact_phrases.append(token)
                base_search_terms.append(token)
            else:
                base_search_terms.append(token)

    # Compile the final search target for Python hybrid fuzzing down below
    # If the user typed complex queries, we only fuzz the primary words.
    final_hybrid_fuzz_target = " ".join(base_search_terms) if base_search_terms else search_term

    # ⚡ BOLT V4 SYNTAX FIX: If base_search_terms is empty (e.g. only "+word -word"), we must evaluate against the required word.
    if not base_search_terms and required_words:
        final_hybrid_fuzz_target = " ".join(required_words)

    search_term_processed = final_hybrid_fuzz_target if case_sensitive else final_hybrid_fuzz_target.lower()

    search_len = len(search_term_processed)

    # ⚡ BOLT V2: Intelligent Author SQL Filtering
    if author_filter:
        if case_sensitive:
            where_clauses.append("(l.author LIKE ? OR (l.author = '' AND l.line_text LIKE ?))")
            params.extend([f"%{author_filter}%", f"%{author_filter}%"])
        else:
            where_clauses.append("(LOWER(l.author) LIKE ? OR (l.author = '' AND LOWER(l.line_text) LIKE ?))")
            params.extend([f"%{author_filter.lower()}%", f"%{author_filter.lower()}%"])

    # ⚡ Puxxzz FF: Functional Size & Date Filtering Execution
    # Ensure they are safely appended and executed.
    if size_min is not None and int(size_min) > 0:
        where_clauses.append("f.size_kb >= ?")
        params.append(int(size_min))
    if size_max is not None and int(size_max) > 0:
        where_clauses.append("f.size_kb <= ?")
        params.append(int(size_max))

    if date_from:
        where_clauses.append("substr(IFNULL(l.msg_date, f.mod_time), 1, 10) >= ?")
        params.append(date_from)
    if date_to:
        where_clauses.append("substr(IFNULL(l.msg_date, f.mod_time), 1, 10) <= ?")
        params.append(date_to)

    # ⚡ BOLT V4: Apply Syntax Filters to SQLite
    # 1. Exact phrases (FTS5 or LIKE)
    for phrase in exact_phrases:
        # Check if the phrase only contains letters/numbers and spaces (no special symbols) for safe FTS matching
        phrase_clean = phrase.replace(" ", "")
        if phrase_clean.isalnum():
            where_clauses.append(f"l.id IN (SELECT rowid FROM fts_lines WHERE line_text MATCH ?)")
            params.append(f'"{phrase}"')
        else:
            if case_sensitive:
                where_clauses.append("l.line_text LIKE ?")
                params.append(f"%{phrase}%")
            else:
                where_clauses.append("LOWER(l.line_text) LIKE ?")
                params.append(f"%{phrase.lower()}%")

    # 2. Required words
    for word in required_words:
        if case_sensitive:
            where_clauses.append("l.line_text LIKE ?")
            params.append(f"%{word}%")
        else:
            where_clauses.append("LOWER(l.line_text) LIKE ?")
            params.append(f"%{word.lower()}%")

    # 3. Excluded words
    for word in excluded_words:
        if case_sensitive:
            where_clauses.append("l.line_text NOT LIKE ?")
            params.append(f"%{word}%")
        else:
            where_clauses.append("LOWER(l.line_text) NOT LIKE ?")
            params.append(f"%{word.lower()}%")

    # 4. Fuzzy DB Chunk Accelerator (only if no syntax overrides exist to prevent over-filtering)
    if not exact_match and not regex_match and not exact_phrases and not required_words:
        if search_len >= 3:
            chunk = search_term_processed[:3]
            if case_sensitive:
                where_clauses.append("l.line_text LIKE ?")
                params.append(f"%{chunk}%")
            else:
                where_clauses.append("LOWER(l.line_text) LIKE ?")
                params.append(f"%{chunk.lower()}%")

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    query = f"""
        SELECT
            f.file_path, f.size_kb, f.mod_time,
            l.line_num, l.line_text, l.words_json, l.msg_date, l.author
        FROM lines l
        JOIN files f ON l.file_id = f.id
        {where_sql}
    """

    cursor.execute(query, params)

    # ⚡ HYBRID PYTHON EVALUATION
    # For fuzzy matching, SQLite can't do rapidfuzz internally.
    # So we pull the lines and let Python do the final RapidFuzz scoring.
    # If FTS or EXACT MATCH was used, we only pulled a tiny subset anyway.

    for row in cursor:
        file_path, size_kb, mod_time, line_num, line_text, words_json, msg_date, author = row
        try:
            words = json.loads(words_json) if words_json else []
        except Exception:
            words = []

        best_match = None
        best_score = 0

        if regex_match:
            best_match = search_term # SQLite regex matched it
            best_score = 100
        elif exact_match:
            # We used LIKE or FTS, so we know it's a hit, but we must find the best word for highlighting
            best_score = 100
            for w in words:
                w_proc = w if case_sensitive else w.lower()
                if search_term_processed in w_proc:
                    best_match = w
                    break
            if not best_match:
                best_match = search_term
        else:
            # Pure RapidFuzz Fuzzy Match
            for word in words:
                word_proc = word if case_sensitive else word.lower()

                if not case_sensitive and word_proc in STOP_WORDS:
                    continue

                word_len = len(word_proc)
                max_diff = max(3, int(search_len * 0.7))
                if abs(word_len - search_len) > max_diff:
                    if search_term_processed not in word_proc:
                        continue

                score = fuzz.WRatio(search_term_processed, word_proc, score_cutoff=accuracy_threshold)

                if search_term_processed in word_proc:
                    length_ratio = search_len / max(word_len, 1)
                    if length_ratio >= 0.3:
                        score = max(score, 85 + (15 * length_ratio))

                if score > best_score:
                    best_score = score
                    best_match = word

        # ⚡ Puxxzz FF: Double Validation System (Post-Filter)
        # ⚡ Puxxzz FF: Empty Line Filter
        if best_score >= accuracy_threshold and line_text.strip():
            final_date = msg_date if msg_date else mod_time

            # ⚡ Puxxzz FF: Context Scoring (Boost if near start of line or contains certain bot names)
            if best_match and best_match in line_text:
                if line_text.find(best_match) < 20:
                    best_score += 1.0 # Slight boost

            # ⚡ Puxxzz FF: Bot Excluder
            if author and author.lower() in ["telegram", "botfather", "system"]:
                best_score -= 10.0 # Decrease priority of bots

            results.append({
                "file": file_path,
                "size_kb": size_kb,
                "mod_time": final_date,
                "line_num": line_num,
                "line": line_text,
                "match": best_match,
                "score": round(best_score, 2),
                "author": author
            })

            # ⚡ Puxxzz FF: Memory Safety Valve (Pagination Engine)
            # Stop filling RAM if we hit 100,000 matches during the loop!
            if len(results) >= 100000:
                print("Puxxzz FF Memory Safety: Reached 100k results threshold. Stopping search.")
                break

    conn.close()

    results.sort(key=lambda x: x['score'], reverse=True)

    end_time = time.time()
    return results, round(end_time - start_time, 4)
