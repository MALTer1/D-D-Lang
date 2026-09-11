import re

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self): return self.tokens[self.pos]
    def advance(self):
        t = self.tokens[self.pos]; self.pos += 1; return t
    def check(self, t): return self.peek().type == t

    def expect(self, t):
        if not self.check(t):
            x = self.peek(); a = getattr(x, "address", None)
            loc = f"line {x.line} (address {a})" if a not in (None, "") else f"line {x.line}"
            raise SyntaxError(f"The DM expected {t} but found {x.type} ('{x.value}') at {loc}.")
        return self.advance()
    def skip_newlines(self):
        while self.check("NEWLINE"): self.advance()
    def parse_program(self):
        b=[]; self.skip_newlines()
        while not self.check("EOF"): b.append(self.parse_statement()); self.skip_newlines()
        return {"type":"Program","body":b}
    def parse_block(self):
        self.expect(":"); self.expect("NEWLINE"); self.skip_newlines(); self.expect("INDENT"); b=[]
        while not self.check("DEDENT") and not self.check("EOF"): b.append(self.parse_statement()); self.skip_newlines()
        self.expect("DEDENT"); return b
    def parse_statement(self):
        t=self.peek().type
        if t in ("ability","pouch"): return self.parse_var_decl(t)
        if t=="vault": return self.parse_vault()
        if t=="narrate": return self.parse_narrate()
        if t=="attempt": return self.parse_attempt()
        if t=="adventure": return self.parse_adventure()
        if t=="quest": return self.parse_quest()
        if t=="homebrew": return self.parse_homebrew()
        if t=="summon": return self.parse_summon()
        if t=="embark": n=self.parse_embark_expr(); self.expect("NEWLINE"); return {"type":"ExprStatement","expr":n}
        if t=="reward": self.advance(); v=self.parse_expr(); self.expect("NEWLINE"); return {"type":"Reword","value":v}
        if t=="init":
            self.advance(); ns=[self.expect("ID").value]
            while self.check(","): self.advance(); ns.append(self.expect("ID").value)
            self.expect("NEWLINE"); return {"type":"Init","names":ns}
        if t=="quit": self.advance(); self.expect("NEWLINE"); return {"type":"Quit"}
        if t=="continue": self.advance(); self.expect("NEWLINE"); return {"type":"Continue"}
        if t=="pass": self.advance(); self.expect("NEWLINE"); return {"type":"Pass"}
        if t=="raise": self.advance(); v=self.parse_expr(); self.expect("NEWLINE"); return {"type":"Raise","value":v}
        if t=="while": self.expect("while"); c=self.parse_expr(); return {"type":"While","condition":c,"body":self.parse_block()}
        if t=="for": return self.parse_for()
        if t=="submit": return self.parse_submit()
        if t=="ID" and self.peek().value=="STATS" and self.tokens[self.pos+1].type==":": return self.parse_global_stats()
        if t=="ID": return self.parse_assignment_or_expr()
        raise SyntaxError(f"The DM doesn't know how to handle '{self.peek().value}' at line {self.peek().line}.")
    def parse_var_decl(self,k):
        self.expect(k); n=self.expect("ID").value; self.expect("="); v=self.parse_expr()
        if k=="pouch" and v.get("type")!="PouchLiteral": raise SyntaxError("The DM expects a pouch to be written as key-value pairs inside { }.")
        self.expect("NEWLINE"); return {"type":"AbilityDecl" if k=="ability" else "PouchDecl","name":n,"value":v}
    def parse_vault(self): self.expect("vault"); n=self.expect("ID").value; self.expect("="); p=self.parse_expr(); self.expect("NEWLINE"); return {"type":"VaultDecl","name":n,"path":p}
    def parse_assignment_or_expr(self):
        s=self.pos; t=self.parse_target()
        if self.check("="): self.advance(); v=self.parse_expr(); self.expect("NEWLINE"); return {"type":"Assignment","target":t,"value":v,"operator":"="}
        if self.peek().type in ("+=","-=","*=","/=","%="):
            op=self.advance().type; r=self.parse_expr(); self.expect("NEWLINE"); return {"type":"Assignment","target":t,"value":r,"operator":op}
        self.pos=s; e=self.parse_expr(); self.expect("NEWLINE"); return {"type":"ExprStatement","expr":e}
    def parse_target(self):
        n={"type":"Identifier","name":self.expect("ID").value}
        while self.check(".") or self.check("["):
            if self.check("."): self.advance(); n={"type":"FieldAccess","obj":n,"field":self.expect("ID").value}
            else: self.advance(); i=self.parse_expr(); self.expect("]"); n={"type":"IndexAccess","obj":n,"index":i}
        return n
    def parse_narrate(self):
        self.expect("narrate")
        if self.check("("): self.advance(); v=self.parse_expr(); self.expect(")")
        else: v=self.parse_expr()
        self.expect("NEWLINE"); return {"type":"Narrate","value":v}
    def parse_attempt(self):
        self.expect("attempt"); self.expect("("); c=self.parse_expr(); self.expect(")"); clauses=[{"condition":c,"body":self.parse_block()}]; f=None
        while self.check("or_attempt"):
            self.advance(); self.expect("("); c=self.parse_expr(); self.expect(")"); clauses.append({"condition":c,"body":self.parse_block()})
        if self.check("fail"): self.advance(); f=self.parse_block()
        return {"type":"Attempt","clauses":clauses,"fail_body":f}
    def parse_adventure(self):
        self.expect("adventure")
        if self.check("("): self.advance(); c=self.parse_expr(); self.expect(")"); return {"type":"Adventure","count":c,"body":self.parse_block()}
        n=self.expect("ID").value; self.expect("in"); x=self.parse_expr(); return {"type":"ForParty","var":n,"args":[x],"body":self.parse_block()}
    def parse_quest(self):
        self.expect("quest"); n=self.expect("ID").value; self.expect("("); p=[]
        if not self.check(")"):
            p.append(self.expect("ID").value)
            while self.check(","): self.advance(); p.append(self.expect("ID").value)
        self.expect(")"); return {"type":"QuestDef","name":n,"params":p,"body":self.parse_block()}
    def parse_embark_expr(self):
        self.expect("embark"); n=self.expect("ID").value; self.expect("("); a=[]
        if not self.check(")"):
            a.append(self.parse_expr())
            while self.check(","): self.advance(); a.append(self.parse_expr())
        self.expect(")"); return {"type":"Embark","name":n,"args":a}
    def parse_homebrew(self):
        self.expect("homebrew"); k=self.expect("ID").value; n=self.expect("ID").value; self.expect(":"); self.expect("NEWLINE"); self.expect("INDENT"); f={}; s={}; e={}
        while not self.check("DEDENT"):
            if self.check("ID") and self.peek().value=="STATS": self.advance(); s,e=self.parse_stats_block()
            else: q=self.expect("ID").value; self.expect("="); f[q]=self.parse_expr(); self.expect("NEWLINE")
            self.skip_newlines()
        self.expect("DEDENT"); return {"type":"HomebrewDef","kind":k,"name":n,"fields":f,"stats":s,"extra_stats":e}
    def parse_stats_block(self):
        self.expect(":"); self.expect("NEWLINE"); self.expect("INDENT"); s={}; e={}
        while not self.check("DEDENT"):
            if self.check("extra"): self.advance(); n=self.expect("ID").value; self.expect("="); e[n]=self.parse_expr(); self.expect("NEWLINE")
            else: n=self.expect("ID").value; self.expect("="); s[n]=self.parse_expr(); self.expect("NEWLINE")
            self.skip_newlines()
        self.expect("DEDENT"); return s,e
    def parse_global_stats(self): self.advance(); s,e=self.parse_stats_block(); return {"type":"GlobalStats","stats":s,"extra_stats":e}
    def parse_summon(self): self.expect("summon"); v=self.expect("ID").value; self.expect("="); n=self.expect("ID").value; self.expect("("); self.expect(")"); self.expect("NEWLINE"); return {"type":"SummonDecl","var_name":v,"template":n}
    def parse_for(self):
        self.expect("for"); v=self.expect("ID").value; self.expect("in"); self.expect("party"); self.expect("("); a=[self.parse_expr()]
        while self.check(","): self.advance(); a.append(self.parse_expr())
        self.expect(")"); return {"type":"ForParty","var":v,"args":a,"body":self.parse_block()}
    def parse_submit(self):
        self.expect("submit"); b=self.parse_block(); c=[]
        while self.check("consider"):
            self.advance(); n=None
            if self.check("issue"): self.advance(); n=self.expect("ID").value
            c.append({"error_name":n,"body":self.parse_block()})
        f=None
        if self.check("finally"): self.advance(); f=self.parse_block()
        return {"type":"Submit","body":b,"considers":c,"finally_body":f}
    def parse_expr(self): return self.parse_comparison()
    def parse_comparison(self):
        n=self.parse_additive()
        while self.peek().type in ("==","!=",">","<",">=","<="):
            o=self.advance().type; r=self.parse_additive(); n={"type":"BinaryOp","op":o,"left":n,"right":r}
        return n
    def parse_additive(self):
        n=self.parse_multiplicative()
        while self.peek().type in ("+","-"):
            o=self.advance().type; r=self.parse_multiplicative(); n={"type":"BinaryOp","op":o,"left":n,"right":r}
        return n
    def parse_multiplicative(self):
        n=self.parse_unary()
        while self.peek().type in ("*","/","%"):
            o=self.advance().type; r=self.parse_unary(); n={"type":"BinaryOp","op":o,"left":n,"right":r}
        return n
    def parse_unary(self):
        if self.check("-"): self.advance(); return {"type":"UnaryOp","op":"-","operand":self.parse_unary()}
        if self.check("+"): self.advance(); return self.parse_unary()
        return self.parse_postfix()
    def parse_postfix(self):
        n=self.parse_primary()
        while True:
            if self.check("."):
                self.advance(); f=self.expect("ID").value
                if f=="solve" and self.check("."):
                    self.advance(); m=self.expect("ID").value; c=""
                    while self.peek().type in ("/","_","\\"): c+=self.advance().type
                    if not c: c="/_"
                    self.expect("("); d=self.parse_expr(); self.expect(")"); n={"type":"SolveExpr","instance":n,"mode":m,"comparator":c,"difficulty":d}
                elif f=="force" and self.check("."): n=self.parse_force_call(n)
                elif f=="sway" and self.check("("): n=self.parse_sway_call(n)
                else: n={"type":"FieldAccess","obj":n,"field":f}
            elif self.check("["):
                self.advance(); i=self.parse_expr(); self.expect("]"); n={"type":"IndexAccess","obj":n,"index":i}
            elif self.check("("):
                self.advance(); a=[]
                if not self.check(")"):
                    a.append(self.parse_expr())
                    while self.check(","): self.advance(); a.append(self.parse_expr())
                self.expect(")"); n={"type":"CallExpr","callee":n,"args":a}
            else: break
        return n
    def parse_force_call(self,i):
        self.expect("."); m=self.expect("ID").value; self.expect("("); s=self.advance()
        if s.type not in ("+","-","*","/","%"): raise SyntaxError("The DM expected a math symbol.")
        self.expect(","); v=self.parse_expr(); self.expect(")"); return {"type":"ForceExpr","instance":i,"mode":m,"symbol":s.type,"value":v}
    def parse_sway_call(self,i):
        self.expect("(")
        if self.check("STRING"):
            raw=self.advance().value
            if not re.fullmatch(r"\d+(?:\.\d+)?",raw): raise SyntaxError("The DM expects a sway address such as 3 or 3.1.")
            a={"type":"AddressLiteral","value":raw}
        elif self.check("NUMBER") and isinstance(self.peek().value,float):
            a={"type":"AddressLiteral","value":str(self.advance().value)}
        else: a=self.parse_expr()
        self.expect(","); q=self.parse_shift_spec(); self.expect(")"); return {"type":"SwayExpr","instance":i,"address":a,"shift":q}
    def parse_shift_spec(self):
        if self.peek().type in ("+","-"): s=self.advance().type; n=self.expect("NUMBER").value; return {"type":"ShiftLiteral","value":n if s=="+" else -n}
        if self.check("NUMBER"): return {"type":"ShiftLiteral","value":self.advance().value}
        n=self.expect("ID").value
        if n in ("mod","number") and not self.check("."): return {"type":"ShiftStatRef","stat":None,"mode":n}
        if self.check("."): self.advance(); return {"type":"ShiftStatRef","stat":n,"mode":self.expect("ID").value}
        raise SyntaxError("The DM does not understand that sway shift.")
    def parse_primary(self):
        t=self.peek()
        if t.type=="NUMBER": self.advance(); return {"type":"NumberLiteral","value":t.value}
        if t.type=="STRING": self.advance(); return {"type":"StringLiteral","value":t.value}
        if t.type=="honor": self.advance(); return {"type":"BoolLiteral","value":True}
        if t.type=="lie": self.advance(); return {"type":"BoolLiteral","value":False}
        if t.type=="none": self.advance(); return {"type":"NoneLiteral"}
        if t.type=="DICE": self.advance(); return {"type":"DiceLiteral","max":t.value}
        if t.type=="player": self.advance(); self.expect("("); p=self.parse_expr(); self.expect(")"); return {"type":"PlayerInput","prompt":p}
        if t.type=="embark": return self.parse_embark_expr()
        if t.type=="[":
            self.advance(); a=[]
            if not self.check("]"):
                a.append(self.parse_expr())
                while self.check(","): self.advance(); a.append(self.parse_expr())
            self.expect("]"); return {"type":"ListLiteral","elements":a}
        if t.type=="{":
            self.advance(); a=[]
            if not self.check("}"):
                k=self.parse_expr(); self.expect(":"); v=self.parse_expr(); a.append((k,v))
                while self.check(","):
                    self.advance()
                    if self.check("}"): break
                    k=self.parse_expr(); self.expect(":"); v=self.parse_expr(); a.append((k,v))
            self.expect("}"); return {"type":"PouchLiteral","pairs":a}
        if t.type=="(": self.advance(); n=self.parse_expr(); self.expect(")"); return n
        if t.type=="ID": self.advance(); return {"type":"Identifier","name":t.value}
        raise SyntaxError(f"The DM doesn't understand '{t.value}' at line {t.line}.")

def parse(tokens): return Parser(tokens).parse_program()
