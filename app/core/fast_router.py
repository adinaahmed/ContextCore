import re

GREETING_WORDS = {"hi", "hello", "hey", "thanks", "thank", "bye", "yo"}
GREETING_PHRASES = ("thank you", "good morning", "good afternoon", "good evening", "good night")
COMPLEX_PATTERN = re.compile(
    r"\b(compare|comparison|difference between|differences|why|explain how|pros and cons|"
    r"advantages and disadvantages|relationship between|summari[sz]e|analy[sz]e|evaluate)\b"
)
CALC_PATTERN = re.compile(r"\d+(\.\d+)?\s*[\+\-\*/x\^%]\s*\d+")
CALC_WORDS = re.compile(r"\b(calculate|compute|how much is|what is the sum|percentage of)\b")


def classify_question(question: str) -> str:
    """Instant rule-based router. Returns direct / calculation / simple / complex
    without calling an AI model. Matches whole words only, so words like
    'hashing' or 'this' are not mistaken for the greeting 'hi'."""
    q = question.strip().lower()
    tokens = re.findall(r"[a-z']+", q)

    if len(tokens) <= 3 and (
        any(t in GREETING_WORDS for t in tokens) or any(p in q for p in GREETING_PHRASES)
    ):
        return "direct"

    if CALC_PATTERN.search(q) or CALC_WORDS.search(q):
        return "calculation"

    if COMPLEX_PATTERN.search(q) or q.count("?") > 1 or len(tokens) > 25:
        return "complex"

    return "simple"
