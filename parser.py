"""
Parser for the D&D-themed language.
Turns the token list from lexer.py into an AST (nested dicts), which
interpreter.py then walks and executes.
"""



class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos]

    def advance(self):
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def check(self, type_):
        return self.peek().type == type_

    def expect(self, type_):
        if not self.check(type_):
            tok = self.peek()
            raise SyntaxError(
                f"The DM expected {type_} but found {tok.type} ('{tok.value}') at line {tok.line}."
            )
        return self.advance()

    def skip_newlines(self):
        while self.check("NEWLINE"):
            self.advance()

    # ---- top level ----

    def parse_program(self):
        statements = []
        self.skip_newlines()
        while not self.check("EOF"):
            statements.append(self.parse_statement())
            self.skip_newlines()
        return {"type": "Program", "body": statements}

    def parse_block(self):
        self.expect(":")
        self.expect("NEWLINE")
        self.skip_newlines()
        self.expect("INDENT")
        statements = []
        self.skip_newlines()
        while not self.check("DEDENT") and not self.check("EOF"):
            statements.append(self.parse_statement())
            self.skip_newlines()
        self.expect("DEDENT")
        return statements

    # ---- statements ----

    def parse_statement(self):
        tok = self.peek()

        if tok.type == "ability":
            return self.parse_ability()
        if tok.type == "narrate":
            return self.parse_narrate()
        if tok.type == "attempt":
            return self.parse_attempt()
        if tok.type == "adventure":
            return self.parse_adventure()
        if tok.type == "quest":
            return self.parse_quest()
        if tok.type == "homebrew":
            return self.parse_homebrew()
        if tok.type == "summon":
            return self.parse_summon()
        if tok.type == "embark":
            node = self.parse_embark_expr()
            self.expect("NEWLINE")
            return {"type": "ExprStatement", "expr": node}
        if tok.type == "reward":
            return self.parse_reward()
        if tok.type == "init":
            return self.parse_init()
        if tok.type == "quit":
            self.advance()
            self.expect("NEWLINE")
            return {"type": "Quit"}
        if tok.type == "continue":
            self.advance()
            self.expect("NEWLINE")
            return {"type": "Continue"}
        if tok.type == "while":
            return self.parse_while()
        if tok.type == "for":
            return self.parse_for()
        if tok.type == "submit":
            return self.parse_submit()
        if tok.type == "ID" and tok.value == "STATS" and self.tokens[self.pos + 1].type == ":":
            return self.parse_global_stats()
        if tok.type == "ID":
            return self.parse_assignment_or_expr()

        raise SyntaxError(f"The DM doesn't know how to handle '{tok.value}' at line {tok.line}.")

    def parse_ability(self):
        self.expect("ability")
        name = self.expect("ID").value
        self.expect("=")
        value = self.parse_expr()
        self.expect("NEWLINE")
        return {"type": "AbilityDecl", "name": name, "value": value}

    def parse_assignment_or_expr(self):
        # could be: ID = expr / ID.field = expr / ID += expr / just an expr statement
        start = self.pos
        target = self.parse_postfix_target()
        if self.check("="):
            self.advance()
            value = self.parse_expr()
            self.expect("NEWLINE")
            return {"type": "Assignment", "target": target, "value": value}
        if self.check("+="):
            self.advance()
            rhs = self.parse_expr()
            self.expect("NEWLINE")
            # desugar `target += rhs` into `target = target + rhs`
            combined = {"type": "BinaryOp", "op": "+", "left": target, "right": rhs}
            return {"type": "Assignment", "target": target, "value": combined}
        else:
            # rewind and parse as a plain expression statement
            self.pos = start
            expr = self.parse_expr()
            self.expect("NEWLINE")
            return {"type": "ExprStatement", "expr": expr}

    def parse_postfix_target(self):
        name = self.expect("ID").value
        node = {"type": "Identifier", "name": name}
        while self.check("."):
            self.advance()
            field = self.expect("ID").value
            node = {"type": "FieldAccess", "obj": node, "field": field}
        return node

    def parse_narrate(self):
        self.expect("narrate")
        # supports both narrate(expr) and narrate expr
        if self.check("("):
            self.advance()
            value = self.parse_expr()
            self.expect(")")
        else:
            value = self.parse_expr()
        self.expect("NEWLINE")
        return {"type": "Narrate", "value": value}

    def parse_reward(self):
        self.expect("reward")
        value = self.parse_expr()
        self.expect("NEWLINE")
        return {"type": "Reword", "value": value}

    def parse_init(self):
        self.expect("init")
        names = [self.expect("ID").value]
        while self.check(","):
            self.advance()
            names.append(self.expect("ID").value)
        self.expect("NEWLINE")
        return {"type": "Init", "names": names}

    def parse_attempt(self):
        self.expect("attempt")
        self.expect("(")
        condition = self.parse_expr()
        self.expect(")")
        body = self.parse_block()
        clauses = [{"condition": condition, "body": body}]
        fail_body = None

        while self.check("or_attempt"):
            self.advance()
            self.expect("(")
            cond = self.parse_expr()
            self.expect(")")
            b = self.parse_block()
            clauses.append({"condition": cond, "body": b})

        if self.check("fail"):
            self.advance()
            fail_body = self.parse_block()

        return {"type": "Attempt", "clauses": clauses, "fail_body": fail_body}

    def parse_adventure(self):
        self.expect("adventure")
        self.expect("(")
        count = self.parse_expr()
        self.expect(")")
        body = self.parse_block()
        return {"type": "Adventure", "count": count, "body": body}

    def parse_quest(self):
        self.expect("quest")
        name = self.expect("ID").value
        self.expect("(")
        params = []
        if not self.check(")"):
            params.append(self.expect("ID").value)
            while self.check(","):
                self.advance()
                params.append(self.expect("ID").value)
        self.expect(")")
        body = self.parse_block()
        return {"type": "QuestDef", "name": name, "params": params, "body": body}

    def parse_embark_expr(self):
        self.expect("embark")
        name = self.expect("ID").value
        self.expect("(")
        args = []
        if not self.check(")"):
            args.append(self.parse_expr())
            while self.check(","):
                self.advance()
                args.append(self.parse_expr())
        self.expect(")")
        return {"type": "Embark", "name": name, "args": args}

    def parse_homebrew(self):
        self.expect("homebrew")
        kind = self.expect("ID").value
        name = self.expect("ID").value
        self.expect(":")
        self.expect("NEWLINE")
        self.expect("INDENT")
        fields = {}
        stats = {}
        extra_stats = {}
        self.skip_newlines()
        while not self.check("DEDENT"):
            if self.check("ID") and self.peek().value == "STATS":
                self.advance()
                stats, extra_stats = self.parse_stats_block()
            else:
                fname = self.expect("ID").value
                self.expect("=")
                fexpr = self.parse_expr()
                self.expect("NEWLINE")
                fields[fname] = fexpr
            self.skip_newlines()
        self.expect("DEDENT")
        return {"type": "HomebrewDef", "kind": kind, "name": name,
                "fields": fields, "stats": stats, "extra_stats": extra_stats}

    def parse_stats_block(self):
        """Shared by homebrew's STATS sub-block and the top-level global STATS block."""
        self.expect(":")
        self.expect("NEWLINE")
        self.expect("INDENT")
        stats = {}
        extra_stats = {}
        self.skip_newlines()
        while not self.check("DEDENT"):
            if self.check("extra"):
                self.advance()
                ename = self.expect("ID").value
                self.expect("=")
                eexpr = self.parse_expr()
                self.expect("NEWLINE")
                extra_stats[ename] = eexpr
            else:
                sname = self.expect("ID").value
                self.expect("=")
                sexpr = self.parse_expr()
                self.expect("NEWLINE")
                stats[sname] = sexpr
            self.skip_newlines()
        self.expect("DEDENT")
        return stats, extra_stats

    def parse_global_stats(self):
        self.advance()  # consume the 'STATS' identifier token
        stats, extra_stats = self.parse_stats_block()
        return {"type": "GlobalStats", "stats": stats, "extra_stats": extra_stats}

    def parse_summon(self):
        self.expect("summon")
        var_name = self.expect("ID").value
        self.expect("=")
        template_name = self.expect("ID").value
        self.expect("(")
        self.expect(")")
        self.expect("NEWLINE")
        return {"type": "SummonDecl", "var_name": var_name, "template": template_name}

    def parse_while(self):
        self.expect("while")
        condition = self.parse_expr()
        body = self.parse_block()
        return {"type": "While", "condition": condition, "body": body}

    def parse_for(self):
        self.expect("for")
        var_name = self.expect("ID").value
        self.expect("in")
        self.expect("party")
        self.expect("(")
        args = [self.parse_expr()]
        while self.check(","):
            self.advance()
            args.append(self.parse_expr())
        self.expect(")")
        body = self.parse_block()
        return {"type": "ForParty", "var": var_name, "args": args, "body": body}

    def parse_submit(self):
        self.expect("submit")
        body = self.parse_block()
        considers = []
        while self.check("consider"):
            self.advance()
            error_name = None
            if self.check("issue"):
                self.advance()
                error_name = self.expect("ID").value
            cbody = self.parse_block()
            considers.append({"error_name": error_name, "body": cbody})
        return {"type": "Submit", "body": body, "considers": considers}

    # ---- expressions (precedence climbing) ----

    def parse_expr(self):
        return self.parse_comparison()

    def parse_comparison(self):
        left = self.parse_additive()
        while self.peek().type in ("==", "!=", ">", "<", ">=", "<="):
            op = self.advance().type
            right = self.parse_additive()
            left = {"type": "BinaryOp", "op": op, "left": left, "right": right}
        return left

    def parse_additive(self):
        left = self.parse_multiplicative()
        while self.peek().type in ("+", "-"):
            op = self.advance().type
            right = self.parse_multiplicative()
            left = {"type": "BinaryOp", "op": op, "left": left, "right": right}
        return left

    def parse_multiplicative(self):
        left = self.parse_unary()
        while self.peek().type in ("*", "/", "%"):
            op = self.advance().type
            right = self.parse_unary()
            left = {"type": "BinaryOp", "op": op, "left": left, "right": right}
        return left

    def parse_unary(self):
        if self.peek().type == "-":
            self.advance()
            operand = self.parse_unary()
            return {"type": "UnaryOp", "op": "-", "operand": operand}
        if self.peek().type == "+":
            self.advance()
            return self.parse_unary()  # unary plus is a no-op
        return self.parse_postfix()

    def parse_force_call(self, instance):
        """Called right after the 'force' identifier. Handles force.mod(SYMBOL, x)
        or force.number(SYMBOL, x) — SYMBOL is a bare math operator token."""
        self.expect(".")
        mode = self.expect("ID").value  # 'mod' or 'number'
        self.expect("(")
        symbol_tok = self.advance()
        if symbol_tok.type not in ("+", "-", "*", "/", "%"):
            raise SyntaxError(
                f"The DM expected a math symbol (+ - * / %) but found "
                f"'{symbol_tok.value}' at line {symbol_tok.line}."
            )
        self.expect(",")
        value_expr = self.parse_expr()
        self.expect(")")
        return {"type": "ForceExpr", "instance": instance, "mode": mode,
                "symbol": symbol_tok.type, "value": value_expr}

    def parse_sway_call(self, instance):
        """Called right after the 'sway' identifier. Handles sway(address, shift)."""
        self.expect("(")
        address_expr = self.parse_expr()
        self.expect(",")
        shift_node = self.parse_shift_spec()
        self.expect(")")
        return {"type": "SwayExpr", "instance": instance, "address": address_expr, "shift": shift_node}

    def parse_shift_spec(self):
        """Parses a sway shift: an explicit signed number, a bare mod/number
        (uses the instance's own CHA), or STATNAME.mod / STATNAME.number
        (uses a different named stat on that instance)."""
        if self.peek().type in ("+", "-"):
            sign = self.advance().type
            num_tok = self.expect("NUMBER")
            value = num_tok.value if sign == "+" else -num_tok.value
            return {"type": "ShiftLiteral", "value": value}
        if self.check("NUMBER"):
            num_tok = self.advance()
            return {"type": "ShiftLiteral", "value": num_tok.value}
        name = self.expect("ID").value
        if name in ("mod", "number") and not self.check("."):
            return {"type": "ShiftStatRef", "stat": None, "mode": name}
        if self.check("."):
            self.advance()
            mode = self.expect("ID").value
            return {"type": "ShiftStatRef", "stat": name, "mode": mode}
        raise SyntaxError(f"The DM doesn't understand the shift '{name}' at line {self.peek().line}.")

    def parse_postfix(self):
        node = self.parse_primary()
        while True:
            if self.check("."):
                self.advance()
                field = self.expect("ID").value
                if field == "solve" and self.check("."):
                    self.advance()
                    mode = self.expect("ID").value  # 'mod' or 'number'
                    comparator = ""
                    while self.peek().type in ("/", "_", "\\"):
                        comparator += self.advance().type
                    if comparator == "":
                        comparator = "/_"
                    self.expect("(")
                    difficulty = self.parse_expr()
                    self.expect(")")
                    node = {"type": "SolveExpr", "instance": node, "mode": mode,
                            "comparator": comparator, "difficulty": difficulty}
                    continue
                if field == "force" and self.check("."):
                    node = self.parse_force_call(instance=node)
                    continue
                if field == "sway" and self.check("("):
                    node = self.parse_sway_call(instance=node)
                    continue
                node = {"type": "FieldAccess", "obj": node, "field": field}
            elif self.check("("):
                self.advance()
                args = []
                if not self.check(")"):
                    args.append(self.parse_expr())
                    while self.check(","):
                        self.advance()
                        args.append(self.parse_expr())
                self.expect(")")
                node = {"type": "CallExpr", "callee": node, "args": args}
            else:
                break
        return node

    def parse_primary(self):
        tok = self.peek()

        if tok.type == "NUMBER":
            self.advance()
            return {"type": "NumberLiteral", "value": tok.value}
        if tok.type == "STRING":
            self.advance()
            return {"type": "StringLiteral", "value": tok.value}
        if tok.type == "honor":
            self.advance()
            return {"type": "BoolLiteral", "value": True}
        if tok.type == "lie":
            self.advance()
            return {"type": "BoolLiteral", "value": False}
        if tok.type == "DICE":
            self.advance()
            return {"type": "DiceLiteral", "max": tok.value}
        if tok.type == "player":
            self.advance()
            self.expect("(")
            prompt = self.parse_expr()
            self.expect(")")
            return {"type": "PlayerInput", "prompt": prompt}
        if tok.type == "embark":
            return self.parse_embark_expr()
        if tok.type == "[":
            self.advance()
            elements = []
            if not self.check("]"):
                elements.append(self.parse_expr())
                while self.check(","):
                    self.advance()
                    elements.append(self.parse_expr())
            self.expect("]")
            return {"type": "ListLiteral", "elements": elements}
        if tok.type == "(":
            self.advance()
            expr = self.parse_expr()
            self.expect(")")
            return expr
        if tok.type == "ID":
            self.advance()
            name = tok.value
            if name == "force" and self.check("."):
                return self.parse_force_call(instance=None)
            if name == "sway" and self.check("("):
                return self.parse_sway_call(instance=None)
            if self.check("("):
                self.advance()
                args = []
                if not self.check(")"):
                    args.append(self.parse_expr())
                    while self.check(","):
                        self.advance()
                        args.append(self.parse_expr())
                self.expect(")")
                return {"type": "Call", "name": name, "args": args}
            return {"type": "Identifier", "name": name}

        raise SyntaxError(f"The DM doesn't understand '{tok.value}' at line {tok.line}.")


def parse(tokens):
    return Parser(tokens).parse_program()
