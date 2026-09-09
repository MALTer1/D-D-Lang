"""v5 runtime extensions for D&D Lang.

This module keeps the existing interpreter intact while adding the v5 list
operations and the small syntax aliases that are safe to desugar before
lexing. The main runtime entry points use V5Interpreter below.
"""

import re

from interpreter import Environment, Interpreter, DMError, RewordSignal


class V5Interpreter(Interpreter):
    """Interpreter with v5 list helpers and auto-growing list assignment."""

    def exec_statement(self, stmt, env):
        if stmt.get("type") == "Assignment":
            target = stmt["target"]
            if target.get("type") == "FieldAccess":
                obj = self.eval_expr(target["obj"], env)
                field = target["field"]
                if isinstance(obj, list) and field.startswith("member_"):
                    value = self.eval_expr(stmt["value"], env)
                    index = self.resolve_member_index(field, env)
                    if index < 0:
                        raise DMError("A list position can't be negative.")
                    if index >= len(obj):
                        obj.extend([None] * (index + 1 - len(obj)))
                    obj[index] = value
                    return
        return super().exec_statement(stmt, env)

    def call_builtin(self, name, arg_nodes, env):
        if name in {"append", "push", "pop", "map", "filter", "contains", "index"}:
            return self.call_v5_builtin(name, arg_nodes, env)
        return super().call_builtin(name, arg_nodes, env)

    def call_v5_builtin(self, name, arg_nodes, env):
        if name in {"append", "push"}:
            if len(arg_nodes) != 2:
                raise DMError(f"'{name}' needs a list and a value.")
            values = self.eval_expr(arg_nodes[0], env)
            value = self.eval_expr(arg_nodes[1], env)
            if not isinstance(values, list):
                raise DMError(f"'{name}' needs a list and a value.")
            values.append(value)
            return values

        if name == "pop":
            if not (1 <= len(arg_nodes) <= 2):
                raise DMError("'pop' needs a list, and can optionally take an index.")
            values = self.eval_expr(arg_nodes[0], env)
            if not isinstance(values, list):
                raise DMError("'pop' needs a list, and can optionally take an index.")
            if not values:
                raise DMError("You can't pop from an empty list.")
            index = -1 if len(arg_nodes) == 1 else int(self.eval_expr(arg_nodes[1], env))
            if index < 0:
                index += len(values)
            if index < 0 or index >= len(values):
                raise DMError(f"There's no item at position {index} in that list.")
            return values.pop(index)

        if name in {"contains", "index"}:
            if len(arg_nodes) != 2:
                raise DMError(f"'{name}' needs a list and a value.")
            values = self.eval_expr(arg_nodes[0], env)
            needle = self.eval_expr(arg_nodes[1], env)
            if not isinstance(values, list):
                raise DMError(f"'{name}' needs a list and a value.")
            if name == "contains":
                return needle in values
            try:
                return values.index(needle)
            except ValueError:
                return -1

        if name in {"map", "filter"}:
            if len(arg_nodes) != 2:
                raise DMError(f"'{name}' needs a list and an operation.")
            values = self.eval_expr(arg_nodes[0], env)
            if not isinstance(values, list):
                raise DMError(f"'{name}' needs a list as its first argument.")
            operation = self.resolve_operation(arg_nodes[1])
            result = []
            for item in values:
                transformed = self.apply_operation(operation, item, env)
                if name == "map" or bool(transformed):
                    result.append(transformed)
            return result

        raise DMError(f"There's no v5 built-in called '{name}'.")

    @staticmethod
    def resolve_operation(node):
        if node.get("type") == "Identifier":
            return ("quest", node["name"])
        if node.get("type") == "StringLiteral":
            return ("name", node["value"])
        raise DMError("The map/filter operation must be a quest name or Scroll.")

    def apply_operation(self, operation, item, env):
        kind, value = operation
        if kind in {"quest", "name"}:
            if value in self.quests:
                return self.call_quest_value(value, item, env)
            if kind == "name" and value in {"str", "len", "num"}:
                return self.call_builtin(value, [self.literal_node(item)], env)
            raise DMError(f"There's no map/filter operation called '{value}'.")
        raise DMError("Invalid map/filter operation.")

    def call_quest_value(self, name, value, env):
        quest = self.quests[name]
        quest_env = Environment(parent=None)
        if quest["params"]:
            quest_env.declare(quest["params"][0], value)
        self.caller_stack.append(env)
        try:
            self.exec_block(quest["body"], quest_env)
            return None
        except RewordSignal as result:
            return result.value
        finally:
            self.caller_stack.pop()

    @staticmethod
    def literal_node(value):
        if isinstance(value, bool):
            return {"type": "BoolLiteral", "value": value}
        if isinstance(value, (int, float)):
            return {"type": "NumberLiteral", "value": value}
        if isinstance(value, str):
            return {"type": "StringLiteral", "value": value}
        if isinstance(value, list):
            return {"type": "ListLiteral", "elements": [V5Interpreter.literal_node(v) for v in value]}
        return {"type": "StringLiteral", "value": str(value)}


def expand_v5_syntax(source):
    """Desugar v5 surface syntax before the existing lexer/parser run.

    - `adventure i in total:` becomes `for i in party(total):`.
    - `encounter Name(...):` becomes the existing isolated `quest` definition.
    - `fight Name(...)` becomes the existing `embark` call.
    """
    lines = []
    for raw in source.splitlines():
        match = re.match(
            r"^(?P<indent>[ \t]*)adventure\s+(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s+in\s+(?P<total>.+):\s*$",
            raw,
        )
        if match:
            lines.append(
                f"{match.group('indent')}for {match.group('var')} in party({match.group('total')}):"
            )
            continue

        raw = re.sub(r"^(?P<indent>[ \t]*)encounter\b", r"\g<indent>quest", raw)
        raw = re.sub(r"^(?P<indent>[ \t]*)fight\b", r"\g<indent>embark", raw)
        lines.append(raw)
    return "\n".join(lines) + ("\n" if source.endswith("\n") else "")
