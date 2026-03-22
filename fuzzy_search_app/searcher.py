import time
from rapidfuzz import fuzz

def perform_search(indexed_data, search_term, accuracy_threshold, exact_match=False):
    start_time = time.time()
    results = []
    search_term_lower = search_term.lower()
    search_len = len(search_term_lower)

    for file_path, lines in indexed_data.items():
        for line_data in lines:
            line_num, line_text, words = line_data

            best_match = None
            best_score = 0

            for word in words:
                word_lower = word.lower()
                word_len = len(word_lower)

                # ⚡ FAST PATH: Length Filter (O(1))
                # If a word is 20 chars and we search for "cat" (3 chars), it's highly unlikely to be a fuzzy match.
                # If a word is 2 chars and we search for "elephant" (8 chars), skip it.
                # We allow a maximum length difference of 70% of the search term or at least 3 chars.
                max_diff = max(3, int(search_len * 0.7))
                if abs(word_len - search_len) > max_diff:
                    # Exception: If the long word contains the search term as a pure substring, it might be a diminutive/suffix
                    if search_term_lower not in word_lower:
                        continue

                # Exclude extremely short noise words
                if word_len < 2 and search_len > 2:
                    continue

                # ⚡ Exact Match
                if exact_match:
                    if search_term_lower == word_lower:
                        score = 100
                    else:
                        continue
                else:
                    # ⚡ Fuzzy Evaluation
                    score = fuzz.WRatio(search_term_lower, word_lower)

                # Morphology/Diminutive Bonus Boost
                if search_term_lower in word_lower:
                    length_ratio = search_len / max(word_len, 1)
                    if length_ratio >= 0.3:
                        score = max(score, 85 + (15 * length_ratio))

                if score > best_score:
                    best_score = score
                    best_match = word

            if best_score >= accuracy_threshold:
                results.append({
                    "file": file_path,
                    "line_num": line_num,
                    "line": line_text,
                    "match": best_match,
                    "score": round(best_score, 2)
                })

    results.sort(key=lambda x: x['score'], reverse=True)
    end_time = time.time()
    return results, round(end_time - start_time, 4)
