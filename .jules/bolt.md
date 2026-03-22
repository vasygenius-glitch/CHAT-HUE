## 2024-05-24 - [Telegram Parsing Bottlenecks]
**Learning:** `datetime.datetime.strptime` inside the `parse_html` loop parsing tens of thousands of messages in massive Telegram exports causes a massive CPU bottleneck during the indexing phase.
**Action:** Replace `strptime` with fast O(1) string slicing when the format is statically known (`DD.MM.YYYY HH:MM:SS` -> `YYYY-MM-DD HH:MM:SS`), saving massive processing time.

## 2024-05-24 - [Search Filter Performance]
**Learning:** Full-text string search (`author_filter_proc not in line_check`) for author filtering is an O(N) operation that wastes cycles and produces false positives (if the author name is in another user's message body).
**Action:** Extract the `author` into its own variable during the indexing phase, and use an O(1) direct string containment check strictly against that metadata variable during the search phase.
