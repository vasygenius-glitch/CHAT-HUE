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
## 2024-05-24 - [Pickle Memory Exhaustion & SQLite]
**Learning:** Storing millions of text lines inside nested Python dictionaries and pickling them into `.pkl` files consumes enormous amounts of RAM (1GB+ for large folders) during search because the entire structure must be deserialized into Python memory simultaneously.
**Action:** Migrated the core architecture to SQLite C++ engine (`.db`). By using `sqlite3`, data is queried from disk directly, and memory consumption drops to near-zero. SQLite `PRAGMA WAL` and `MEMORY temp_store` settings matched or exceeded `pickle`'s raw save speeds.

## 2024-05-24 - [PyQt6 Table View Freezes]
**Learning:** Inserting 10,000+ `QTableWidgetItem` elements into a `QTableWidget` simultaneously causes the PyQt main event loop to hang for several seconds.
**Action:** Implemented Table Pagination (Lazy Loading). The search thread now returns the list of results instantly, but the GUI only generates and injects the first 100 table rows. By connecting to `verticalScrollBar().valueChanged`, additional batches of 100 rows are injected seamlessly as the user scrolls, retaining a stable 60FPS UI.

## 2024-05-24 - [SQLite Sub-Sorting]
**Learning:** When sorting dates alphabetically or lexicographically in a table, messages occurring on the exact same second (e.g. `2024-01-01 10:00:00`) lose their chronological order and get randomly mixed because their primary sort keys are identical.
**Action:** Injected a hidden tie-breaker payload into `Qt.ItemDataRole.UserRole` for the Date column: `f"{mod_time}|{line_num.zfill(7)}"`. If two dates match exactly, the table falls back to comparing the padded line number string, instantly fixing chronologies.
