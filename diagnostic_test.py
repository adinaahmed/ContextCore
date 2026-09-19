from app.core.document_parser import document_parser
from app.core.chunking import chunking_service
from app.core.document_lifecycle import _extract_page_and_clean

with open('test_pdf_heading.pdf', 'rb') as f:
    text = document_parser.parse('test_pdf_heading.pdf', f.read())

print('=== RAW PARSED TEXT (repr, showing exact whitespace) ===')
print(repr(text))
print()

chunks = chunking_service.chunk_text(text, strategy='recursive')
print('=== ' + str(len(chunks)) + ' CHUNK(S) ===')

cursor = 0
for i, chunk in enumerate(chunks):
    page, cleaned, cursor = _extract_page_and_clean(text, chunk, cursor)
    print('Chunk ' + str(i) + ': page=' + str(page))
    print('  Cleaned text: ' + repr(cleaned[:80]))
