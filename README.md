## Getting Started

### Requirements
- Python 3.11 (not 3.12+, some libraries aren't compatible yet)
- PostgreSQL
- Tesseract OCR (only needed for scanned PDFs)
- A free Google Gemini API key from https://aistudio.google.com/apikey
- Optional: Ollama with the `gemma3:4b` model, as a local fallback

### Setup
```bash
git clone https://github.com/adinaahmed/ContextCore.git
cd ContextCore
python3.11 -m venv .venv          # Windows: py -3.11 -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your own values:
```
GOOGLE_API_KEY=your_gemini_key
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/rag_db
JWT_SECRET_KEY=any_long_random_text
```

Create the database and tables, then start the server:
```bash
psql -U postgres -c "CREATE DATABASE rag_db;"
python init_db.py
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open http://127.0.0.1:8000/ui/ and register an account.

## Authors
- Hifsa Khattak
- Adina Ahmed
