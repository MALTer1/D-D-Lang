"""
Interpreter for the D&D-themed language.
Walks the AST from parser.py and actually executes the program.

Scoping rules implemented:
- attempt/or_attempt/fail and adventure blocks are normal nested scopes:
  they can see and modify variables from any enclosing scope.
- quest bodies are ISOLATED by default. They only see their own
  parameters, plus anything explicitly pulled in with `init name`.
  `init` looks up the variable in the scope that was active where
  `embark` was called from.

homebrew/STATS notes:
- kind names are fixed: character, item, monster, spell.
- field names inside a homebrew are free, but must be number/Scroll/
  honor-lie/list, and must meet a shape requirement (min total counted
  fields, min distinct types, capped contribution per type).
- Every homebrew automatically gets a STATS block: STR/DEX/CON/INT/WIS/CHA,
  defaulting to 10 if not set, plus unlimited custom "extra" stats.
  Each stat has .number and .mod (auto = floor((number-10)/2), overridable).
- The 6 default stats have real built-in behavior, called via the instance:
    instance.force.mod(x)     -- STR: x + STR value
    instance.sway.mod(x)      -- CHA: x * CHA value
    instance.endure.mod(x, times)   -- CON: repeated % reduction
    instance.perceive.mod(x_list)   -- WIS: average of list + WIS value
    instance.solve.mod COMPARATOR(difficulty)  -- INT: dice check, e.g.
        instance.solve.mod \\_(10)
  (.mod or .number picks which of the stat's two values feeds the math)
  `initiative` (DEX, code reordering) is not implemented yet.
"""

import math
import random
import re


class DMError(Exception):
    """A runtime error, reported in the DM's voice."""
    def __init__(self, message, line=None):
        loc = f" (line {line})" if line is not None else ""
        super().__init__(f"That's not within your ability{loc}: {message}")


class QuitSignal(Exception):
    """Raised by `quit` to break out of the nearest adventure/while/for loop."""
    pass


class ContinueSignal(Exception):
    """Raised by `continue` to skip to the next iteration of the nearest loop."""
    pass


class RewordSignal(Exception):
    """Raised by `reward` to return a value from a quest."""
    def __init__(self, value):
        self.value = value


SHAPE_RULES = {
    "character": {"min_total": 3, "min_types": 2, "max_per_type": 2},
    "item":      {"min_total": 2, "min_types": 2, "max_per_type": 1},
    "monster":   {"min_total": 2, "min_types": 2, "max_per_type": 1},
    "spell":     {"min_total": 2, "min_types": 2, "max_per_type": 1},
}

DEFAULT_STAT_NAMES = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]

STAT_FUNC_TO_STAT = {"endure": "CON", "perceive": "WIS"}


class Environment:
    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent

    def get(self, name):
        if name in self.vars:
            return self.vars[name]
        if self.parent is not None:
            return self.parent.get(name)
        raise DMError(f"'{name}' hasn't been declared with 'ability' yet.")

    def set_existing(self, name, value):
        """Set a variable that must already exist somewhere in the chain."""
        env = self
        while env is not None:
            if name in env.vars:
                env.vars[name] = value
                return
            env = env.parent
        # if it doesn't exist anywhere, declare it here (fallback)
        self.vars[name] = value

    def declare(self, name, value):
        self.vars[name] = value


def to_scroll(value):
    """Convert any value to its display/Scroll form."""
    if value is True:
        return "honor"
    if value is False:
        return "lie"
    return str(value)


def classify_value(value):
    if isinstance(value, bool):
        return "honor/lie"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "Scroll"
    if isinstance(value, list):
        return "list"
    return "unknown"


class Interpreter:
    def __init__(self, output_func=print, input_func=input):
        self.global_env = Environment()
        self.quests = {}
        self.homebrews = {}
        self.output_func = output_func
        self.input_func = input_func
        # a stack of the environments active where each `embark` call happened,
        # so `init` can reach back to the *caller's* scope.
        self.caller_stack = []
        # global STATS (set via a top-level STATS: block), used by force/sway
        # calls that aren't attached to any instance. None until declared.
        self.global_stats = None
        # a stack of {"statements": [...], "index": n} frames, one per
        # currently-executing block, so `sway` can reorder the block it's
        # actually inside (and only the part that hasn't run yet).
        self.block_stack = []

    def run(self, program_ast):
        self.exec_block(program_ast["body"], self.global_env)

    # ---- statement execution ----

    def exec_block(self, statements, env):
        frame = {"statements": list(statements), "index": 0}
        self.block_stack.append(frame)
        try:
            while frame["index"] < len(frame["statements"]):
                stmt = frame["statements"][frame["index"]]
                self.exec_statement(stmt, env)
                frame["index"] += 1
        finally:
            self.block_stack.pop()

    def exec_statement(self, stmt, env):
        kind = stmt["type"]

        if kind == "AbilityDecl":
            value = self.eval_expr(stmt["value"], env)
            env.declare(stmt["name"], value)

        elif kind == "Assignment":
            value = self.eval_expr(stmt["value"], env)
            target = stmt["target"]
            if target["type"] == "Identifier":
                env.set_existing(target["name"], value)
            elif target["type"] == "FieldAccess":
                obj = self.eval_expr(target["obj"], env)
                field = target["field"]
                if isinstance(obj, list) and field.startswith("member_"):
                    index = self.resolve_member_index(field, env)
                    if 0 <= index < len(obj):
                        obj[index] = value
                    else:
                        raise DMError(f"There's no item at position {index} in that list.")
                elif isinstance(obj, dict):
                    obj[field] = value
                else:
                    raise DMError("That's not something you can assign to.")
            else:
                raise DMError("That's not something you can assign to.")

        elif kind == "Narrate":
            value = self.eval_expr(stmt["value"], env)
            self.output_func(to_scroll(value))

        elif kind == "Attempt":
            for clause in stmt["clauses"]:
                if self.eval_expr(clause["condition"], env):
                    inner = Environment(parent=env)
                    self.exec_block(clause["body"], inner)
                    return
            if stmt["fail_body"] is not None:
                inner = Environment(parent=env)
                self.exec_block(stmt["fail_body"], inner)

        elif kind == "Adventure":
            count = self.eval_expr(stmt["count"], env)
            try:
                for _ in range(int(count)):
                    inner = Environment(parent=env)
                    try:
                        self.exec_block(stmt["body"], inner)
                    except ContinueSignal:
                        continue
            except QuitSignal:
                pass

        elif kind == "While":
            try:
                while self.eval_expr(stmt["condition"], env):
                    inner = Environment(parent=env)
                    try:
                        self.exec_block(stmt["body"], inner)
                    except ContinueSignal:
                        continue
            except QuitSignal:
                pass

        elif kind == "ForParty":
            items = self.resolve_party(stmt["args"], env)
            try:
                for item in items:
                    inner = Environment(parent=env)
                    inner.declare(stmt["var"], item)
                    try:
                        self.exec_block(stmt["body"], inner)
                    except ContinueSignal:
                        continue
            except QuitSignal:
                pass

        elif kind == "Submit":
            self.exec_submit(stmt, env)

        elif kind == "Quit":
            raise QuitSignal()

        elif kind == "Continue":
            raise ContinueSignal()

        elif kind == "QuestDef":
            self.quests[stmt["name"]] = stmt

        elif kind == "HomebrewDef":
            self.define_homebrew(stmt, env)

        elif kind == "GlobalStats":
            self.global_stats = self.build_stats(stmt["stats"], stmt["extra_stats"], env)

        elif kind == "SummonDecl":
            self.exec_summon(stmt, env)

        elif kind == "Reword":
            value = self.eval_expr(stmt["value"], env)
            raise RewordSignal(value)

        elif kind == "Init":
            if not self.caller_stack:
                raise DMError("'init' can't be used outside of a quest.")
            caller_env = self.caller_stack[-1]
            for name in stmt["names"]:
                env.declare(name, caller_env.get(name))

        elif kind == "ExprStatement":
            self.eval_expr(stmt["expr"], env)

        else:
            raise DMError(f"Unknown statement type '{kind}'.")

    # ---- expression evaluation ----

    def eval_expr(self, node, env):
        kind = node["type"]

        if kind == "NumberLiteral":
            return node["value"]
        if kind == "StringLiteral":
            return node["value"]
        if kind == "BoolLiteral":
            return node["value"]
        if kind == "ListLiteral":
            return [self.eval_expr(e, env) for e in node["elements"]]
        if kind == "DiceLiteral":
            return node["max"]
        if kind == "Identifier":
            return env.get(node["name"])
        if kind == "FieldAccess":
            obj = self.eval_expr(node["obj"], env)
            field = node["field"]
            if isinstance(obj, dict) and field in obj:
                return obj[field]
            if isinstance(obj, list) and field.startswith("member_"):
                index = self.resolve_member_index(field, env)
                if 0 <= index < len(obj):
                    return obj[index]
                raise DMError(f"There's no item at position {index} in that list.")
            raise DMError(f"'{field}' isn't a field on that thing.")
        if kind == "PlayerInput":
            prompt = self.eval_expr(node["prompt"], env)
            raw = self.input_func(to_scroll(prompt))
            return coerce_input(raw)
        if kind == "UnaryOp":
            val = self.eval_expr(node["operand"], env)
            if node["op"] == "-":
                return -val
        if kind == "BinaryOp":
            return self.eval_binary(node, env)
        if kind == "Embark":
            return self.call_quest(node["name"], node["args"], env)
        if kind == "Call":
            return self.call_builtin(node["name"], node["args"], env)
        if kind == "CallExpr":
            return self.eval_call_expr(node, env)
        if kind == "SolveExpr":
            return self.eval_solve(node, env)
        if kind == "ForceExpr":
            return self.eval_force(node, env)
        if kind == "SwayExpr":
            return self.eval_sway(node, env)

        raise DMError(f"Unknown expression type '{kind}'.")

    def eval_binary(self, node, env):
        left = self.eval_expr(node["left"], env)
        right = self.eval_expr(node["right"], env)
        op = node["op"]

        if op == "+":
            if isinstance(left, str) or isinstance(right, str):
                return to_scroll(left) + to_scroll(right)
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            if right == 0:
                raise DMError("You can't divide by zero.")
            return left / right
        if op == "%":
            if right == 0:
                raise DMError("You can't divide by zero.")
            return left % right
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == ">":
            return left > right
        if op == "<":
            return left < right
        if op == ">=":
            return left >= right
        if op == "<=":
            return left <= right

        raise DMError(f"Unknown operator '{op}'.")

    def call_quest(self, name, arg_nodes, env):
        if name not in self.quests:
            raise DMError(f"There's no quest called '{name}'.")
        quest = self.quests[name]
        args = [self.eval_expr(a, env) for a in arg_nodes]

        quest_env = Environment(parent=None)  # isolated!
        for pname, aval in zip(quest["params"], args):
            quest_env.declare(pname, aval)

        self.caller_stack.append(env)
        try:
            self.exec_block(quest["body"], quest_env)
            return None
        except RewordSignal as r:
            return r.value
        finally:
            self.caller_stack.pop()

    def resolve_member_index(self, field, env):
        """'member_1' -> literal index 1. 'member_player_num' -> looks up
        the variable 'player_num' and uses its current value as the index."""
        remainder = field[len("member_"):]
        if remainder.isdigit():
            return int(remainder)
        return int(env.get(remainder))

    def call_builtin(self, name, arg_nodes, env):
        args = [self.eval_expr(a, env) for a in arg_nodes]
        if name == "roll":
            size = args[0]
            if size == 0:
                return 0
            return random.randint(1, int(size))
        if name in ("endure", "perceive"):
            return self.run_plain_stat_function(name, args)
        if name == "max":
            return max(args[0]) if len(args) == 1 else max(args)
        if name == "min":
            return min(args[0]) if len(args) == 1 else min(args)
        if name == "len":
            return len(args[0])
        if name == "num":
            raw = args[0]
            try:
                if isinstance(raw, (int, float)):
                    return raw
                if "." in raw:
                    return float(raw)
                return int(raw)
            except ValueError:
                raise ValueError(f"'{raw}' isn't a valid number.")
        if name == "str":
            return to_scroll(args[0])
        raise DMError(f"There's no built-in called '{name}'.")

    def resolve_party(self, arg_nodes, env):
        """Resolves the items a `for x in party(...)` loop iterates over."""
        args = [self.eval_expr(a, env) for a in arg_nodes]
        if len(args) == 1:
            a = args[0]
            if isinstance(a, dict):
                return list(a.keys())
            if isinstance(a, list):
                return a
            return list(range(int(a)))
        if len(args) == 2:
            return list(range(int(args[0]), int(args[1])))
        raise DMError("party(...) takes 1 or 2 arguments.")

    def exec_submit(self, stmt, env):
        try:
            inner = Environment(parent=env)
            self.exec_block(stmt["body"], inner)
        except (QuitSignal, ContinueSignal, RewordSignal):
            raise  # control-flow signals aren't errors, let them propagate
        except Exception as e:
            for clause in stmt["considers"]:
                name = clause["error_name"]
                matches = (
                    name is None
                    or (name == "ValueError" and isinstance(e, ValueError))
                    or (name == "DMError" and isinstance(e, DMError))
                    or (name == "ZeroDivisionError" and isinstance(e, ZeroDivisionError))
                )
                if matches:
                    inner2 = Environment(parent=env)
                    self.exec_block(clause["body"], inner2)
                    return
            raise

    # ---- homebrew / STATS ----

    def define_homebrew(self, stmt, env):
        kind = stmt["kind"]
        if kind not in SHAPE_RULES:
            raise DMError(
                f"'{kind}' isn't a real homebrew kind. Choose character, item, monster, or spell."
            )
        values = {fname: self.eval_expr(expr, env) for fname, expr in stmt["fields"].items()}
        filled = self.fill_shape(kind, values)
        for fname, val in filled.items():
            if fname not in stmt["fields"]:
                stmt["fields"][fname] = value_to_literal_node(val)
        self.homebrews[stmt["name"]] = stmt

    def fill_shape(self, kind, values):
        """Silently auto-fills placeholder fields until the kind's shape
        requirement (min total / min distinct types / max per type) is met."""
        rules = SHAPE_RULES[kind]
        type_counts = {}
        for v in values.values():
            t = classify_value(v)
            type_counts[t] = type_counts.get(t, 0) + 1

        def counted_total():
            return sum(min(c, rules["max_per_type"]) for c in type_counts.values())

        filler_cycle = ["number", "Scroll", "list", "honor/lie"]
        defaults = {"number": 0, "Scroll": "", "list": [], "honor/lie": False}
        i = 0
        while counted_total() < rules["min_total"] or len(type_counts) < rules["min_types"]:
            missing = [t for t in filler_cycle if t not in type_counts]
            if len(type_counts) < rules["min_types"] and missing:
                new_type = missing[0]
            else:
                new_type = filler_cycle[i % len(filler_cycle)]
            placeholder_name = f"_auto_{new_type.replace('/', '_')}_{i}"
            values[placeholder_name] = defaults[new_type]
            type_counts[new_type] = type_counts.get(new_type, 0) + 1
            i += 1
        return values

    def build_stats(self, stats_exprs, extra_exprs, env):
        stats = {}
        for sname in DEFAULT_STAT_NAMES:
            if sname in stats_exprs:
                number = self.eval_expr(stats_exprs[sname], env)
            else:
                number = 10  # auto-fill default
            stats[sname] = {"number": number, "mod": math.floor((number - 10) / 2)}
        for ename, expr in extra_exprs.items():
            number = self.eval_expr(expr, env)
            stats[ename] = {"number": number, "mod": math.floor((number - 10) / 2)}
        return stats

    def get_global_stats(self):
        if self.global_stats is not None:
            return self.global_stats
        return {s: {"number": 10, "mod": 0} for s in DEFAULT_STAT_NAMES}

    def exec_summon(self, stmt, env):
        tmpl = self.homebrews.get(stmt["template"])
        if tmpl is None:
            raise DMError(f"There's no homebrew called '{stmt['template']}'.")

        instance = {}
        for fname, expr in tmpl["fields"].items():
            instance[fname] = self.eval_expr(expr, env)

        instance["STATS"] = self.build_stats(tmpl["stats"], tmpl["extra_stats"], env)
        instance["__kind__"] = tmpl["kind"]
        env.declare(stmt["var_name"], instance)

    def eval_call_expr(self, node, env):
        callee = node["callee"]

        # instance.force.mod(x) / instance.sway.number(x) / etc.
        if (callee["type"] == "FieldAccess"
                and callee["field"] in ("mod", "number")
                and callee["obj"]["type"] == "FieldAccess"
                and callee["obj"]["field"] in STAT_FUNC_TO_STAT):
            args = [self.eval_expr(a, env) for a in node["args"]]
            stat_func = callee["obj"]["field"]
            mode = callee["field"]
            instance = self.eval_expr(callee["obj"]["obj"], env)
            return self.run_stat_function(stat_func, instance, mode, args)

        # plain endure(x, times, rate) / perceive(list) with no instance
        if callee["type"] == "Identifier" and callee["name"] in ("endure", "perceive"):
            args = [self.eval_expr(a, env) for a in node["args"]]
            return self.run_plain_stat_function(callee["name"], args)

        # string methods: someString.lower(), someString.contains(x), etc.
        if callee["type"] == "FieldAccess":
            obj = self.eval_expr(callee["obj"], env)
            if isinstance(obj, str):
                args = [self.eval_expr(a, env) for a in node["args"]]
                return self.run_string_method(obj, callee["field"], args)

        raise DMError("That's not something you can call like that.")

    def run_string_method(self, s, method, args):
        if method == "lower":
            return s.lower()
        if method == "upper":
            return s.upper()
        if method == "trim":
            return s.strip()
        if method == "clean":
            return " ".join(s.split())
        if method == "title":
            return s.title()
        if method == "starts":
            return s.startswith(to_scroll(args[0]))
        if method == "ends":
            return s.endswith(to_scroll(args[0]))
        if method == "contains":
            return to_scroll(args[0]) in s
        if method == "empty":
            return len(s) == 0
        if method == "words":
            return s.split()
        if method == "split":
            return s.split(to_scroll(args[0])) if args else s.split()
        if method == "join":
            return s.join(to_scroll(v) for v in args[0])
        if method == "find":
            return s.find(to_scroll(args[0]))
        if method == "count":
            return s.count(to_scroll(args[0]))
        raise DMError(f"Scrolls don't have a '{method}' method.")

    def run_stat_function(self, stat_func, instance, mode, args):
        if not isinstance(instance, dict) or "STATS" not in instance:
            raise DMError(f"That doesn't have STATS to use '{stat_func}' with.")
        stat_name = STAT_FUNC_TO_STAT[stat_func]
        stat_value = instance["STATS"][stat_name][mode]

        if stat_func == "endure":
            x, times = args[0], args[1]
            rate = stat_value * (0.05 if mode == "mod" else 0.005)
            for _ in range(int(times)):
                x = x - (x * rate)
            return x
        if stat_func == "perceive":
            values = args[0]
            avg = sum(values) / len(values)
            return avg + stat_value

        raise DMError(f"Unknown stat function '{stat_func}'.")

    def run_plain_stat_function(self, name, args):
        if name == "endure":
            x, times, rate_percent = args
            rate = rate_percent / 100
            for _ in range(int(times)):
                x = x - (x * rate)
            return x
        if name == "perceive":
            values = args[0]
            return sum(values) / len(values)
        raise DMError(f"Unknown built-in '{name}'.")

    def eval_force(self, node, env):
        mode = node["mode"]
        symbol = node["symbol"]
        value = self.eval_expr(node["value"], env)
        stat_value = self.resolve_stat_value("STR", mode, node["instance"], env)
        return apply_math_symbol(stat_value, symbol, value)

    def eval_sway(self, node, env):
        if not self.block_stack:
            raise DMError("sway can't be used outside of a block.")
        frame = self.block_stack[-1]
        stmts = frame["statements"]

        address = self.eval_expr(node["address"], env)
        source_idx = int(address)
        if source_idx < 0 or source_idx >= len(stmts):
            raise DMError(f"There's no line at address {source_idx} to move.")
        if source_idx <= frame["index"]:
            raise DMError("You can't move a line that's already happened.")

        shift = self.resolve_shift(node["shift"], node["instance"], env)
        dest_idx = source_idx + int(shift)
        dest_idx = max(frame["index"] + 1, min(dest_idx, len(stmts) - 1))

        item = stmts.pop(source_idx)
        stmts.insert(dest_idx, item)
        return None

    def resolve_shift(self, shift_node, instance_node, env):
        if shift_node["type"] == "ShiftLiteral":
            return shift_node["value"]
        stat_name = shift_node["stat"] or "CHA"
        mode = shift_node["mode"]
        return self.resolve_stat_value(stat_name, mode, instance_node, env)

    def resolve_stat_value(self, stat_name, mode, instance_node, env):
        if instance_node is not None:
            instance = self.eval_expr(instance_node, env)
            if not isinstance(instance, dict) or "STATS" not in instance:
                raise DMError("That doesn't have STATS to use.")
            stats = instance["STATS"]
        else:
            stats = self.get_global_stats()
        if stat_name not in stats:
            raise DMError(f"'{stat_name}' isn't a stat there.")
        return stats[stat_name][mode]

    def eval_solve(self, node, env):
        instance = self.eval_expr(node["instance"], env)
        if not isinstance(instance, dict) or "STATS" not in instance:
            raise DMError("That doesn't have STATS to run a solve check with.")
        difficulty = self.eval_expr(node["difficulty"], env)
        die_size = instance["STATS"]["INT"][node["mode"]]

        roll_result = 0 if die_size <= 0 else random.randint(1, int(die_size))

        comparator = node["comparator"]
        if comparator == "/":
            result = roll_result > difficulty
        elif comparator == "_":
            result = roll_result == difficulty
        elif comparator == "\\":
            result = roll_result < difficulty
        elif comparator == "/_":
            result = roll_result >= difficulty
        elif comparator == "\\_":
            result = roll_result <= difficulty
        else:
            raise DMError(f"Unknown comparator '{comparator}'.")
        return result


def apply_math_symbol(a, symbol, b):
    if symbol == "+":
        return a + b
    if symbol == "-":
        return a - b
    if symbol == "*":
        return a * b
    if symbol == "/":
        if b == 0:
            raise DMError("You can't divide by zero.")
        return a / b
    if symbol == "%":
        if b == 0:
            raise DMError("You can't divide by zero.")
        return a % b
    raise DMError(f"Unknown math symbol '{symbol}'.")


def value_to_literal_node(val):
    """Turns a plain Python value into a literal AST node, so auto-filled
    placeholder fields can be re-evaluated normally on every summon()."""
    if isinstance(val, bool):
        return {"type": "BoolLiteral", "value": val}
    if isinstance(val, (int, float)):
        return {"type": "NumberLiteral", "value": val}
    if isinstance(val, list):
        return {"type": "ListLiteral", "elements": [value_to_literal_node(v) for v in val]}
    return {"type": "StringLiteral", "value": val}


def coerce_input(raw):
    """Try to turn player() input into a number if it looks like one."""
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


# ---------------------------------------------------------------------------
# v5 core additions
# ---------------------------------------------------------------------------

_ORIGINAL_EXEC_STATEMENT = Interpreter.exec_statement
_ORIGINAL_EVAL_EXPR = Interpreter.eval_expr
_ORIGINAL_CALL_BUILTIN = Interpreter.call_builtin
_ORIGINAL_RUN = Interpreter.run


def _address_statements(program_ast):
    """Attach the same major.minor addresses shown by the IDE gutter.

    Major numbers belong to top-level source lines. All indented source lines
    under that major share its major number and receive increasing minors.
    Multi-line control constructs reserve their visible `or_attempt`, `fail`,
    and `consider` header lines so executable lines stay aligned with the IDE.
    """
    major = -1

    def process_block(statements, major_number, counter):
        for stmt in statements:
            stmt["address"] = f"{major_number}.{counter[0]}"
            counter[0] += 1
            kind = stmt.get("type")

            if kind in ("Adventure", "While", "ForParty", "QuestDef"):
                process_block(stmt.get("body", []), major_number, counter)
            elif kind == "Attempt":
                clauses = stmt.get("clauses", [])
                if clauses:
                    process_block(clauses[0].get("body", []), major_number, counter)
                    for clause in clauses[1:]:
                        counter[0] += 1  # or_attempt header
                        process_block(clause.get("body", []), major_number, counter)
                if stmt.get("fail_body") is not None:
                    counter[0] += 1  # fail header
                    process_block(stmt.get("fail_body", []), major_number, counter)
            elif kind == "Submit":
                process_block(stmt.get("body", []), major_number, counter)
                for clause in stmt.get("considers", []):
                    counter[0] += 1  # consider header
                    process_block(clause.get("body", []), major_number, counter)

    for stmt in program_ast.get("body", []):
        major += 1
        stmt["address"] = str(major)
        process_block(stmt.get("body", []), major, [0])
        if stmt.get("type") == "Attempt":
            # The normal process above handled Attempt bodies with a fresh
            # counter, so restore the address stream by explicitly rebuilding
            # this major block below.
            counter = [0]
            def process_attempt_body(attempt_stmt):
                clauses = attempt_stmt.get("clauses", [])
                if clauses:
                    process_block(clauses[0].get("body", []), major, counter)
                    for clause in clauses[1:]:
                        counter[0] += 1
                        process_block(clause.get("body", []), major, counter)
                if attempt_stmt.get("fail_body") is not None:
                    counter[0] += 1
                    process_block(attempt_stmt.get("fail_body", []), major, counter)
            process_attempt_body(stmt)


def _v5_run(self, program_ast):
    _address_statements(program_ast)
    return _ORIGINAL_RUN(self, program_ast)


def _v5_exec_statement(self, stmt, env):
    try:
        if stmt.get("type") == "Assignment":
            target = stmt["target"]
            if target.get("type") == "FieldAccess":
                obj = self.eval_expr(target["obj"], env)
                field = target["field"]
                if isinstance(obj, list) and field.startswith("member_"):
                    value = self.eval_expr(stmt["value"], env)
                    index = self.resolve_member_index(field, env)
                    if index < 0:
                        raise DMError("A list position can't be negative.", stmt.get("address"))
                    if index >= len(obj):
                        obj.extend([None] * (index + 1 - len(obj)))
                    obj[index] = value
                    return
        return _ORIGINAL_EXEC_STATEMENT(self, stmt, env)
    except DMError as exc:
        # Preserve the most specific inner address when a nested call already
        # supplied one; otherwise attach the current executable source address.
        text = str(exc)
        if " (line " not in text and stmt.get("address") is not None:
            prefix = "That's not within your ability"
            message = text[len(prefix):].lstrip(": ") if text.startswith(prefix) else text
            raise DMError(message, stmt["address"]) from None
        raise


def _v5_eval_expr(self, node, env):
    if node.get("type") == "Identifier" and node.get("name") == "none":
        return None
    return _ORIGINAL_EVAL_EXPR(self, node, env)


def _v5_call_builtin(self, name, arg_nodes, env):
    if name in {"append", "push", "pop", "map", "filter", "contains", "index"}:
        return _v5_list_builtin(self, name, arg_nodes, env)
    return _ORIGINAL_CALL_BUILTIN(self, name, arg_nodes, env)


def _v5_list_builtin(self, name, arg_nodes, env):
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

        operation = arg_nodes[1]
        if operation.get("type") == "Identifier":
            op_name = operation["name"]
        elif operation.get("type") == "StringLiteral":
            op_name = operation["value"]
        else:
            raise DMError(f"'{name}' needs a quest name or Scroll as its operation.")

        if op_name not in self.quests:
            raise DMError(f"There's no quest called '{op_name}'.")

        result = []
        for item in values:
            transformed = self.call_quest(op_name, [{
                "type": "NumberLiteral", "value": item
            }] if isinstance(item, (int, float)) and not isinstance(item, bool) else [{
                "type": "BoolLiteral", "value": item
            }] if isinstance(item, bool) else [{
                "type": "StringLiteral", "value": item
            }] if isinstance(item, str) else [{
                "type": "ListLiteral", "elements": [
                    {"type": "NumberLiteral", "value": v} if isinstance(v, (int, float)) and not isinstance(v, bool)
                    else {"type": "BoolLiteral", "value": v} if isinstance(v, bool)
                    else {"type": "StringLiteral", "value": v}
                    for v in item
                ]
            }], env)
            if name == "map" or bool(transformed):
                result.append(transformed)
        return result

    raise DMError(f"There's no list built-in called '{name}'.")


def _v5_to_scroll(value):
    if value is None:
        return "none"
    return _ORIGINAL_TO_SCROLL(value)


_ORIGINAL_TO_SCROLL = to_scroll
Interpreter.run = _v5_run
Interpreter.exec_statement = _v5_exec_statement
Interpreter.eval_expr = _v5_eval_expr
Interpreter.call_builtin = _v5_call_builtin
to_scroll = _v5_to_scroll
