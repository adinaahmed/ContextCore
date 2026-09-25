import re
from google.genai import types
from app.core.llm_providers.gemini_provider import GeminiProvider
from app.core.tools.calculator import calculator_tool

# Tool-calling uses Gemini's native function-calling schema specifically,
# so it owns its own GeminiProvider instance rather than going through the
# generic LLMProvider interface (which doesn't expose function-calling).
# If Gemini is unavailable, a local rule-based parser extracts the
# expression from the question so calculations still work without an LLM.
_gemini = GeminiProvider()

calculator_function_declaration = types.FunctionDeclaration(
    name="calculate",
    description=(
        "Evaluates a basic arithmetic expression (addition, subtraction, "
        "multiplication, division, exponents). Use this for any math question "
        "instead of computing the answer yourself."
    ),
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "expression": types.Schema(
                type="STRING",
                description="The math expression to evaluate, e.g. '284 * 17' or '(12 + 3) / 5'",
            )
        },
        required=["expression"],
    ),
)

calculator_tool_config = types.Tool(function_declarations=[calculator_function_declaration])

_NUMBER = r"\d+(?:\.\d+)?"


def _format_number(value) -> str:
    """Shows 492.0 as 492, and rounds long decimals."""
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(round(value, 6))
    return str(value)


def _extract_expression(question: str) -> str | None:
    """
    Turns a plain-English math question into an arithmetic expression,
    e.g. 'What is 123 multiplied by 4?' -> '123 * 4'.
    Returns None if no calculable expression is found.
    """
    s = question.lower()

    # Thousands separators: 1,000 -> 1000
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)

    # Aggregates: average / sum / product of a, b and c
    def _aggregate(match, kind):
        nums = re.findall(_NUMBER, match.group(1))
        if len(nums) < 2:
            return match.group(0)
        if kind == "average":
            return f"(({'+'.join(nums)})/{len(nums)})"
        if kind == "sum":
            return f"({'+'.join(nums)})"
        return f"({'*'.join(nums)})"

    s = re.sub(rf"(?:average|mean) of ((?:{_NUMBER}[\s,]*(?:and)?\s*)+)", lambda m: _aggregate(m, "average"), s)
    s = re.sub(rf"sum of ((?:{_NUMBER}[\s,]*(?:and)?\s*)+)", lambda m: _aggregate(m, "sum"), s)
    s = re.sub(rf"product of ((?:{_NUMBER}[\s,]*(?:and)?\s*)+)", lambda m: _aggregate(m, "product"), s)

    # Percentages and powers
    s = re.sub(rf"({_NUMBER})\s*(?:%|percent)\s+of\s+({_NUMBER})", r"(\1/100*\2)", s)
    s = re.sub(rf"square root of\s+({_NUMBER})", r"(\1**0.5)", s)
    s = re.sub(rf"({_NUMBER})\s+squared", r"(\1**2)", s)
    s = re.sub(rf"({_NUMBER})\s+cubed", r"(\1**3)", s)
    s = s.replace("to the power of", "**").replace("^", "**")

    # Word operators
    replacements = [
        ("multiplied by", "*"), ("times", "*"), ("divided by", "/"),
        ("plus", "+"), ("minus", "-"), ("added to", "+"),
    ]
    for word, op in replacements:
        s = s.replace(word, f" {op} ")
    s = re.sub(r"(?<=\d)\s*x\s*(?=\d)", " * ", s)  # 12 x 4

    # Pick the longest run of arithmetic characters that contains an operator
    candidates = re.findall(r"[\d\.\s\+\-\*/\(\)]+", s)
    best = None
    for c in candidates:
        c = c.strip().strip("+-*/ ").strip()
        if re.search(r"\d", c) and re.search(r"\d\s*(\*\*|[\+\-\*/])\s*[\d\(]", c):
            if best is None or len(c) > len(best):
                best = c
    return best


def _plain_answer(expression: str, tool_result: dict) -> str:
    if tool_result["success"]:
        return f"{expression} = {_format_number(tool_result['result'])}"
    return f"I couldn't calculate that: {tool_result['error']}."


def _local_answer(question: str) -> dict | None:
    """Fallback when Gemini is unavailable: parse the question and use the calculator directly."""
    expression = _extract_expression(question)
    if not expression:
        return None
    tool_result = calculator_tool.calculate(expression)
    if not tool_result["success"]:
        return None
    return {
        "answer": _plain_answer(expression, tool_result),
        "tool_used": True,
        "tool_result": tool_result,
        "fallback": True,
    }


def answer_with_tools(question: str) -> dict:
    try:
        response = _gemini.client.models.generate_content(
            model=_gemini.model_name,
            contents=question,
            config=types.GenerateContentConfig(tools=[calculator_tool_config]),
        )

        candidate = response.candidates[0]
        function_call = None

        for part in candidate.content.parts:
            if part.function_call:
                function_call = part.function_call
                break

        if function_call is None:
            text = (response.text or "").strip()
            if text:
                return {"answer": text, "tool_used": False}
            local = _local_answer(question)
            return local or {"answer": "I couldn't work out that calculation.", "tool_used": False}

        if function_call.name != "calculate":
            return {"answer": "Unsupported tool requested by the model.", "tool_used": False}

        expression = function_call.args.get("expression", "")
        tool_result = calculator_tool.calculate(expression)

        if not tool_result["success"]:
            follow_up_contents = (
                f"The calculation failed with error: {tool_result['error']}. "
                f"Explain this to the user briefly."
            )
        else:
            follow_up_contents = (
                f"The calculator tool computed: {expression} = {tool_result['result']}. "
                f"Respond to the original question '{question}' using this result."
            )

        # The second call only phrases the answer nicely. If it fails,
        # still return the correct result in plain form.
        try:
            final_response = _gemini.client.models.generate_content(
                model=_gemini.model_name,
                contents=follow_up_contents,
            )
            answer = (final_response.text or "").strip() or _plain_answer(expression, tool_result)
        except Exception:
            answer = _plain_answer(expression, tool_result)

        return {"answer": answer, "tool_used": True, "tool_result": tool_result}

    except Exception as e:
        # Gemini unavailable (quota, 503, 403): compute locally instead
        local = _local_answer(question)
        if local:
            return local
        return {
            "answer": "I couldn't work out that calculation right now. "
                      "Try writing it as a math expression, for example: 123 * 4",
            "tool_used": False,
            "error": str(e)[:200],
        }