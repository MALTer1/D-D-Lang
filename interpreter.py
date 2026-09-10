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
        elif kind=="Assignment":self.assign_target(stmt["target"],self.eval_expr(stmt["value"],env),env)
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
    def eval_binary(self,n,env):
        a=self.eval_expr(n['left'],env);b=self.eval_expr(n['right'],env);o=n['op']
        if o=='+':return to_scroll(a)+to_scroll(b) if isinstance(a,str) or isinstance(b,str) else a+b
        if o=='-':return a-b
        if o=='*':return a*b
        if o in ('/','%') and b==0:raise DMError("You can't divide by zero.")
        if o=='/':return a/b
        if o=='%':return a%b
        if o=='==':return a==b
        if o=='!=':return a!=b
        if o=='>':return a>b
        if o=='<':return a<b
        if o=='>=':return a>=b
        if o=='<=':return a<=b
        raise DMError(f"Unknown operator '{o}'.")
    def call_quest(self,name,nodes,env):
        if name not in self.quests:raise DMError(f"There's no quest called '{name}'.")
        q=self.quests[name];args=[self.eval_expr(x,env) for x in nodes];qe=Environment()
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
            return args[0].pop(-1 if len(args)==1 else int(args[1]))
        if name=='read':return self._vault_read(args[0])
        if name=='write':self._vault_write(args[0],to_scroll(args[1]));return None
        if name in ('close','seal'):
            if not isinstance(args[0],VaultHandle):raise DMError("'close' needs a vault.")
            args[0].closed=True;return None
        if name=='exists':return os.path.exists(self._vault_path(args[0]))
        if name=='remove':
            try:os.remove(self._vault_path(args[0]))
            except FileNotFoundError:pass
            return None
        if name=='forget':
            if not nodes or nodes[0].get('type')!='Identifier':raise DMError("'forget' expects a variable name.")
            if not env.forget(nodes[0]['name']):raise DMError(f"'{nodes[0]['name']}' doesn't exist.")
            return None
        if name=='memory':return len(repr(self.global_env.vars).encode('utf-8'))
        raise DMError(f"There's no built-in called '{name}'.")
    def run_functional(self,name,nodes,args,env):
        if len(nodes)!=2 and not (name=='reduce' and len(nodes)==3):raise DMError(f"'{name}' needs a list and a quest.")
        values=args[0]
        op=nodes[1];qname=op.get('name') if op.get('type')=='Identifier' else op.get('value') if op.get('type')=='StringLiteral' else None
        if qname not in self.quests:raise DMError(f"There's no quest called '{qname}'.")
        if not isinstance(values,list):raise DMError(f"'{name}' needs a list as its first value.")
        if name=='map':return [self.call_quest(qname,[value_to_literal_node(x)],env) for x in values]
        if name=='filter':return [x for x in values if self.call_quest(qname,[value_to_literal_node(x)],env)]
        if len(args)==2:
            if not values:raise DMError("'reduce' can't reduce an empty list without a starting value.")
            acc=values[0];items=values[1:]
        else:acc=args[1];items=values
        for item in items:acc=self.call_quest(qname,[value_to_literal_node(acc),value_to_literal_node(item)],env)
        return acc
    def _vault_path(self,v):
        if isinstance(v,VaultHandle):v.check();return v.path
        if isinstance(v,str):return v
        raise DMError("That isn't a vault or file path.")
    def _vault_read(self,v):
        p=self._vault_path(v)
        try:
            with open(p,'r',encoding='utf-8') as f:return f.read()
        except FileNotFoundError:raise DMError(f"The vault '{p}' doesn't exist yet.")
    def _vault_write(self,v,data):
        p=self._vault_path(v)
        try:
            with open(p,'w',encoding='utf-8') as f:f.write(data)
        except OSError as e:raise DMError(f"The DM couldn't write '{p}': {e}")
    def _vault_append(self,v,data):
        p=self._vault_path(v)
        try:
            with open(p,'a',encoding='utf-8') as f:f.write(data)
        except OSError as e:raise DMError(f"The DM couldn't inscribe '{p}': {e}")
    def resolve_party(self,nodes,env):
        a=[self.eval_expr(x,env) for x in nodes]
        if len(a)==1:
            if isinstance(a[0],dict):return list(a[0].keys())
            if isinstance(a[0],(list,str)):return list(a[0])
            return list(range(int(a[0])))
        if len(a)==2:return list(range(int(a[0]),int(a[1])))
        raise DMError("party(...) takes 1 or 2 arguments.")
    def exec_submit(self,stmt,env):
        caught=False
        try:self.exec_block(stmt['body'],Environment(parent=env))
        except (QuitSignal,ContinueSignal,RewordSignal):raise
        except Exception as e:
            for c in stmt['considers']:
                n=c['error_name'];match=n is None or (n=='ValueError' and isinstance(e,ValueError)) or (n=='DMError' and isinstance(e,DMError)) or (n=='OSError' and isinstance(e,OSError))
                if match:self.exec_block(c['body'],Environment(parent=env));caught=True;break
            if not caught:raise
        finally:
            if stmt.get('finally_body') is not None:self.exec_block(stmt['finally_body'],Environment(parent=env))
    def define_homebrew(self,stmt,env):
        k=stmt['kind']
        if k not in SHAPE_RULES:raise DMError(f"'{k}' isn't a real homebrew kind.")
        vals={n:self.eval_expr(e,env) for n,e in stmt['fields'].items()};filled=self.fill_shape(k,vals)
        for n,v in filled.items():
            if n not in stmt['fields']:stmt['fields'][n]=value_to_literal_node(v)
        self.homebrews[stmt['name']]=stmt
    def fill_shape(self,k,values):
        r=SHAPE_RULES[k];counts={}
        for v in values.values():t=classify_value(v);counts[t]=counts.get(t,0)+1
        def total():return sum(min(c,r['max_per_type']) for c in counts.values())
        cyc=['number','Scroll','list','honor/lie'];defs={'number':0,'Scroll':'','list':[],'honor/lie':False};i=0
        while total()<r['min_total'] or len(counts)<r['min_types']:
            missing=[t for t in cyc if t not in counts];t=missing[0] if len(counts)<r['min_types'] and missing else cyc[i%len(cyc)];values[f'_auto_{t.replace("/","_")}_{i}']=defs[t];counts[t]=counts.get(t,0)+1;i+=1
        return values
    def build_stats(self,se,ee,env):
        out={}
        for s in DEFAULT_STAT_NAMES:
            n=self.eval_expr(se[s],env) if s in se else 10;out[s]={'number':n,'mod':math.floor((n-10)/2)}
        for s,e in ee.items():n=self.eval_expr(e,env);out[s]={'number':n,'mod':math.floor((n-10)/2)}
        return out
    def get_global_stats(self):return self.global_stats if self.global_stats is not None else {s:{'number':10,'mod':0} for s in DEFAULT_STAT_NAMES}
    def exec_summon(self,stmt,env):
        t=self.homebrews.get(stmt['template'])
        if t is None:raise DMError(f"There's no homebrew called '{stmt['template']}'.")
        x={n:self.eval_expr(e,env) for n,e in t['fields'].items()};x['STATS']=self.build_stats(t['stats'],t['extra_stats'],env);x['__kind__']=t['kind'];env.declare(stmt['var_name'],x)
    def eval_call_expr(self,n,env):
        c=n['callee']
        if c['type']=='FieldAccess' and c['field'] in ('mod','number') and c['obj']['type']=='FieldAccess' and c['obj']['field'] in STAT_FUNC_TO_STAT:
            return self.run_stat_function(c['obj']['field'],self.eval_expr(c['obj']['obj'],env),c['field'],[self.eval_expr(a,env) for a in n['args']])
        if c['type']=='Identifier' and c['name'] in ('endure','perceive'):return self.run_plain_stat_function(c['name'],[self.eval_expr(a,env) for a in n['args']])
        if c['type']=='FieldAccess':
            o=self.eval_expr(c['obj'],env)
            if isinstance(o,str):return self.run_string_method(o,c['field'],[self.eval_expr(a,env) for a in n['args']])
        raise DMError("That's not something you can call like that.")
    def run_string_method(self,s,m,a):
        x=to_scroll(a[0]) if a else None
        if m=='lower':return s.lower()
        if m=='upper':return s.upper()
        if m=='trim':return s.strip()
        if m=='clean':return ' '.join(s.split())
        if m=='title':return s.title()
        if m=='starts':return s.startswith(x)
        if m=='ends':return s.endswith(x)
        if m=='contains':return x in s
        if m=='empty':return not s
        if m=='words':return s.split()
        if m=='split':return s.split(x) if a else s.split()
        if m=='join':return s.join(to_scroll(v) for v in a[0])
        if m=='find':return s.find(x)
        if m=='count':return s.count(x)
        if m=='replace':return s.replace(x,to_scroll(a[1]),int(a[2]) if len(a)>2 else -1)
        raise DMError(f"Scrolls don't have a '{m}' method.")
    def run_stat_function(self,sf,inst,mode,args):
        if not isinstance(inst,dict) or 'STATS' not in inst:raise DMError("That doesn't have STATS.")
        v=inst['STATS'][STAT_FUNC_TO_STAT[sf]][mode]
        if sf=='endure':
            x,t=args;rate=v*(0.05 if mode=='mod' else 0.005)
            for _ in range(int(t)):x=x-x*rate
            return x
        return sum(args[0])/len(args[0])+v
    def run_plain_stat_function(self,n,a):
        if n=='endure':
            x,t,r=a
            for _ in range(int(t)):x=x-x*(r/100)
            return x
        return sum(a[0])/len(a[0])
    def eval_force(self,n,env):return apply_math_symbol(self.resolve_stat_value('STR',n['mode'],n['instance'],env),n['symbol'],self.eval_expr(n['value'],env))
    def eval_sway(self,n,env):
        if not self.block_stack:raise DMError("sway can't be used outside of a block.")
        f=self.block_stack[-1];ss=f['statements'];a=int(self.eval_expr(n['address'],env))
        if a<0 or a>=len(ss):raise DMError(f"There's no line at address {a} to move.")
        if a<=f['index']:raise DMError("You can't move a line that's already happened.")
        d=max(f['index']+1,min(a+int(self.resolve_shift(n['shift'],n['instance'],env)),len(ss)-1));x=ss.pop(a);ss.insert(d,x)
    def resolve_shift(self,n,i,env):return n['value'] if n['type']=='ShiftLiteral' else self.resolve_stat_value(n['stat'] or 'CHA',n['mode'],i,env)
    def resolve_stat_value(self,s,m,i,env):return (self.eval_expr(i,env)['STATS'] if i is not None else self.get_global_stats())[s][m]
    def eval_solve(self,n,env):
        i=self.eval_expr(n['instance'],env);d=self.eval_expr(n['difficulty'],env);size=i['STATS']['INT'][n['mode']];r=0 if size<=0 else random.randint(1,int(size));return {'/':r>d,'_':r==d,'\\':r<d,'/_':r>=d,'\\_':r<=d}[n['comparator']]

def apply_math_symbol(a,s,b):
    if s=='+':return a+b
    if s=='-':return a-b
    if s=='*':return a*b
    if s=='/':
        if b==0:raise DMError("You can't divide by zero.")
        return a/b
    if s=='%':
        if b==0:raise DMError("You can't divide by zero.")
        return a%b
    raise DMError(f"Unknown math symbol '{s}'.")

def coerce_input(raw):
    try:s=raw.strip();return float(s) if '.' in s else int(s)
    except (ValueError,AttributeError):return raw
