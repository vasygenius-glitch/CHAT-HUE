import re
from rapidfuzz import process, fuzz

def tokenize_line(line):
    # Splits line into words, removing punctuation
    words = re.findall(r'\w+', line)
    return words

def perform_search(indexed_data, search_term, accuracy_threshold):
    results = []
    search_term_lower = search_term.lower()

    for file_path, lines in indexed_data.items():
        for line_num, line_text in lines:
            words = tokenize_line(line_text)

            best_match = None
            best_score = 0

            for word in words:
                word_lower = word.lower()

                # Exclude extremely short noise words matching purely by coincidence if they don't share characters
                if len(word_lower) < 2 and len(search_term_lower) > 2:
                    continue

                score = fuzz.WRatio(search_term_lower, word_lower)

                # Bonus if the word starts with the search term or contains it
                if search_term_lower in word_lower:
                    length_ratio = len(search_term_lower) / max(len(word_lower), 1)
                    if length_ratio >= 0.4:
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
    return results
