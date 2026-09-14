import math
import os
import random

class DMError(Exception):
    def __init__(self, message, line=None):
        loc=f" (line {line})" if line is not None else ""
        super().__init__(f"That's not within your ability{loc}: {message}")
class QuitSignal(Exception): pass
class ContinueSignal(Exception): pass
class RewordSignal(Exception):
    def __init__(self,value): self.value=value
class VaultHandle:
    def __init__(self,path): self.path=os.fspath(path); self.closed=False
    def check(self):
        if self.closed: raise DMError("That vault has already been sealed.")

SHAPE_RULES={"character":{"min_total":3,"min_types":2,"max_per_type":2},"item":{"min_total":2,"min_types":2,"max_per_type":1},"monster":{"min_total":2,"min_types":2,"max_per_type":1},"spell":{"min_total":2,"min_types":2,"max_per_type":1}}
DEFAULT_STAT_NAMES=["STR","DEX","CON","INT","WIS","CHA"]
STAT_FUNC_TO_STAT={"endure":"CON","perceive":"WIS"}

def classify_value(v):
    if v is None:return "NoneType"
    if isinstance(v,bool):return "honor/lie"
    if isinstance(v,(int,float)):return "number"
    if isinstance(v,str):return "Scroll"
    if isinstance(v,list):return "list"
    if isinstance(v,dict):return "pouch"
    if isinstance(v,VaultHandle):return "vault"
    return "unknown"

def to_scroll(v):
    if v is None:return "none"
    if v is True:return "honor"
    if v is False:return "lie"
    if isinstance(v,VaultHandle):return v.path
    return str(v)

def value_to_literal_node(v):
    if v is None:return {"type":"NoneLiteral"}
    if isinstance(v,bool):return {"type":"BoolLiteral","value":v}
    if isinstance(v,(int,float)):return {"type":"NumberLiteral","value":v}
    if isinstance(v,list):return {"type":"ListLiteral","elements":[value_to_literal_node(x) for x in v]}
    if isinstance(v,dict):return {"type":"PouchLiteral","pairs":[(value_to_literal_node(k),value_to_literal_node(x)) for k,x in v.items()]}
    return {"type":"StringLiteral","value":to_scroll(v)}

class Environment:
    def __init__(self,parent=None):self.vars={};self.parent=parent
    def get(self,name):
        if name in self.vars:return self.vars[name]
        if self.parent is not None:return self.parent.get(name)
        raise DMError(f"'{name}' hasn't been declared with 'ability', 'pouch', or 'vault'.")
    def set_existing(self,name,value):
        e=self
        while e is not None:
            if name in e.vars:e.vars[name]=value;return
            e=e.parent
        self.vars[name]=value
    def declare(self,name,value):self.vars[name]=value
    def forget(self,name):
        e=self
        while e is not None:
            if name in e.vars:del e.vars[name];return True
            e=e.parent
        return False

class Interpreter:
    def __init__(self,output_func=print,input_func=input):
        self.global_env=Environment();self.quests={};self.homebrews={};self.output_func=output_func;self.input_func=input_func;self.caller_stack=[];self.global_stats=None;self.block_stack=[]
    def run(self,program_ast):self.exec_block(program_ast["body"],self.global_env)
    def exec_block(self,statements,env):
        frame={"statements":list(statements),"index":0};self.block_stack.append(frame)
        try:
            while frame["index"]<len(frame["statements"]):
                self.exec_statement(frame["statements"][frame["index"]],env);frame["index"]+=1
        finally:self.block_stack.pop()
    def exec_statement(self,stmt,env):
        kind=stmt["type"]
        if kind in ("AbilityDecl","PouchDecl"):env.declare(stmt["name"],self.eval_expr(stmt["value"],env))
        elif kind=="VaultDecl":env.declare(stmt["name"],VaultHandle(to_scroll(self.eval_expr(stmt["path"],env))))
        elif kind=="Assignment":
            value=self.eval_expr(stmt["value"],env); op=stmt.get("operator","=")
            if op=="=": self.assign_target(stmt["target"],value,env)
            else:self.assign_target(stmt["target"],self.apply_binary_values(self.eval_expr(stmt["target"],env),value,op[0]),env)
        elif kind=="Narrate":self.output_func(to_scroll(self.eval_expr(stmt["value"],env)))
        elif kind=="Attempt":
            for c in stmt["clauses"]:
                if self.eval_expr(c["condition"],env):self.exec_block(c["body"],Environment(parent=env));return
            if stmt["fail_body"] is not None:self.exec_block(stmt["fail_body"],Environment(parent=env))
        elif kind=="Adventure":
            try:
                for _ in range(int(self.eval_expr(stmt["count"],env))):
                    try:self.exec_block(stmt["body"],Environment(parent=env))
                    except ContinueSignal:continue
            except QuitSignal:pass
        elif kind=="While":
            try:
                while self.eval_expr(stmt["condition"],env):
                    try:self.exec_block(stmt["body"],Environment(parent=env))
                    except ContinueSignal:continue
            except QuitSignal:pass
        elif kind=="ForParty":
            try:
                for item in self.resolve_party(stmt["args"],env):
                    inner=Environment(parent=env);inner.declare(stmt["var"],item)
                    try:self.exec_block(stmt["body"],inner)
                    except ContinueSignal:continue
            except QuitSignal:pass
        elif kind=="Submit":self.exec_submit(stmt,env)
        elif kind=="Quit":raise QuitSignal()
        elif kind=="Continue":raise ContinueSignal()
        elif kind=="Pass":pass
        elif kind=="Raise":raise DMError(to_scroll(self.eval_expr(stmt["value"],env)))
        elif kind=="QuestDef":self.quests[stmt["name"]]=stmt
        elif kind=="HomebrewDef":self.define_homebrew(stmt,env)
        elif kind=="GlobalStats":self.global_stats=self.build_stats(stmt["stats"],stmt["extra_stats"],env)
        elif kind=="SummonDecl":self.exec_summon(stmt,env)
        elif kind=="Reword":raise RewordSignal(self.eval_expr(stmt["value"],env))
        elif kind=="Init":
            if not self.caller_stack:raise DMError("'init' can't be used outside of a quest.")
            caller=self.caller_stack[-1]
            for name in stmt["names"]:env.declare(name,caller.get(name))
        elif kind=="ExprStatement":self.eval_expr(stmt["expr"],env)
        else:raise DMError(f"Unknown statement type '{kind}'.")
    def assign_target(self,t,v,env):
        if t["type"]=="Identifier":env.set_existing(t["name"],v);return
        if t["type"]=="FieldAccess":
            o=self.eval_expr(t["obj"],env)
            if not isinstance(o,dict):raise DMError("That's not something you can assign a field on.")
            o[t["field"]]=v;return
        if t["type"]=="IndexAccess":self.assign_index(self.eval_expr(t["obj"],env),self.eval_expr(t["index"],env),v);return
        raise DMError("That's not something you can assign to.")
    def assign_index(self,o,i,v):
        if isinstance(o,list):
            i=int(i)
            if i<0:raise DMError("A list position can't be negative.")
            if i>=len(o):o.extend([None]*(i+1-len(o)))
            o[i]=v
        elif isinstance(o,dict):o[i]=v
        else:raise DMError("Only lists and pouches can be indexed for assignment.")
    def eval_expr(self,n,env):
        k=n["type"]
        if k=="NumberLiteral":return n["value"]
        if k=="StringLiteral":return n["value"]
        if k=="BoolLiteral":return n["value"]
        if k=="NoneLiteral":return None
        if k=="AddressLiteral":return n["value"]
        if k=="ListLiteral":return [self.eval_expr(x,env) for x in n["elements"]]
        if k=="PouchLiteral":return {self.eval_expr(a,env):self.eval_expr(b,env) for a,b in n["pairs"]}
        if k=="DiceLiteral":return n["max"]
        if k=="Identifier":return env.get(n["name"])
        if k=="FieldAccess":
            o=self.eval_expr(n["obj"],env);f=n["field"]
            if isinstance(o,dict) and f in o:return o[f]
            if isinstance(o,list) and f.startswith('member_'):return self.index_value(o,self.resolve_member_index(f,env))
            raise DMError(f"'{f}' isn't a field on that thing.")
        if k=="IndexAccess":return self.index_value(self.eval_expr(n["obj"],env),self.eval_expr(n["index"],env))
        if k=="PlayerInput":return coerce_input(self.input_func(to_scroll(self.eval_expr(n["prompt"],env))))
        if k=="UnaryOp":return -self.eval_expr(n["operand"],env) if n["op"]=='-' else self.eval_expr(n["operand"],env)
        if k=="BinaryOp":return self.eval_binary(n,env)
        if k=="Embark":return self.call_quest(n["name"],n["args"],env)
        if k=="Call":return self.call_builtin(n["name"],n["args"],env)
        if k=="CallExpr":return self.eval_call_expr(n,env)
        if k=="SolveExpr":return self.eval_solve(n,env)
        if k=="ForceExpr":return self.eval_force(n,env)
        if k=="SwayExpr":return self.eval_sway(n,env)
        raise DMError(f"Unknown expression type '{k}'.")
    def index_value(self,o,i):
        if isinstance(o,(list,str)):
            try:return o[int(i)]
            except (IndexError,ValueError):raise DMError(f"There's no item at position {i} in that sequence.")
        if isinstance(o,dict):
            if i not in o:raise DMError(f"That pouch has no key '{to_scroll(i)}'.")
            return o[i]
        raise DMError("Only lists, Scrolls, and pouches can be indexed.")
    def apply_binary_values(self,a,b,o):
        if o=='+':return to_scroll(a)+to_scroll(b) if isinstance(a,str) or isinstance(b,str) else a+b
        if o=='-':return a-b
        if o=='*':return a*b
        if o in ('/','%') and b==0:raise DMError("You can't divide by zero.")
        if o=='/':return a/b
        if o=='%':return a%b
        if o=='==':return a==b
        if o=='!=':return a!=b
        # `none` is a missing/empty value. Ordering a missing value against a concrete value is a non-match.
        if a is None or b is None:
            if o in ('>','<','>=','<='):return False
        if o=='>':return a>b
        if o=='<':return a<b
        if o=='>=':return a>=b
        if o=='<=':return a<=b
        raise DMError(f"Unknown operator '{o}'.")
    def eval_binary(self,n,env):return self.apply_binary_values(self.eval_expr(n['left'],env),self.eval_expr(n['right'],env),n['op'])
    def call_quest(self,name,nodes,env):
        actual_name=name
        if actual_name not in self.quests:
            try:candidate=env.get(name)
            except DMError:candidate=None
            if isinstance(candidate,str) and candidate in self.quests:actual_name=candidate
        if actual_name not in self.quests:raise DMError(f"There's no quest called '{name}'.")
        q=self.quests[actual_name];args=[self.eval_expr(x,env) for x in nodes];qe=Environment(parent=env)
        for p,a in zip(q['params'],args):qe.declare(p,a)
        self.caller_stack.append(env)
        try:self.exec_block(q['body'],qe);return None
        except RewordSignal as r:return r.value
        finally:self.caller_stack.pop()
    def resolve_member_index(self,f,env):
        r=f[len('member_'):];return int(r) if r.isdigit() else int(env.get(r))
    def call_builtin(self,name,nodes,env):
        if name in ('map','filter','reduce'):
            args=[self.eval_expr(nodes[0],env)] if nodes else []
            args += [self.eval_expr(x,env) for x in nodes[2:]]
            return self.run_functional(name,nodes,args,env)
        args=[self.eval_expr(x,env) for x in nodes]
        if name=='roll':return 0 if args[0]==0 else random.randint(1,int(args[0]))
        if name in ('endure','perceive'):return self.run_plain_stat_function(name,args)
        if name=='max':return max(args[0]) if len(args)==1 else max(args)
        if name=='min':return min(args[0]) if len(args)==1 else min(args)
        if name=='len':return len(args[0])
        if name=='sum':return sum(args[0]) if len(args)==1 else sum(args)
        if name=='abs':return abs(args[0])
        if name=='round':return round(args[0]) if len(args)==1 else round(args[0],int(args[1]))
        if name=='sorted':return sorted(args[0])
        if name=='reversed':return list(reversed(args[0]))
        if name=='reverse':
            if not isinstance(args[0],list):raise DMError("'reverse' needs a list.")
            args[0].reverse();return args[0]
        if name=='any':return any(args[0])
        if name=='all':return all(args[0])
        if name=='zip':
            if any(not isinstance(x,list) for x in args):raise DMError("'zip' needs lists.")
            return [list(row) for row in zip(*args)]
        if name=='enumerate':return [{'index':i,'value':v} for i,v in enumerate(args[0])]
        if name=='type':return classify_value(args[0])
        if name=='bool':return bool(args[0])
        if name=='num':
            try:
                s=to_scroll(args[0]).strip();return float(s) if '.' in s else int(s)
            except (ValueError,TypeError):raise ValueError(f"'{to_scroll(args[0])}' isn't a valid number.")
        if name=='str':return to_scroll(args[0])
        if name=='list':return list(args[0]) if isinstance(args[0],(list,str)) else list(args[0].keys()) if isinstance(args[0],dict) else [args[0]]
        if name=='pouch':
            if isinstance(args[0],dict):return dict(args[0])
            if isinstance(args[0],list):return {p[0]:p[1] for p in args[0] if isinstance(p,list) and len(p)==2}
            raise DMError("'pouch' needs a pouch or a list of key-value pairs.")
        if name=='contains':
            if len(args)!=2:raise DMError("'contains' needs a collection and a value.")
            return args[1] in args[0]
        if name=='index':
            try:return args[0].index(args[1])
            except (ValueError,AttributeError):return -1
        if name in ('append','push'):
            if len(args)!=2:raise DMError(f"'{name}' needs two values.")
            if isinstance(args[0],list):args[0].append(args[1]);return args[0]
            if isinstance(args[0],VaultHandle):self._vault_append(args[0],to_scroll(args[1]));return args[0]
            raise DMError(f"'{name}' needs a list or vault as its first value.")
        if name=='pop':
            if not isinstance(args[0],list) or not args[0]:raise DMError("'pop' needs a non-empty list.")
            idx=-1 if len(args)==1 else int(args[1]);return args[0].pop(idx)
        if name=='read':return self._vault_read(args[0])
        if name=='write':self._vault_write(args[0],to_scroll(args[1]));return None
        if name in ('close','seal'):
            if not isinstance(args[0],VaultHandle):raise DMError("'close' needs a vault.")
            args[0].closed=True;return None
        if name=='exists':return self._vault_path(args[0]) and os.path.exists(self._vault_path(args[0]))
        if name=='remove':
            path=self._vault_path(args[0])
            try:os.remove(path)
            except FileNotFoundError:pass
            return None
        if name=='forget':
            if not nodes:raise DMError("'forget' needs a variable name.")
            node=nodes[0]
            if node.get('type')!='Identifier':raise DMError("'forget' expects a variable name, not its value.")
            if not env.forget(node['name']):raise DMError(f"'{node['name']}' doesn't exist.")
            return None
        if name=='memory':return len(repr(self.global_env.vars).encode('utf-8'))
        raise DMError(f"There's no built-in called '{name}'.")
    def run_functional(self,name,arg_nodes,args,env):
        if name in ('map','filter'):
            if len(arg_nodes)!=2 or not isinstance(args[0],list):raise DMError(f"'{name}' needs a list and a quest.")
            op_node=arg_nodes[1];op_name=op_node.get('name') if op_node.get('type')=='Identifier' else op_node.get('value') if op_node.get('type')=='StringLiteral' else None
            if op_name not in self.quests:raise DMError(f"There's no quest called '{op_name}'.")
            result=[]
            for item in args[0]:
                transformed=self.call_quest(op_name,[value_to_literal_node(item)],env)
                if name=='map' or bool(transformed):result.append(transformed)
            return result
        if len(arg_nodes) not in (2,3) or not isinstance(args[0],list):raise DMError("'reduce' needs a list, a quest, and optionally a starting value.")
        op_node=arg_nodes[1];op_name=op_node.get('name') if op_node.get('type')=='Identifier' else op_node.get('value') if op_node.get('type')=='StringLiteral' else None
        if op_name not in self.quests:raise DMError(f"There's no reduce operation called '{op_name}'.")
        values=args[0]
        if len(args)==3:acc=args[2];start=0
        else:
            if not values:raise DMError("'reduce' can't reduce an empty list without a starting value.")
            acc=values[0];start=1
        for item in values[start:]:acc=self.call_quest(op_name,[value_to_literal_node(acc),value_to_literal_node(item)],env)
        return acc
    def run_string_method(self,s,method,args):
        value=to_scroll(args[0]) if args else None
        if method=='lower':return s.lower()
        if method=='upper':return s.upper()
        if method=='trim':return s.strip()
        if method=='clean':return ' '.join(s.split())
        if method=='title':return s.title()
        if method=='starts':return s.startswith(value)
        if method=='ends':return s.endswith(value)
        if method=='contains':return value in s
        if method=='empty':return len(s)==0
        if method=='words':return s.split()
        if method=='split':return s.split(value) if args else s.split()
        if method=='join':return s.join(to_scroll(v) for v in args[0])
        if method=='find':return s.find(value)
        if method=='count':return s.count(value)
        if method=='replace':return s.replace(value,to_scroll(args[1]),int(args[2]) if len(args)>2 else -1)
        raise DMError(f"Scrolls don't have a '{method}' method.")
    def run_stat_function(self,sf,inst,mode,args):
        if not isinstance(inst,dict) or 'STATS' not in inst:raise DMError("That doesn't have STATS.")
        stat=STAT_FUNC_TO_STAT[sf];value=inst['STATS'][stat][mode]
        if sf=='endure':
            x,t=args[0],args[1];rate=value*(0.05 if mode=='mod' else 0.005)
            for _ in range(int(t)):x=x-(x*rate)
            return x
        if sf=='perceive':return sum(args[0])/len(args[0])+value
        raise DMError("Unknown stat function.")
    def run_plain_stat_function(self,name,args):
        if name=='endure':
            x,t,r=args
            for _ in range(int(t)):x=x-(x*(r/100))
            return x
        if name=='perceive':return sum(args[0])/len(args[0])
        raise DMError("Unknown built-in.")
    def eval_force(self,node,env):return apply_math_symbol(self.resolve_stat_value('STR',node['mode'],node['instance'],env),node['symbol'],self.eval_expr(node['value'],env))
    def eval_sway(self,node,env):
        if not self.block_stack:raise DMError("sway can't be used outside of a block.")
        frame=self.block_stack[-1];raw_address=self.eval_expr(node['address'],env);target=self.find_sway_target(frame,raw_address)
        if target is None:raise DMError(f"There's no line at address {self.format_sway_address(raw_address)} to move.")
        owner,index,ancestor_index=self._sway_target_parts(target)
        if owner is frame['statements']:
            if index<=frame['index']:raise DMError("You can't move a line that's already happened.")
            minimum=frame['index']+1
        else:
            if ancestor_index<=frame['index']:raise DMError("You can't move a line that's already happened.")
            minimum=0
        shift=self.resolve_shift(node['shift'],node['instance'],env);dest=max(minimum,min(index+int(shift),len(owner)-1));item=owner.pop(index);owner.insert(dest,item);return None
    def format_sway_address(self,address):return address if isinstance(address,str) else str(address)
    def _sway_target_parts(self,target):return target['owner'],target['index'],target['ancestor_index']
    def find_sway_target(self,frame,address):
        if isinstance(address,(int,float)) and not isinstance(address,bool) and float(address).is_integer():
            i=int(address);stmts=frame['statements']
            if 0<=i<len(stmts):return {'owner':stmts,'index':i,'ancestor_index':i}
            return None
        text=str(address)
        if '.' not in text:return None
        major_text,minor_text=text.split('.',1)
        if not major_text.isdigit() or not minor_text.isdigit():return None
        major,minor=int(major_text),int(minor_text);stmts=frame['statements']
        if major<0 or major>=len(stmts):return None
        parent=stmts[major]
        for block in self._statement_blocks(parent):
            if 0<=minor<len(block):return {'owner':block,'index':minor,'ancestor_index':major}
        return None
    def _statement_blocks(self,stmt):
        blocks=[];kind=stmt.get('type')
        if kind in ('While','Adventure','ForParty','QuestDef','HomebrewDef','Submit'):
            if isinstance(stmt.get('body'),list):blocks.append(stmt['body'])
        if kind=='Attempt':
            for clause in stmt.get('clauses',[]):
                if isinstance(clause.get('body'),list):blocks.append(clause['body'])
            if isinstance(stmt.get('fail_body'),list):blocks.append(stmt['fail_body'])
        return blocks
    def resolve_shift(self,node,inst,env):return node['value'] if node['type']=='ShiftLiteral' else self.resolve_stat_value(node['stat'] or 'CHA',node['mode'],inst,env)
    def resolve_stat_value(self,stat,mode,inst,env):
        stats=self.eval_expr(inst,env)['STATS'] if inst is not None else self.get_global_stats()
        if stat not in stats:raise DMError(f"'{stat}' isn't a stat there.")
        return stats[stat][mode]
    def get_global_stats(self):return self.global_stats if self.global_stats is not None else {s:{'number':10,'mod':0} for s in DEFAULT_STAT_NAMES}

def apply_math_symbol(a,op,b):
    if op=='+':return a+b
    if op=='-':return a-b
    if op=='*':return a*b
    if op=='/':
        if b==0:raise DMError("You can't divide by zero.")
        return a/b
    if op=='%':
        if b==0:raise DMError("You can't divide by zero.")
        return a%b
    raise DMError(f"Unknown math symbol '{op}'.")

def coerce_input(raw):
    text=raw.strip()
    if text=='honor':return True
    if text=='lie':return False
    try:return float(text) if '.' in text else int(text)
    except ValueError:return raw
