FROM python:3.11-slim

# Tesseract is a system-level dependency (not pip-installable) — required for OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

# Install CPU-only PyTorch explicitly FIRST. The default Linux wheel pulls in
# several GB of NVIDIA CUDA libraries we will never use (no GPU in this
# container) — this was the real cause of the earlier timeout, not just bad luck.
RUN pip install --no-cache-dir --default-timeout=180 \
    torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir --default-timeout=180 -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
