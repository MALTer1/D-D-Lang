"""v5 runtime extensions for D&D Lang.

This module keeps the existing interpreter intact while adding the v5 list
operations and the small syntax aliases that are safe to desugar before
lexing. The main runtime entry points use V5Interpreter below.
"""

import re

from interpreter import Interpreter, DMError


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
        args = [self.eval_expr(node, env) for node in arg_nodes]

        if name in {"append", "push"}:
            if len(args) != 2 or not isinstance(args[0], list):
                raise DMError(f"'{name}' needs a list and a value.")
            args[0].append(args[1])
            return args[0]

        if name == "pop":
            if not (1 <= len(args) <= 2) or not isinstance(args[0], list):
                raise DMError("'pop' needs a list, and can optionally take an index.")
            values = args[0]
            if not values:
                raise DMError("You can't pop from an empty list.")
            index = -1 if len(args) == 1 else int(args[1])
            if index < 0:
                index += len(values)
            if index < 0 or index >= len(values):
                raise DMError(f"There's no item at position {index} in that list.")
            return values.pop(index)

        if name in {"contains", "index"}:
            if len(args) != 2 or not isinstance(args[0], list):
                raise DMError(f"'{name}' needs a list and a value.")
            values, needle = args
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
            operation = self.resolve_operation(arg_nodes[1], env)
            result = []
            for item in values:
                transformed = self.apply_operation(operation, item, env)
                if name == "map" or bool(transformed):
                    result.append(transformed)
            return result

        raise DMError(f"There's no v5 built-in called '{name}'.")

    def resolve_operation(self, node, env):
        """Resolve the second argument to map/filter.

        A quest name can be passed bare, e.g. `map(scores, double)`, or as a
        Scroll, e.g. `map(scores, "double")`. A built-in can also be named in
        a Scroll for one-argument built-ins such as `str` and `len`.
        """
        if node.get("type") == "Identifier":
            return ("quest", node["name"])
        if node.get("type") == "StringLiteral":
            return ("name", node["value"])
        try:
            return ("value", self.eval_expr(node, env))
        except Exception:
            raise DMError("The map/filter operation must be a quest name or Scroll.")

    def apply_operation(self, operation, item, env):
        kind, value = operation
        if kind == "quest":
            if value not in self.quests:
                raise DMError(f"There's no quest called '{value}'.")")
            return self.call_quest_value(value, item, env)

        if kind == "name":
            if value in self.quests:
                return self.call_quest_value(value, item, env)
            if value in {"str", "len", "num"}:
                return self.call_builtin(value, [self.literal_node(item)], env)
            raise DMError(f"There's no map/filter operation called '{value}'.")

        return value

    def call_quest_value(self, name, value, env):
        quest = self.quests[name]
        quest_env = self._make_quest_env(quest, [value])
        self.caller_stack.append(env)
        try:
            self.exec_block(quest["body"], quest_env)
            return None
        except Exception as exc:
            from interpreter import RewordSignal
            if isinstance(exc, RewordSignal):
                return exc.value
            raise
        finally:
            self.caller_stack.pop()

    def _make_quest_env(self, quest, args):
        from interpreter import Environment
        quest_env = Environment(parent=None)
        for pname, aval in zip(quest["params"], args):
            quest_env.declare(pname, aval)
        return quest_env

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
        match = re.match(r"^(?P<indent>[ \\t]*)adventure\\s+(?P<var>[A-Za-z_][A-Za-z0-9_]*)\\s+in\\s+(?P<total>.+):\\s*$", raw)
        if match:
            lines.append(
                f"{match.group('indent')}for {match.group('var')} in party({match.group('total')}):"
            )
            continue

        raw = re.sub(r"^(?P<indent>[ \\t]*)encounter\\b", r"\g<indent>quest", raw)
        raw = re.sub(r"^(?P<indent>[ \\t]*)fight\\b", r"\g<indent>embark", raw)
        lines.append(raw)
    return "\n".join(lines) + ("\n" if source.endswith("\n") else "")
