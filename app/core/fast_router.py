import re

GREETINGS = {"hi", "hello", "hey", "thanks", "thank you", "good morning", "good evening", "bye"}
COMPLEX_HINTS = ("compare", "difference between", "differences", "why", "explain how",
                 "pros and cons", "advantages and disadvantages", "relationship between",
                 "summarize", "summarise", "analyze", "analyse", "evaluate")
CALC_PATTERN = re.compile(r"\d+(\.\d+)?\s*[\+\-\*/x\^%]\s*\d+")
CALC_WORDS = ("calculate", "compute", "how much is", "what is the sum", "percentage of")


def classify_question(question: str) -> str:
    """Instant rule-based router. Returns direct / calculation / simple / complex
    without calling an AI model, so it adds almost no time to a query."""
    q = question.strip().lower()
    words = q.split()

    if q.rstrip("!?.") in GREETINGS or (len(words) <= 3 and any(g in q for g in GREETINGS)):
        return "direct"

    if CALC_PATTERN.search(q) or any(w in q for w in CALC_WORDS):
        return "calculation"

    if any(h in q for h in COMPLEX_HINTS) or q.count("?") > 1 or len(words) > 25:
        return "complex"

    return "simple"