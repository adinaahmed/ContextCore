from google.genai import types
from app.core.llm_providers.gemini_provider import GeminiProvider
from app.core.tools.calculator import calculator_tool

# Tool-calling uses Gemini's native function-calling schema specifically,
# so it owns its own GeminiProvider instance rather than going through the
# generic LLMProvider interface (which doesn't expose function-calling).
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
            return {"answer": response.text.strip(), "tool_used": False}

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

        final_response = _gemini.client.models.generate_content(
            model=_gemini.model_name,
            contents=follow_up_contents,
        )

        return {
            "answer": final_response.text.strip() if final_response.text else str(tool_result),
            "tool_used": True,
            "tool_result": tool_result,
        }

    except Exception as e:
        return {"answer": f"Tool-calling failed: {str(e)}", "tool_used": False}
