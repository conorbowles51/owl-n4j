"""Bounded, deterministic Python-expression workspace. No eval/exec, attributes, I/O or imports.

The interpreter supports ordinary row calculations and comprehensions without exposing a
Python runtime or production credentials. Values and the exact expression are recorded.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import operator
from decimal import Decimal


class CalculationError(ValueError):
    pass


def bounded_range(*args):
    values = range(*args)
    if len(values) > 100_000:
        raise CalculationError('A generated sequence may contain at most 100,000 items; use batches.')
    return list(values)


class Workspace:
    def __init__(self, inputs: dict, max_steps=200_000):
        self.inputs = inputs
        self.remaining = max_steps

    def tick(self, value=None):
        self.remaining -= 1
        if self.remaining < 0:
            raise CalculationError("Calculation work limit reached. Split the input into batches.")
        if isinstance(value, (list, tuple, dict, str)) and len(value) > 100_000:
            raise CalculationError("Calculation result is too large; use batches.")
        if isinstance(value, int) and value.bit_length() > 1024:
            raise CalculationError("Integer is too large.")
        if isinstance(value, float) and not math.isfinite(value):
            raise CalculationError("Calculation produced a non-finite number.")
        return value

    def run(self, expression: str):
        if len(expression) > 20_000:
            raise CalculationError("The expression is too long.")
        try:
            root = ast.parse(expression, mode="eval")
            if sum(1 for _ in ast.walk(root)) > 1500:
                raise CalculationError("Simplify the expression into smaller steps.")
            return self.visit(root.body, self.inputs)
        except (SyntaxError, TypeError, KeyError, IndexError, ZeroDivisionError, ArithmeticError, RecursionError) as exc:
            raise CalculationError(f"Calculation could not be evaluated: {type(exc).__name__}.") from exc

    def visit(self, node, env):
        self.tick()
        if isinstance(node, ast.Constant):
            if node.value is None or isinstance(node.value, (str, int, float, bool)):
                return self.tick(node.value)
        if isinstance(node, ast.Name):
            if node.id.startswith("_") or node.id not in env:
                raise CalculationError("Unknown input variable: " + node.id)
            return env[node.id]
        if isinstance(node, (ast.List, ast.Tuple)):
            return [self.visit(e, env) for e in node.elts]
        if isinstance(node, ast.Dict):
            if any(k is None for k in node.keys):
                raise CalculationError("Dictionary unpacking is not supported.")
            return {self.visit(k, env): self.visit(v, env) for k, v in zip(node.keys, node.values)}
        if isinstance(node, ast.Subscript):
            value = self.visit(node.value, env)
            if not isinstance(value, (dict, list, tuple, str)):
                raise CalculationError("Only input collections can be indexed.")
            return value[self.visit(node.slice, env)]
        if isinstance(node, ast.Slice):
            return slice(*(self.visit(n, env) if n else None for n in (node.lower, node.upper, node.step)))
        if isinstance(node, ast.BinOp):
            left, right = self.visit(node.left, env), self.visit(node.right, env)
            ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                   ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod}
            fn = ops.get(type(node.op))
            if fn is None:
                raise CalculationError("Unsupported arithmetic operator.")
            if isinstance(node.op, ast.Mult):
                for collection, count in ((left, right), (right, left)):
                    if isinstance(collection, (str, list, tuple)) and isinstance(count, int) and len(collection) * count > 100_000:
                        raise CalculationError("Requested repetition is too large.")
            return self.tick(fn(left, right))
        if isinstance(node, ast.UnaryOp):
            fn = {ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Not: operator.not_}.get(type(node.op))
            if fn:
                return fn(self.visit(node.operand, env))
        if isinstance(node, ast.Compare):
            left = self.visit(node.left, env)
            fns = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le,
                   ast.Gt: operator.gt, ast.GtE: operator.ge, ast.In: lambda a, b: a in b,
                   ast.NotIn: lambda a, b: a not in b, ast.Is: operator.is_, ast.IsNot: operator.is_not}
            for op, rhs in zip(node.ops, node.comparators):
                right = self.visit(rhs, env)
                if type(op) not in fns or not fns[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.BoolOp):
            for part in node.values:
                value = self.visit(part, env)
                if isinstance(node.op, ast.And) and not value or isinstance(node.op, ast.Or) and value:
                    return value
            return value
        if isinstance(node, ast.IfExp):
            return self.visit(node.body if self.visit(node.test, env) else node.orelse, env)
        if isinstance(node, (ast.ListComp, ast.GeneratorExp, ast.DictComp)):
            result = []
            def gather(index, scope):
                if index == len(node.generators):
                    result.append((self.visit(node.key, scope), self.visit(node.value, scope))
                                  if isinstance(node, ast.DictComp) else self.visit(node.elt, scope))
                    self.tick(result)
                    return
                generator = node.generators[index]
                if generator.is_async or not isinstance(generator.target, ast.Name) or generator.target.id.startswith("_"):
                    raise CalculationError("Use a simple named row variable.")
                for item in self.visit(generator.iter, scope):
                    self.tick()
                    child = dict(scope, **{generator.target.id: item})
                    if all(self.visit(condition, child) for condition in generator.ifs):
                        gather(index + 1, child)
            gather(0, env)
            return dict(result) if isinstance(node, ast.DictComp) else result
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            functions = {"sum": sum, "len": len, "min": min, "max": max, "abs": abs,
                         "round": round, "sorted": sorted, "str": str, "int": int,
                         "float": float, "decimal": lambda x: Decimal(str(x)), "range": bounded_range}
            fn = functions.get(node.func.id)
            if fn:
                return self.tick(fn(*(self.visit(arg, env) for arg in node.args)))
        raise CalculationError("Only arithmetic, comparisons, indexing, comprehensions and approved functions are allowed.")


def calculate(expression: str, inputs: dict) -> dict:
    encoded = json.dumps(inputs, ensure_ascii=False, allow_nan=False, sort_keys=True)
    if len(encoded.encode()) > 16 * 1024 * 1024:
        raise CalculationError("Calculation input exceeds 16 MiB. Use smaller batches.")
    result = Workspace(json.loads(encoded)).run(expression)
    result = json.loads(json.dumps(result, default=lambda x: str(x) if isinstance(x, Decimal) else x, allow_nan=False))
    return {"expression": expression, "inputs_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
            "value": result, "method": "bounded_python_expression", "arithmetic": "use decimal() for exact money"}
