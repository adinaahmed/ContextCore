import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
print("API key loaded:", bool(api_key))
print("Key length:", len(api_key) if api_key else 0)

if not api_key:
    raise RuntimeError("GOOGLE_API_KEY was not found.")

client = genai.Client(api_key=api_key)

try:
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents="Reply with exactly: Gemini connection successful."
    )
    print("SUCCESS")
    print("Gemini response:", response.text)
except Exception as e:
    print("FAILED")
    print("Exception type:", type(e).__name__)
    print("Exception details:", str(e))
