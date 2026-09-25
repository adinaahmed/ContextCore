from app.core.vector_store import vector_store

all_chunks = vector_store.get_all_chunks()
ids = all_chunks.get("ids", [])
docs = all_chunks.get("documents", [])

print(f"Total chunks in store: {len(docs)}")
print()

found = False
for chunk_id, text in zip(ids, docs):
    if "confidence" in text.lower() and "interval" in text.lower():
        found = True
        print(f"=== Chunk ID: {chunk_id} ===")
        print(f"Length: {len(text)} chars")
        print()
        print("=== Suspicious characters in this chunk ===")
        for i, ch in enumerate(text):
            codepoint = ord(ch)
            if codepoint > 127:
                context = text[max(0, i-15):i+15].replace("\n", " ")
                print(f"U+{codepoint:04X} ({codepoint}) | repr: {ch!r} | context: ...{context}...")
        print()
        print("=== Full chunk text ===")
        print(repr(text))
        print()
