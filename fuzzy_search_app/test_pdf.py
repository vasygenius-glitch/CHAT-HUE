import fitz
import os

doc = fitz.open()
page = doc.new_page()

# Let's try to just use a system font or skip font embedding for the test,
# or use english to verify the parse logic, as the real PDF support just needs to work with normal PDFs
page.insert_text((50, 50), 'English PDF test. Here is puksy.', fontsize=12)
doc.save('test_data/sample4.pdf')

doc2 = fitz.open('test_data/sample4.pdf')
text = doc2[0].get_text()
print("Extracted:", text)

import indexer
import searcher

data = indexer.index_folder('test_data')
results = searcher.perform_search(data, 'puksy', 50)
print('PDF search results:', [(r['match'], r['file']) for r in results if r['file'].endswith('pdf')])
