import tkinter as tk
from tkinter import filedialog, simpledialog
import threading
import queue
import re
from lexer import tokenize, strip_comments
from parser import parse
from interpreter import Interpreter, DMError

DECL_WORDS={"ability","pouch","vault","summon","homebrew","quest","init","extra","STATS"}
CONTROL_WORDS={"attempt","or_attempt","fail","finally","adventure","while","for","in","party","quit","continue","submit","consider","issue","pass","raise"}
IO_WORDS={"narrate","player","embark","reward"}
BOOL_WORDS={"honor","lie"}
BUILTIN_WORDS={"force","sway","endure","perceive","solve","roll","max","min","len","num","str","bool","type","list","pouch","sum","abs","round","sorted","reversed","reverse","any","all","zip","enumerate","append","push","pop","map","filter","reduce","contains","index","read","write","close","seal","exists","remove","forget","memory","lower","upper","trim","clean","title","starts","ends","empty","words","split","join","find","count","replace"}
STAT_WORDS={"STR","DEX","CON","INT","WIS","CHA"}
KIND_WORDS={"character","item","monster","spell"}
HOVER_DOCS={
"ability":"Declares a normal value.","pouch":"Declares named key-value data: pouch hero = {\"name\": \"Hero\", \"hp\": 20}.","vault":"Declares a file vault: vault save = \"save.txt\".",
"pass":"Does nothing. Useful as a placeholder.","raise":"Raises a DM error on purpose: raise \"Quest failed.\".","finally":"Runs after submit/consider whether an error happened or not.","submit":"Runs code that might fail; pair with consider and optionally finally.","consider":"Handles an error after submit.","issue":"Names the error kind for consider.","none":"The empty value. Its language type is NoneType.",
"party":"D&D Lang's sequence/range tool: party(n) gives 0..n-1; party(a, b) gives a..b-1.","type":"Returns a D&D Lang type name.","bool":"Converts a value to honor/lie.","list":"Converts a value to a list.","pouch":"Key-value collection.",
"sum":"Adds a sequence or supplied numbers.","sorted":"Returns a sorted copy.","reversed":"Returns a reversed copy.","reverse":"Reverses a list in place.","enumerate":"Returns pouches containing index and value.","zip":"Combines lists by matching positions.","map":"Applies a quest to each list item.","filter":"Keeps list items whose quest result is honor.","reduce":"Combines a list with a two-argument quest.",
"read":"Reads text from a vault or path.","write":"Writes text to a vault, replacing its contents.","close":"Seals a vault.","append":"Adds to a list, or appends text to a vault.","forget":"Removes a named variable from scope.","memory":"Reports a small runtime memory estimate for global values.",
"replace":"Scroll method: returns a copy with matching text replaced.","find":"Scroll method: finds text and returns its position, or -1.","count":"Scroll method: counts matching text.","contains":"Checks whether a collection contains a value.","len":"Returns the length of a list or Scroll.","num":"Converts text/value to a number.","str":"Converts a value to a Scroll."}
HOVER_DOCS.update({"summon":"Creates a homebrew instance.","homebrew":"Defines a custom D&D type.","quest":"Defines a function-like quest.","embark":"Calls a quest.","reward":"Returns a value from a quest.","init":"Pulls a caller variable into an isolated quest.","narrate":"Prints output.","player":"Gets player input.","attempt":"Conditional block.","or_attempt":"Additional conditional branch.","fail":"Fallback branch.","adventure":"Repeats or iterates a block.","while":"Loops while a condition is honor.","for":"Starts a party loop.","quit":"Stops the nearest loop.","continue":"Skips the current loop iteration."})
HOVER_DOCS["member"]="List indexing can use list.member_2 or list[index]. Pouches use pouch[key]."

def compute_line_addresses(text):
    addresses=[];major=-1;minor=None
    for raw in text.split("\n"):
        code=strip_comments(raw)
        if not code.strip():addresses.append("");continue
        indent=len(code)-len(code.lstrip(" \t"))
        if indent==0:major+=1;minor=None;addresses.append(str(major))
        else:minor=0 if minor is None else minor+1;addresses.append(f"{major}.{minor}")
    return addresses

class DndIDE:
    def __init__(self,root):
        self.root=root;self.root.title("D&D Lang IDE — untitled.dnd");self.current_path=None;self.output_queue=queue.Queue();self.input_result_queue=queue.Queue();self.tooltip=None;self._last_hover_word=None
        self._build_menu();self._build_layout();self._highlight();self._poll_output_queue()
    def _build_menu(self):
        m=tk.Menu(self.root);f=tk.Menu(m,tearoff=0);f.add_command(label="New",command=self.new_file,accelerator="Ctrl+N");f.add_command(label="Open...",command=self.open_file,accelerator="Ctrl+O");f.add_command(label="Save",command=self.save_file,accelerator="Ctrl+S");f.add_command(label="Save As...",command=self.save_file_as);f.add_separator();f.add_command(label="Exit",command=self.root.quit);m.add_cascade(label="File",menu=f);r=tk.Menu(m,tearoff=0);r.add_command(label="Run",command=self.run_code,accelerator="F5");m.add_cascade(label="Run",menu=r);self.root.config(menu=m);self.root.bind("<Control-n>",lambda e:self.new_file());self.root.bind("<Control-o>",lambda e:self.open_file());self.root.bind("<Control-s>",lambda e:self.save_file());self.root.bind("<F5>",lambda e:self.run_code())
    def _build_layout(self):
        t=tk.Frame(self.root);t.pack(side=tk.TOP,fill=tk.X);self.run_button=tk.Button(t,text="Run (F5)",command=self.run_code,bg="#4CAF50",fg="white");self.run_button.pack(side=tk.LEFT,padx=4,pady=4);p=tk.PanedWindow(self.root,orient=tk.VERTICAL,sashwidth=6);p.pack(fill=tk.BOTH,expand=True);e=tk.Frame(p);self.linenumbers=tk.Text(e,width=7,padx=6,border=0,background="#252526",foreground="#7a7a7a",font=("Consolas",12),state="disabled",wrap="none");self.linenumbers.pack(side=tk.LEFT,fill=tk.Y);self.editor=tk.Text(e,wrap="none",undo=True,font=("Consolas",12),bg="#1e1e1e",fg="#d4d4d4",insertbackground="white",yscrollcommand=self._on_editor_yview);self.editor.pack(side=tk.LEFT,fill=tk.BOTH,expand=True);self.editor.bind("<KeyRelease>",self._on_key_release);self.editor.bind("<Return>",self._on_return);self.editor.bind("(",self._open_paren);self.editor.bind(")",self._close_paren);self.editor.bind('[',self._open_bracket);self.editor.bind(']',self._close_bracket);self.editor.bind('{',self._open_brace);self.editor.bind('}',self._close_brace);self.editor.bind('"',self._quote);self.editor.bind("<Motion>",self._on_hover);self.editor.bind("<Leave>",lambda e:self._hide_tooltip());self._configure_tags();p.add(e,minsize=200);c=tk.Frame(p);tk.Label(c,text="Console").pack(anchor="w");self.console=tk.Text(c,height=10,bg="black",fg="#00ff00",font=("Consolas",11),state="disabled");self.console.pack(fill=tk.BOTH,expand=True);p.add(c,minsize=100)
    def _configure_tags(self):
        for n,c in [("decl","#569CD6"),("control","#C586C0"),("io","#4EC9B0"),("bool","#D19A66"),("builtin","#DCDCAA"),("statname","#4FC1FF"),("kind","#D7BA7D"),("string","#CE9178"),("number","#B5CEA8"),("comment","#6A9955")]:self.editor.tag_configure(n,foreground=c)
    ALL_TAGS=("decl","control","io","bool","builtin","statname","kind","string","number","comment")
    def _tag(self,tag,a,b):self.editor.tag_add(tag,f"1.0+{a}c",f"1.0+{b}c")
    def _highlight(self):
        text=self.editor.get("1.0","end-1c")
        for tag in self.ALL_TAGS:self.editor.tag_remove(tag,"1.0","end")
        i=0;n=len(text)
        while i<n:
            if text[i]=='"':
                a=i;i+=1;esc=False
                while i<n:
                    ch=text[i]
                    if esc:esc=False
                    elif ch=='\\':esc=True
                    elif ch=='"':i+=1;break
                    i+=1
                self._tag('string',a,i);continue
            if i+1<n and text[i:i+2]=='--':
                a=i;i+=2;close=text.find('--',i);nl=text.find('\n',i)
                if close==-1 or (nl!=-1 and nl<close):i=n if nl==-1 else nl
                else:i=close+2
                self._tag('comment',a,i);continue
            ch=text[i]
            if ch.isalpha() or ch=='_':
                a=i;i+=1
                while i<n and (text[i].isalnum() or text[i]=='_'):i+=1
                w=text[a:i];tag='decl' if w in DECL_WORDS else 'control' if w in CONTROL_WORDS else 'io' if w in IO_WORDS else 'bool' if w in BOOL_WORDS else 'builtin' if w in BUILTIN_WORDS or w.startswith('member_') else 'statname' if w in STAT_WORDS else 'kind' if w in KIND_WORDS else None
                if tag:self._tag(tag,a,i)
                continue
            if ch.isdigit():
                a=i;i+=1
                while i<n and (text[i].isdigit() or text[i]=='.'):i+=1
                self._tag('number',a,i);continue
            i+=1
        self._update_line_numbers(text)
    def _update_line_numbers(self,text=None):
        if text is None:text=self.editor.get('1.0','end-1c')
        self.linenumbers.config(state='normal');self.linenumbers.delete('1.0','end');self.linenumbers.insert('1.0','\n'.join(compute_line_addresses(text)));self.linenumbers.config(state='disabled');self.linenumbers.yview_moveto(self.editor.yview()[0])
    def _on_key_release(self,e=None):self._highlight()
    def _on_editor_yview(self,a,b):self.linenumbers.yview_moveto(float(a))
    def _on_return(self,e):
        cur=self.editor.index(tk.INSERT);ls=cur.split('.')[0]+'.0';line=self.editor.get(ls,cur);ws=re.match(r'[ \t]*',line).group();extra='    ' if line.rstrip().endswith(':') else '';self.editor.insert(tk.INSERT,'\n'+ws+extra);return 'break'
    def _pair(self,a,b):self.editor.insert(tk.INSERT,a+b);self.editor.mark_set(tk.INSERT,f'{tk.INSERT}-1c');return 'break'
    def _close(self,ch):
        i=self.editor.index(tk.INSERT)
        if self.editor.get(i,f'{i}+1c')==ch:self.editor.mark_set(tk.INSERT,f'{i}+1c');return 'break'
    def _open_paren(self,e):return self._pair('(',')')
    def _close_paren(self,e):return self._close(')')
    def _open_bracket(self,e):return self._pair('[',']')
    def _close_bracket(self,e):return self._close(']')
    def _open_brace(self,e):return self._pair('{','}')
    def _close_brace(self,e):return self._close('}')
    def _quote(self,e):
        i=self.editor.index(tk.INSERT)
        if self.editor.get(i,f'{i}+1c')=='"':self.editor.mark_set(tk.INSERT,f'{i}+1c');return 'break'
        return self._pair('"','"')
    def _word_at(self,idx):
        ln=idx.split('.')[0];line=self.editor.get(f'{ln}.0',f'{ln}.0 lineend');c=int(idx.split('.')[1]);a=c
        while a>0 and (line[a-1].isalnum() or line[a-1]=='_'):a-=1
        b=c
        while b<len(line) and (line[b].isalnum() or line[b]=='_'):b+=1
        return line[a:b]
    def _on_hover(self,e):
        w=self._word_at(self.editor.index(f'@{e.x},{e.y}'))
        if w==self._last_hover_word:return
        self._last_hover_word=w
        if w in HOVER_DOCS:self._show_tooltip(e.x_root,e.y_root,w,HOVER_DOCS[w])
        else:self._hide_tooltip()
    def _show_tooltip(self,x,y,w,t):
        self._hide_tooltip();self.tooltip=tk.Toplevel(self.root);self.tooltip.wm_overrideredirect(True);self.tooltip.wm_geometry(f'+{x+14}+{y+16}');f=tk.Frame(self.tooltip,background='#ffffe0',relief='solid',borderwidth=1);f.pack();tk.Label(f,text=w,background='#ffffe0',font=('Consolas',10,'bold')).pack(fill='x',padx=6,pady=(4,0));tk.Label(f,text=t,background='#ffffe0',font=('Consolas',9),wraplength=380,justify='left').pack(fill='x',padx=6,pady=(0,4))
    def _hide_tooltip(self):
        if self.tooltip:self.tooltip.destroy();self.tooltip=None
        self._last_hover_word=None
    def new_file(self):self.editor.delete('1.0','end');self.current_path=None;self.root.title('D&D Lang IDE — untitled.dnd');self._highlight()
    def open_file(self):
        p=filedialog.askopenfilename(filetypes=[('D&D files','*.dnd'),('All files','*.*')])
        if not p:return
        with open(p,'r',encoding='utf-8') as f:c=f.read()
        self.editor.delete('1.0','end');self.editor.insert('1.0',c);self.current_path=p;self.root.title(f'D&D Lang IDE — {p}');self._highlight()
    def save_file(self):
        if self.current_path is None:return self.save_file_as()
        with open(self.current_path,'w',encoding='utf-8') as f:f.write(self.editor.get('1.0','end-1c'))
    def save_file_as(self):
        p=filedialog.asksaveasfilename(defaultextension='.dnd',filetypes=[('D&D files','*.dnd'),('All files','*.*')])
        if p:self.current_path=p;self.root.title(f'D&D Lang IDE — {p}');self.save_file()
    def run_code(self):
        s=self.editor.get('1.0','end-1c');self._clear_console();self.run_button.config(state='disabled',text='Running...');threading.Thread(target=self._run_in_thread,args=(s,),daemon=True).start()
    def _run_in_thread(self,s):
        try:Interpreter(output_func=self._queue_output,input_func=self._ask_input).run(parse(tokenize(s)))
        except (SyntaxError,DMError,ValueError) as e:self._queue_output(f'DM: {e}')
        except Exception as e:self._queue_output(f'DM: something went very wrong ({e})')
        finally:self.output_queue.put(('__DONE__',None))
    def _queue_output(self,t):self.output_queue.put(('line',t))
    def _ask_input(self,prompt):
        def show():
            v=simpledialog.askstring('Player Input',prompt,parent=self.root);self.input_result_queue.put(v if v is not None else '')
        self.root.after(0,show);return self.input_result_queue.get()
    def _poll_output_queue(self):
        try:
            while True:
                k,p=self.output_queue.get_nowait()
                if k=='line':self._append_console(p+'\n')
                elif k=='__DONE__':self.run_button.config(state='normal',text='Run (F5)')
        except queue.Empty:pass
        self.root.after(50,self._poll_output_queue)
    def _append_console(self,t):self.console.config(state='normal');self.console.insert('end',t);self.console.see('end');self.console.config(state='disabled')
    def _clear_console(self):self.console.config(state='normal');self.console.delete('1.0','end');self.console.config(state='disabled')

def main():
    root=tk.Tk();root.geometry('900x700');DndIDE(root);root.mainloop()
if __name__=='__main__':main()
