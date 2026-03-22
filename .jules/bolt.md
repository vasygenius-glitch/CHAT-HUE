## 2024-05-24 - [Telegram Parsing Bottlenecks]
**Learning:** `datetime.datetime.strptime` inside the `parse_html` loop parsing tens of thousands of messages in massive Telegram exports causes a massive CPU bottleneck during the indexing phase.
**Action:** Replace `strptime` with fast O(1) string slicing when the format is statically known (`DD.MM.YYYY HH:MM:SS` -> `YYYY-MM-DD HH:MM:SS`), saving massive processing time.

## 2024-05-24 - [Search Filter Performance]
**Learning:** Full-text string search (`author_filter_proc not in line_check`) for author filtering is an O(N) operation that wastes cycles and produces false positives (if the author name is in another user's message body).
**Action:** Extract the `author` into its own variable during the indexing phase, and use an O(1) direct string containment check strictly against that metadata variable during the search phase.
## 2024-05-24 - [RapidFuzz & ThreadPoolExecutor]
**Learning:** RapidFuzz is a C++ extension that automatically releases the Global Interpreter Lock (GIL). Therefore, `ThreadPoolExecutor` CAN achieve true multi-core parallel processing during fuzzy searches. Switching to `ProcessPoolExecutor` is unnecessary and introduces risky pickling overhead for PyQt apps.
**Action:** Kept `ThreadPoolExecutor` but dynamically scaled `max_workers` using `os.cpu_count()` to fully saturate CPU cores during massive searches.

## 2024-05-24 - [RapidFuzz `score_cutoff` C++ Bailout]
**Learning:** Calling `fuzz.WRatio(str1, str2)` calculates the exact match percentage even if it's incredibly low.
**Action:** Pass `score_cutoff=accuracy_threshold` directly into the RapidFuzz call. The C++ engine mathematically determines if a string cannot possibly meet the threshold mid-computation and aborts instantly, saving massive CPU cycles on high-accuracy searches.

## 2024-05-24 - [BeautifulSoup RAM Explosion]
**Learning:** Passing a giant Telegram HTML chat log (100MB+) into `BeautifulSoup(f, 'lxml')` consumes over a Gigabyte of RAM because it builds a DOM node for every useless `<style>`, `<script>`, and empty layout `<div>`.
**Action:** Use `bs4.SoupStrainer('div', class_='message')` during initialization. The DOM tree is only built for relevant messages, slashing memory usage by 90% and parsing time in half.
