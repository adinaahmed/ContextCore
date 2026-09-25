from app.core.document_parser import document_parser

# Replace with your actual statistics PDF filename
filename = "test_pdf_heading.pdf"  # CHANGE THIS to your real slides filename

with open(filename, "rb") as f:
    text = document_parser.parse(filename, f.read())

print("=== Looking for suspicious characters ===")
for i, ch in enumerate(text):
    codepoint = ord(ch)
    if codepoint > 127 and codepoint not in (0x2018, 0x2019, 0x201C, 0x201D, 0x2013, 0x2014, 0x2026):
        # Print anything non-ASCII that isn't a normal smart-quote/dash
        context = text[max(0, i-20):i+20].replace("\n", " ")
        print(f"Codepoint: U+{codepoint:04X} ({codepoint}) | char repr: {ch!r} | context: ...{context}...")
