import ast
import operator


class CalculatorTool:
    """Safely evaluates basic arithmetic expressions without using eval()."""

    _ALLOWED_OPS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def calculate(self, expression: str) -> dict:
        try:
            self._validate_input(expression)
            tree = ast.parse(expression, mode="eval")
            result = self._safe_eval(tree.body)
            return {"success": True, "result": result, "error": None}

        except ZeroDivisionError:
            return {"success": False, "result": None, "error": "Division by zero"}
        except (SyntaxError, ValueError) as e:
            return {"success": False, "result": None, "error": f"Invalid expression: {str(e)}"}
        except Exception as e:
            return {"success": False, "result": None, "error": f"Calculation failed: {str(e)}"}

    def _validate_input(self, expression: str):
        if not expression or not expression.strip():
            raise ValueError("Expression cannot be empty")
        if len(expression) > 200:
            raise ValueError("Expression too long")

    def _safe_eval(self, node):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("Only numeric constants are allowed")

        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in self._ALLOWED_OPS:
                raise ValueError(f"Operator {op_type.__name__} is not allowed")
            left = self._safe_eval(node.left)
            right = self._safe_eval(node.right)
            return self._ALLOWED_OPS[op_type](left, right)

        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in self._ALLOWED_OPS:
                raise ValueError(f"Operator {op_type.__name__} is not allowed")
            operand = self._safe_eval(node.operand)
            return self._ALLOWED_OPS[op_type](operand)

        else:
            raise ValueError(f"Unsupported expression element: {type(node).__name__}")


calculator_tool = CalculatorTool()
