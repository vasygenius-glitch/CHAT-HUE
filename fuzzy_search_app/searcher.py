import time
import concurrent.futures
from rapidfuzz import fuzz
import re

def search_chunk(file_paths_chunk, indexed_data, search_term_processed, search_len, accuracy_threshold, exact_match, stop_words, regex_match=False, search_pattern=None, case_sensitive=False, author_filter=""):
    author_filter_proc = author_filter if case_sensitive else author_filter.lower()
    chunk_results = []
    for file_path in file_paths_chunk:
        file_metadata = indexed_data[file_path]
        lines = file_metadata.get("lines", []) if isinstance(file_metadata, dict) else file_metadata
        size_kb = file_metadata.get("size_kb", 0) if isinstance(file_metadata, dict) else 0
        mod_time = file_metadata.get("mod_time", "Unknown") if isinstance(file_metadata, dict) else "Unknown"

        for line_data in lines:
            if len(line_data) == 4:
                line_num, line_text, words, msg_date = line_data
            else:
                line_num, line_text, words = line_data
                msg_date = ""

            # ⚡ FAST PATH: Author/Nickname Filter (O(1) line rejection)
            if author_filter_proc:
                line_check = line_text if case_sensitive else line_text.lower()
                # Fast check: does the line even contain the author string?
                # More robust: Check if it's inside brackets like Telegram exports [Author Name]
                if f"[{author_filter_proc}]" not in line_check and author_filter_proc not in line_check:
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

                    if not exact_match and not case_sensitive and word_proc in stop_words:
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
                        score = fuzz.WRatio(search_term_processed, word_proc)

                    if not exact_match and search_term_processed in word_proc:
                        length_ratio = search_len / max(word_len, 1)
                        if length_ratio >= 0.3:
                            score = max(score, 85 + (15 * length_ratio))

                    if score > best_score:
                        best_score = score
                        best_match = word

            if best_score >= accuracy_threshold:
                chunk_results.append({
                    "file": file_path,
                    "size_kb": size_kb,
                    "mod_time": msg_date if msg_date else mod_time, # ⚡ Use exact message date if available, else file modified date
                    "line_num": line_num,
                    "line": line_text,
                    "match": best_match,
                    "score": round(best_score, 2)
                })
    return chunk_results

def perform_search(indexed_data, search_term, accuracy_threshold, exact_match=False, regex_match=False, case_sensitive=False, author_filter=""):
    start_time = time.time()
    results = []
    search_term_processed = search_term if case_sensitive else search_term.lower()
    search_len = len(search_term_processed)

    stop_words = {"и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то", "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за", "бы", "по", "только", "ее", "мне", "было", "вот", "от", "меня", "еще", "нет", "о", "из", "ему", "теперь", "когда", "даже", "ну", "вдруг", "ли", "если", "уже", "или", "ни", "быть", "был", "него", "до", "вас", "нибудь", "опять", "уж", "вам", "ведь", "там", "потом", "себя", "ничего", "ей", "может", "они", "тут", "где", "есть", "надо", "ней", "для", "мы", "тебя", "их", "чем", "была", "сам", "чтоб", "без", "будто", "человек", "чего", "раз", "тоже", "себе", "под", "будет", "ж", "тогда", "кто", "этот", "того", "потому", "этого", "какой", "совсем", "ним", "здесь", "этом", "один", "почти", "мой", "тем", "чтобы", "нее", "сейчас", "были", "куда", "зачем", "всех", "никогда", "можно", "при", "наконец", "два", "об", "другой", "хоть", "после", "над", "больше", "тот", "через", "эти", "нас", "про", "всего", "них", "какая", "много", "разве", "три", "эту", "моя", "впрочем", "хорошо", "свою", "этой", "перед", "иногда", "лучше", "чуть", "том", "нельзя", "такой", "им", "более", "всегда", "конечно", "всю", "между", "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with", "by", "of"}

    search_pattern = None
    all_files = list(indexed_data.keys())
    chunk_size = max(1, len(all_files) // 8)
    chunks = [all_files[i:i + chunk_size] for i in range(0, len(all_files), chunk_size)]

    with concurrent.futures.ThreadPoolExecutor() as executor:
        flags = re.IGNORECASE if not case_sensitive else 0
        if regex_match:
            try:
                search_pattern = re.compile(search_term, flags)
            except re.error:
                pass

        futures = [executor.submit(search_chunk, chunk, indexed_data, search_term_processed, search_len, accuracy_threshold, exact_match, stop_words, regex_match, search_pattern, case_sensitive, author_filter) for chunk in chunks]
        for future in concurrent.futures.as_completed(futures):
            results.extend(future.result())

    results.sort(key=lambda x: x['score'], reverse=True)

    # ⚡ BOLT RAM OPTIMIZATION: Aggressive Garbage Collection
    if len(results) > 500:
        results = results[:500]
        import gc
        gc.collect() # Force free memory of the discarded millions of dictionary results

    end_time = time.time()
    return results, round(end_time - start_time, 4)
