import tkinter as tk
from tkinter import filedialog, simpledialog, colorchooser, messagebox, ttk
import threading
import queue
import re
import json
import os

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
    "ability":"Declares a normal value.","pouch":"Declares named key-value data.","vault":"Declares a file vault.",
    "pass":"Does nothing. Useful as a placeholder.","raise":"Raises a DM error on purpose.","finally":"Runs after submit/consider.",
    "submit":"Runs code that might fail.","consider":"Handles an error after submit.","issue":"Names the error kind.",
    "none":"The empty value. Its language type is NoneType.","party":"Creates a D&D Lang sequence/range.","type":"Returns a D&D Lang type name.",
    "bool":"Converts a value to honor/lie.","list":"Converts a value to a list.","sum":"Adds a sequence or supplied numbers.",
    "sorted":"Returns a sorted copy.","reversed":"Returns a reversed copy.","reverse":"Reverses a list in place.",
    "enumerate":"Returns pouches containing index and value.","zip":"Combines lists by matching positions.","map":"Applies a quest to each list item.",
    "filter":"Keeps list items whose quest result is honor.","reduce":"Combines a list with a two-argument quest.","read":"Reads text from a vault or path.",
    "write":"Writes text to a vault.","close":"Seals a vault.","append":"Adds to a list or vault.","forget":"Removes a named variable from scope.",
    "memory":"Reports a small runtime memory estimate.","replace":"Scroll method: replaces matching text.","find":"Scroll method: finds text.",
    "count":"Scroll method: counts matching text.","contains":"Checks whether a collection contains a value.","len":"Returns length.","num":"Converts to a number.","str":"Converts to a Scroll.",
    "summon":"Creates a homebrew instance.","homebrew":"Defines a custom D&D type.","quest":"Defines a function-like quest.","embark":"Calls a quest.","reward":"Returns a value from a quest.",
    "init":"Pulls a caller variable into an isolated quest.","narrate":"Prints output.","player":"Gets player input.","attempt":"Conditional block.",
    "or_attempt":"Additional conditional branch.","fail":"Fallback branch.","adventure":"Repeats or iterates a block.","while":"Loops while a condition is honor.",
    "for":"Starts a party loop.","quit":"Stops the nearest loop.","continue":"Skips the current loop iteration.","force":"Moves execution forward.","sway":"Reorders unexecuted code. Supports addresses such as 3 or 3.1."
}

THEMES={
    "D&D Dark": {"bg":"#101318","panel":"#171b22","panel2":"#1d232d","editor":"#11151b","gutter":"#171b22","text":"#d9e1ea","muted":"#7f8b99","accent":"#d6a85f","accent2":"#8f6f3f","console":"#0b0f13","console_text":"#8fe388","select":"#334155","current":"#1a222d","border":"#293241","button":"#202936","button_hover":"#2a3545","error":"#ef7d7d"},
    "Midnight": {"bg":"#090b14","panel":"#111426","panel2":"#171b31","editor":"#0b0e1a","gutter":"#111426","text":"#dfe5ff","muted":"#737b9b","accent":"#8c7cff","accent2":"#5b52aa","console":"#080a12","console_text":"#7ee7ff","select":"#30365c","current":"#151a2d","border":"#252b47","button":"#1b2140","button_hover":"#28305a","error":"#ff7c9e"},
    "Forest": {"bg":"#0d1511","panel":"#132019","panel2":"#1a2a21","editor":"#0d1712","gutter":"#132019","text":"#dce9df","muted":"#78907e","accent":"#7bc47f","accent2":"#4d8053","console":"#09100c","console_text":"#9be7a0","select":"#294335","current":"#16251b","border":"#263b2e","button":"#1a2c21","button_hover":"#254031","error":"#ff8b80"},
    "Ember": {"bg":"#18100f","panel":"#241614","panel2":"#2e1c19","editor":"#170f0e","gutter":"#241614","text":"#f2e1da","muted":"#a48479","accent":"#ff9a62","accent2":"#a65b3b","console":"#100a09","console_text":"#ffc078","select":"#513026","current":"#281815","border":"#453027","button":"#34201a","button_hover":"#4a2b21","error":"#ff7474"},
    "Light": {"bg":"#eef1f5","panel":"#ffffff","panel2":"#e4e8ee","editor":"#fbfcfe","gutter":"#e9edf2","text":"#253041","muted":"#6d7786","accent":"#9a6b18","accent2":"#c59a45","console":"#20252c","console_text":"#a9f0a0","select":"#cbd7e8","current":"#edf2f8","border":"#cbd2dc","button":"#e2e7ee","button_hover":"#d5dde8","error":"#c33c3c"}
}

DEFAULTS={"theme":"D&D Dark","font":"Consolas","font_size":12,"console_size":11,"tab_size":4,"line_numbers":True,"addresses":True,"word_wrap":False,"minimap":True,"current_line":True,"bold_keywords":False,"ui_scale":1.0,"cursor":"#ffffff","accent_override":None}


def compute_line_addresses(text):
    addresses=[];major=-1;minor=None
    for raw in text.split("\n"):
        code=strip_comments(raw)
        if not code.strip(): addresses.append(""); continue
        indent=len(code)-len(code.lstrip(" \t"))
        if indent==0:
            major+=1;minor=None;addresses.append(str(major))
        else:
            minor=0 if minor is None else minor+1;addresses.append(f"{major}.{minor}")
    return addresses


class DndIDE:
    def __init__(self,root):
        self.root=root
        self.current_path=None
        self.workspace_root=None
        self.output_queue=queue.Queue();self.input_result_queue=queue.Queue()
        self.tooltip=None;self._last_hover_word=None;self._highlight_job=None
        self.settings=dict(DEFAULTS)
        self._load_settings()
        self.root.title("D&D Lang IDE — untitled.dnd")
        self.root.minsize(850,560)
        try:self.root.option_add("*tearOff",False)
        except Exception:pass
        self._build_menu();self._build_layout();self._bind_keys();self._apply_theme();self._explorer_style();self._highlight();self._poll_output_queue();self.refresh_explorer()

    def _settings_path(self):
        try:return os.path.join(os.path.expanduser("~"),".dnd_lang_ide.json")
        except Exception:return None

    def _load_settings(self):
        p=self._settings_path()
        if p:
            try:
                with open(p,"r",encoding="utf-8") as f:self.settings.update(json.load(f))
            except Exception:pass
        for key,value in DEFAULTS.items():
            self.settings.setdefault(key,value)
        if self.settings.get("theme") not in THEMES:self.settings["theme"]="D&D Dark"
        self._save_settings()

    def _save_settings(self):
        p=self._settings_path()
        if not p:return
        try:
            with open(p,"w",encoding="utf-8") as f:json.dump(self.settings,f,indent=2)
        except Exception:pass

    @property
    def C(self):
        c=THEMES[self.settings["theme"]].copy()
        if self.settings.get("accent_override"):c["accent"]=self.settings["accent_override"]
        return c

    def _build_menu(self):
        m=tk.Menu(self.root)
        f=tk.Menu(m);f.add_command(label="New",command=self.new_file,accelerator="Ctrl+N");f.add_command(label="Open...",command=self.open_file,accelerator="Ctrl+O");f.add_command(label="Save",command=self.save_file,accelerator="Ctrl+S");f.add_command(label="Save As...",command=self.save_file_as,accelerator="Ctrl+Shift+S");f.add_separator();f.add_command(label="Settings...",command=self.open_settings);f.add_separator();f.add_command(label="Exit",command=self.root.quit);m.add_cascade(label="File",menu=f)
        r=tk.Menu(m);r.add_command(label="Run",command=self.run_code,accelerator="F5");r.add_command(label="Clear Console",command=self._clear_console,accelerator="Ctrl+L");m.add_cascade(label="Run",menu=r)
        v=tk.Menu(m);v.add_command(label="Settings...",command=self.open_settings);v.add_command(label="Toggle Minimap",command=self.toggle_minimap);v.add_command(label="Toggle Line Numbers",command=self.toggle_line_numbers);v.add_command(label="Toggle Addresses",command=self.toggle_addresses);v.add_command(label="Toggle Word Wrap",command=self.toggle_wrap);m.add_cascade(label="View",menu=v)
        w=tk.Menu(m);w.add_command(label="Open Folder...",command=self.open_folder);w.add_command(label="Refresh Explorer",command=self.refresh_explorer);w.add_separator();w.add_command(label="New File",command=self.create_file);w.add_command(label="New Folder",command=self.create_folder);m.add_cascade(label="Workspace",menu=w)
        self.root.config(menu=m)

    def _build_layout(self):
        C=self.C
        self.top=tk.Frame(self.root,height=52);self.top.pack(side=tk.TOP,fill=tk.X);self.top.pack_propagate(False)
        self.brand=tk.Label(self.top,text="⚔  D&D LANG",font=("Segoe UI",11,"bold"));self.brand.pack(side=tk.LEFT,padx=(16,12))
        self.file_label=tk.Label(self.top,text="untitled.dnd",font=("Segoe UI",10));self.file_label.pack(side=tk.LEFT)
        self.run_button=tk.Button(self.top,text="▶  Run",command=self.run_code,font=("Segoe UI",9,"bold"),relief="flat",bd=0,cursor="hand2",padx=14,pady=6);self.run_button.pack(side=tk.RIGHT,padx=(6,12),pady=8)
        self.settings_button=tk.Button(self.top,text="⚙",command=self.open_settings,font=("Segoe UI",13),relief="flat",bd=0,width=3,cursor="hand2");self.settings_button.pack(side=tk.RIGHT,pady=8)
        self.status_mode=tk.Label(self.top,text="READY",font=("Segoe UI",8,"bold"));self.status_mode.pack(side=tk.RIGHT,padx=10)

        body=tk.Frame(self.root);body.pack(fill=tk.BOTH,expand=True)
        self.sidebar=tk.Frame(body,width=270);self.sidebar.pack(side=tk.LEFT,fill=tk.Y);self.sidebar.pack_propagate(False)
        explorer_head=tk.Frame(self.sidebar,height=38);explorer_head.pack(fill=tk.X);explorer_head.pack_propagate(False)
        tk.Label(explorer_head,text="EXPLORER",font=("Segoe UI",8,"bold"),anchor="w").pack(side=tk.LEFT,padx=(12,4))
        for label,cmd in (("＋",self.create_file),("📁",self.create_folder),("↻",self.refresh_explorer),("📂",self.open_folder)):
            tk.Button(explorer_head,text=label,command=cmd,relief="flat",bd=0,font=("Segoe UI",10),padx=4,cursor="hand2").pack(side=tk.RIGHT,padx=1,pady=5)
        self.workspace_label=tk.Label(self.sidebar,text="NO FOLDER OPEN",anchor="w",font=("Segoe UI",8,"bold"),padx=12,pady=6);self.workspace_label.pack(fill=tk.X)
        tree_wrap=tk.Frame(self.sidebar);tree_wrap.pack(fill=tk.BOTH,expand=True,padx=(5,2),pady=(3,4))
        self.explorer=ttk.Treeview(tree_wrap,show="tree",selectmode="browse")
        self.explorer.pack(side=tk.LEFT,fill=tk.BOTH,expand=True)
        exp_scroll=tk.Scrollbar(tree_wrap,orient="vertical",command=self.explorer.yview);exp_scroll.pack(side=tk.RIGHT,fill=tk.Y);self.explorer.configure(yscrollcommand=exp_scroll.set)
        self.explorer.bind("<Double-1>",self._explorer_double_click)
        self.explorer.bind("<Return>",self._explorer_open_selected)
        self.explorer.bind("<Button-3>",self._explorer_context)
        self.side_hint=tk.Label(self.sidebar,text="Open a folder to browse your project.\nRight-click for file actions.",justify="left",anchor="w",font=("Segoe UI",8),padx=12,pady=12);self.side_hint.pack(fill=tk.X)
        self._explorer_menu=tk.Menu(self.root)
        self._explorer_menu.add_command(label="Open",command=self._explorer_open_selected)
        self._explorer_menu.add_separator()
        self._explorer_menu.add_command(label="New File",command=self.create_file)
        self._explorer_menu.add_command(label="New Folder",command=self.create_folder)
        self._explorer_menu.add_command(label="Rename",command=self.rename_selected)
        self._explorer_menu.add_command(label="Delete",command=self.delete_selected)
        self._explorer_menu.add_separator()
        self._explorer_menu.add_command(label="Refresh",command=self.refresh_explorer)

        center=tk.Frame(body);center.pack(side=tk.LEFT,fill=tk.BOTH,expand=True)
        self.pane=tk.PanedWindow(center,orient=tk.VERTICAL,sashwidth=5,bd=0,relief="flat");self.pane.pack(fill=tk.BOTH,expand=True)
        editor_wrap=tk.Frame(self.pane)
        self.linenumbers=tk.Text(editor_wrap,width=8,padx=7,border=0,state="disabled",wrap="none",font=(self.settings["font"],self.settings["font_size"]));self.linenumbers.pack(side=tk.LEFT,fill=tk.Y)
        self.editor=tk.Text(editor_wrap,wrap="none",undo=True,font=(self.settings["font"],self.settings["font_size"]),padx=12,pady=10,bd=0,highlightthickness=0,insertwidth=2,yscrollcommand=self._on_editor_yview,xscrollcommand=lambda a,b:self._sync_x(a,b));self.editor.pack(side=tk.LEFT,fill=tk.BOTH,expand=True)
        self.minimap=tk.Text(editor_wrap,width=18,wrap="none",state="disabled",bd=0,padx=7,pady=8,font=("Consolas",5),yscrollcommand=lambda a,b:self._noop());self.minimap.pack(side=tk.RIGHT,fill=tk.Y)
        self.pane.add(editor_wrap,minsize=250)
        console_wrap=tk.Frame(self.pane)
        con_head=tk.Frame(console_wrap,height=30);con_head.pack(fill=tk.X);con_head.pack_propagate(False)
        tk.Label(con_head,text="CONSOLE",font=("Segoe UI",8,"bold")).pack(side=tk.LEFT,padx=12)
        self.console_clear=tk.Button(con_head,text="Clear",command=self._clear_console,relief="flat",bd=0,font=("Segoe UI",8),padx=8);self.console_clear.pack(side=tk.RIGHT,padx=8,pady=4)
        self.console=tk.Text(console_wrap,height=9,wrap="word",bd=0,font=(self.settings["font"],self.settings["console_size"]),state="disabled",padx=12,pady=8);self.console.pack(fill=tk.BOTH,expand=True)
        self.pane.add(console_wrap,minsize=100)
        self.statusbar=tk.Frame(self.root,height=25);self.statusbar.pack(fill=tk.X);self.statusbar.pack_propagate(False)
        self.cursor_label=tk.Label(self.statusbar,text="Ln 1, Col 1",font=("Segoe UI",8));self.cursor_label.pack(side=tk.LEFT,padx=10)
        self.status_right=tk.Label(self.statusbar,text="D&D Lang  •  UTF-8  •  Spaces: 4",font=("Segoe UI",8));self.status_right.pack(side=tk.RIGHT,padx=10)

    def _bind_keys(self):
        for key,fn in [("<Control-n>",self.new_file),("<Control-o>",self.open_file),("<Control-s>",self.save_file),("<Control-S>",self.save_file_as),("<F5>",self.run_code),("<Control-l>",self._clear_console)]:self.root.bind(key,lambda e,fn=fn:fn())
        for key,fn in [("<KeyRelease>",self._on_key_release),("<ButtonRelease-1>",self._update_cursor),("<Return>",self._on_return),("<Tab>",self._on_tab),("<Shift-Tab>",self._on_shift_tab),("(",self._open_paren),(")",self._close_paren),("[",self._open_bracket),( "]",self._close_bracket),("{",self._open_brace),("}",self._close_brace),("\"",self._quote),("<Motion>",self._on_hover)]:self.editor.bind(key,fn)
        self.editor.bind("<Leave>",lambda e:self._hide_tooltip())

    def _configure_tags(self):
        C=self.C;tags={"decl":C["accent"],"control":"#c58ad9","io":"#55c7b1","bool":"#e2a45c","builtin":"#e1d27c","statname":"#55b9ef","kind":"#d9b77b","string":"#d99278","number":"#9fd18b","comment":"#65966b"}
        for n,c in tags.items():self.editor.tag_configure(n,foreground=c,font=(self.settings["font"],self.settings["font_size"],"bold" if self.settings.get("bold_keywords") and n not in ("string","comment") else "normal"))
        self.editor.tag_configure("current_line",background=C["current"])
    ALL_TAGS=("decl","control","io","bool","builtin","statname","kind","string","number","comment")

    def _apply_theme(self):
        C=self.C;self.root.configure(bg=C["bg"]);self.top.configure(bg=C["panel"]);self.sidebar.configure(bg=C["panel"]);self.brand.configure(bg=C["panel"],fg=C["accent"]);self.file_label.configure(bg=C["panel"],fg=C["muted"]);self.status_mode.configure(bg=C["panel"],fg=C["accent"]);self.settings_button.configure(bg=C["panel"],fg=C["muted"],activebackground=C["button_hover"]);self.run_button.configure(bg=C["accent"],fg=C["editor"],activebackground=C["accent2"]);self.side_hint.configure(bg=C["panel"],fg=C["muted"]);self.workspace_label.configure(bg=C["panel2"],fg=C["text"]);self.linenumbers.configure(bg=C["gutter"],fg=C["muted"]);self.editor.configure(bg=C["editor"],fg=C["text"],insertbackground=self.settings.get("cursor",DEFAULTS["cursor"]),selectbackground=C["select"],selectforeground=C["text"]);self.minimap.configure(bg=C["panel2"],fg=C["muted"]);self.console.configure(bg=C["console"],fg=C["console_text"],insertbackground=C["console_text"]);self.statusbar.configure(bg=C["panel2"]);self.cursor_label.configure(bg=C["panel2"],fg=C["muted"]);self.status_right.configure(bg=C["panel2"],fg=C["muted"]);self.console_clear.configure(bg=C["button"],fg=C["muted"],activebackground=C["button_hover"]);self._configure_tags();self._update_line_numbers();self._update_minimap()

    def _explorer_style(self):
        C=self.C
        style=ttk.Style(self.root)
        try:style.theme_use("clam")
        except Exception:pass
        style.configure("Treeview",background=C["panel"],foreground=C["text"],fieldbackground=C["panel"],borderwidth=0,rowheight=24,font=("Segoe UI",9))
        style.map("Treeview",background=[("selected",C["select"])],foreground=[("selected",C["text"])])

    def _update_fonts(self):self.editor.configure(font=(self.settings["font"],self.settings["font_size"]));self.linenumbers.configure(font=(self.settings["font"],self.settings["font_size"]));self.console.configure(font=(self.settings["font"],self.settings["console_size"]));self._configure_tags();self._highlight()
    def _on_editor_yview(self,a,b):self.linenumbers.yview_moveto(float(a));self.minimap.yview_moveto(float(a))
    def _sync_x(self,a,b):return None
    def _noop(self,*args):return None

    def _update_line_numbers(self,text=None):
        text=self.editor.get("1.0","end-1c") if text is None else text;addrs=compute_line_addresses(text);lines=[(a if self.settings["addresses"] else str(i)).rjust(5) for i,a in enumerate(addrs,1)];self.linenumbers.config(state="normal");self.linenumbers.delete("1.0","end");self.linenumbers.insert("1.0","\n".join(lines));self.linenumbers.config(state="disabled");self.status_right.config(text=f"D&D Lang  •  UTF-8  •  Spaces: {self.settings['tab_size']}");self.linenumbers.pack_forget();self.linenumbers.pack(side=tk.LEFT,fill=tk.Y) if self.settings["line_numbers"] else None

    def _update_minimap(self):
        text=self.editor.get("1.0","end-1c");self.minimap.config(state="normal");self.minimap.delete("1.0","end");self.minimap.insert("1.0",text);self.minimap.config(state="disabled");self.minimap.pack_forget();self.minimap.pack(side=tk.RIGHT,fill=tk.Y) if self.settings["minimap"] else None

    def _highlight(self,event=None):
        if self._highlight_job:
            try:self.root.after_cancel(self._highlight_job)
            except Exception:pass
        self._highlight_job=self.root.after(20,self._do_highlight)

    def _do_highlight(self):
        self._highlight_job=None;text=self.editor.get("1.0","end-1c")
        for t in self.ALL_TAGS:self.editor.tag_remove(t,"1.0","end")
        i=0
        while i<len(text):
            if text[i]=='"':
                j=i+1
                while j<len(text):
                    if text[j]=='\\':j+=2;continue
                    if text[j]=='"':j+=1;break
                    j+=1
                self.editor.tag_add("string",f"1.0+{i}c",f"1.0+{j}c");i=j;continue
            if text.startswith("--",i):
                j=text.find("\n",i)
                if j<0:j=len(text)
                self.editor.tag_add("comment",f"1.0+{i}c",f"1.0+{j}c");i=j;continue
            m=re.match(r"[A-Za-z_][A-Za-z0-9_]*",text[i:])
            if m:
                w=m.group(0);start=i;end=i+len(w);tag="decl" if w in DECL_WORDS else "control" if w in CONTROL_WORDS else "io" if w in IO_WORDS else "bool" if w in BOOL_WORDS else "builtin" if w in BUILTIN_WORDS else "statname" if w in STAT_WORDS else "kind" if w in KIND_WORDS else None
                if tag:self.editor.tag_add(tag,f"1.0+{start}c",f"1.0+{end}c")
                i=end;continue
            m=re.match(r"(?:\d+(?:\.\d*)?|\.\d+)",text[i:])
            if m:
                end=i+len(m.group(0));self.editor.tag_add("number",f"1.0+{i}c",f"1.0+{end}c");i=end;continue
            i+=1
        self._update_line_numbers(text);self._update_minimap();self._update_current_line()

    def _update_current_line(self):
        self.editor.tag_remove("current_line","1.0","end")
        if self.settings.get("current_line"):
            line=self.editor.index(tk.INSERT).split('.')[0];self.editor.tag_add("current_line",f"{line}.0",f"{line}.end")

    def _on_key_release(self,event=None):self._update_cursor();self._highlight()
    def _update_cursor(self,event=None):
        i=self.editor.index(tk.INSERT);parts=i.split('.');self.cursor_label.config(text=f"Ln {parts[0]}, Col {int(parts[1])+1}");self._update_current_line()
    def _on_return(self,e):
        line=self.editor.get("insert linestart","insert");indent=re.match(r"[ \t]*",line).group(0);extra="    " if line.rstrip().endswith(":") else "";self.editor.insert("insert","\n"+indent+extra);return "break"
    def _on_tab(self,e):self.editor.insert("insert"," "*self.settings["tab_size"]);return "break"
    def _on_shift_tab(self,e):
        line=self.editor.get("insert linestart","insert");n=min(self.settings["tab_size"],len(line)-len(line.lstrip(" ")));self.editor.delete("insert linestart",f"insert linestart+{n}c");return "break"
    def _pair(self,open_c,close_c):self.editor.insert("insert",open_c+close_c);self.editor.mark_set("insert","insert-1c");return "break"
    def _close(self,c):
        if self.editor.get("insert", "insert+1c")==c:self.editor.mark_set("insert","insert+1c");return "break"
    def _open_paren(self,e):return self._pair("(",")")
    def _close_paren(self,e):return self._close(")")
    def _open_bracket(self,e):return self._pair("[","]")
    def _close_bracket(self,e):return self._close("]")
    def _open_brace(self,e):return self._pair("{","}")
    def _close_brace(self,e):return self._close("}")
    def _quote(self,e):
        i=self.editor.index(tk.INSERT)
        if self.editor.get(i,f"{i}+1c")=="\"":self.editor.mark_set(tk.INSERT,f"{i}+1c");return "break"
        return self._pair('"','"')

    def _word_at(self,idx):
        ln=idx.split('.')[0];line=self.editor.get(f"{ln}.0",f"{ln}.0 lineend");c=int(idx.split('.')[1]);a=c
        while a>0 and (line[a-1].isalnum() or line[a-1]=='_'):a-=1
        b=c
        while b<len(line) and (line[b].isalnum() or line[b]=='_'):b+=1
        return line[a:b]
    def _on_hover(self,e):
        w=self._word_at(self.editor.index(f"@{e.x},{e.y}"))
        if w==self._last_hover_word:return
        self._last_hover_word=w
        if w in HOVER_DOCS:self._show_tooltip(e.x_root,e.y_root,w,HOVER_DOCS[w])
        else:self._hide_tooltip()
    def _show_tooltip(self,x,y,w,t):
        self._hide_tooltip();self.tooltip=tk.Toplevel(self.root);self.tooltip.wm_overrideredirect(True);self.tooltip.wm_geometry(f"+{x+14}+{y+16}");C=self.C;f=tk.Frame(self.tooltip,bg=C["panel2"],relief="solid",bd=1);f.pack();tk.Label(f,text=w,bg=C["panel2"],fg=C["accent"],font=("Segoe UI",9,"bold")).pack(fill="x",padx=8,pady=(6,1));tk.Label(f,text=t,bg=C["panel2"],fg=C["text"],font=("Segoe UI",9),wraplength=420,justify="left").pack(fill="x",padx=8,pady=(0,7))
    def _hide_tooltip(self):
        if self.tooltip:
            try:self.tooltip.destroy()
            except Exception:pass
        self.tooltip=None;self._last_hover_word=None

    def new_file(self):self.editor.delete("1.0","end");self.current_path=None;self._set_file_title("untitled.dnd");self._highlight()
    def _set_file_title(self,name):self.root.title(f"D&D Lang IDE — {name}");self.file_label.config(text=name)
    def open_file(self):
        p=filedialog.askopenfilename(title="Open D&D Lang File",filetypes=[("D&D files","*.dnd"),("Text files","*.txt"),("All files","*.*")])
        if not p:return
        self._open_path(p)
        if not self.workspace_root:self.workspace_root=os.path.dirname(os.path.abspath(p));self.workspace_label.config(text=os.path.basename(self.workspace_root) or self.workspace_root);self.refresh_explorer()
    def save_file(self):
        if self.current_path is None:return self.save_file_as()
        try:
            with open(self.current_path,"w",encoding="utf-8") as f:f.write(self.editor.get("1.0","end-1c"))
            self.status_mode.config(text="SAVED")
            if self.workspace_root:self.refresh_explorer()
        except Exception as e:messagebox.showerror("Save failed",str(e),parent=self.root)
    def save_file_as(self):
        p=filedialog.asksaveasfilename(defaultextension=".dnd",filetypes=[("D&D files","*.dnd"),("All files","*.*")])
        if p:
            self.current_path=p;self._set_file_title(os.path.basename(p))
            if not self.workspace_root:self.workspace_root=os.path.dirname(os.path.abspath(p));self.workspace_label.config(text=os.path.basename(self.workspace_root) or self.workspace_root)
            self.save_file();self.refresh_explorer()

    def open_folder(self):
        p=filedialog.askdirectory(title="Open D&D Lang Folder")
        if not p:return
        self.workspace_root=os.path.abspath(p);self.workspace_label.config(text=os.path.basename(self.workspace_root) or self.workspace_root);self.refresh_explorer()
    def refresh_explorer(self):
        if not hasattr(self,"explorer"):return
        for item in self.explorer.get_children():self.explorer.delete(item)
        if not self.workspace_root or not os.path.isdir(self.workspace_root):return
        root_id=self.explorer.insert("","end",text="📂  "+os.path.basename(self.workspace_root),open=True,values=(self.workspace_root,"folder"))
        self._populate_explorer(root_id,self.workspace_root)
    def _populate_explorer(self,parent,path):
        try:items=sorted(os.listdir(path),key=lambda x:(not os.path.isdir(os.path.join(path,x)),x.lower()))
        except OSError:return
        for name in items:
            if name in {".git","__pycache__"} or name.startswith("."):continue
            full=os.path.join(path,name)
            if os.path.isdir(full):
                iid=self.explorer.insert(parent,"end",text="📁  "+name,values=(full,"folder"));self._populate_explorer(iid,full)
            else:
                icon="📜" if name.lower().endswith(".dnd") else "📄";self.explorer.insert(parent,"end",text=f"{icon}  {name}",values=(full,"file"))
    def _explorer_path(self,item=None):
        item=item or self.explorer.focus()
        if not item:return None,None
        vals=self.explorer.item(item,"values")
        return (vals[0],vals[1]) if len(vals)>=2 else (None,None)
    def _explorer_double_click(self,e):self._explorer_open_selected(e)
    def _explorer_open_selected(self,e=None):
        path,kind=self._explorer_path()
        if path and kind=="file":self._open_path(path)
        elif path and kind=="folder":
            item=self.explorer.focus();self.explorer.item(item,open=not self.explorer.item(item,"open"))
    def _explorer_context(self,e):
        item=self.explorer.identify_row(e.y)
        if item:self.explorer.selection_set(item);self.explorer.focus(item);self._explorer_menu.tk_popup(e.x_root,e.y_root)
        else:self._explorer_menu.tk_popup(e.x_root,e.y_root)
    def _selected_directory(self):
        path,kind=self._explorer_path()
        if kind=="folder":return path
        if kind=="file":return os.path.dirname(path)
        return self.workspace_root
    def create_file(self):
        base=self._selected_directory()
        if not base:return
        name=simpledialog.askstring("New File","File name:",parent=self.root)
        if not name:return
        path=os.path.join(base,name)
        if os.path.exists(path):return messagebox.showerror("Create file",f"Already exists:\n{path}",parent=self.root)
        try:
            with open(path,"w",encoding="utf-8") as f:f.write("")
            self.refresh_explorer();self._open_path(path)
        except Exception as e:messagebox.showerror("Create file",str(e),parent=self.root)
    def create_folder(self):
        base=self._selected_directory()
        if not base:return
        name=simpledialog.askstring("New Folder","Folder name:",parent=self.root)
        if not name:return
        path=os.path.join(base,name)
        try:os.makedirs(path,exist_ok=False);self.refresh_explorer()
        except Exception as e:messagebox.showerror("Create folder",str(e),parent=self.root)
    def rename_selected(self):
        path,kind=self._explorer_path()
        if not path:return
        name=simpledialog.askstring("Rename","New name:",initialvalue=os.path.basename(path),parent=self.root)
        if not name:return
        dest=os.path.join(os.path.dirname(path),name)
        try:os.rename(path,dest);self.refresh_explorer()
        except Exception as e:messagebox.showerror("Rename",str(e),parent=self.root)
    def delete_selected(self):
        path,kind=self._explorer_path()
        if not path or path==self.workspace_root:return
        if not messagebox.askyesno("Delete",f"Delete {os.path.basename(path)}?",parent=self.root):return
        try:
            if os.path.isdir(path):
                import shutil;shutil.rmtree(path)
            else:os.remove(path)
            if self.current_path and os.path.abspath(self.current_path)==os.path.abspath(path):self.new_file()
            self.refresh_explorer()
        except Exception as e:messagebox.showerror("Delete",str(e),parent=self.root)
    def _open_path(self,p):
        try:
            with open(p,"r",encoding="utf-8") as f:s=f.read()
            self.editor.delete("1.0","end");self.editor.insert("1.0",s);self.current_path=os.path.abspath(p);self._set_file_title(os.path.basename(p));self._highlight();self.status_mode.config(text="READY")
        except Exception as e:messagebox.showerror("Open failed",str(e),parent=self.root)

    def run_code(self):
        s=self.editor.get("1.0","end-1c");self._clear_console();self.run_button.config(state="disabled",text="⏳  Running");self.status_mode.config(text="RUNNING",fg=self.C["accent"]);threading.Thread(target=self._run_in_thread,args=(s,),daemon=True).start()
    def _run_in_thread(self,s):
        try:Interpreter(output_func=self._queue_output,input_func=self._ask_input).run(parse(tokenize(s)))
        except (SyntaxError,DMError,ValueError) as e:self._queue_output(f"DM: {e}")
        except Exception as e:self._queue_output(f"DM: something went very wrong ({e})")
        finally:self.output_queue.put(("__DONE__",None))
    def _queue_output(self,t):self.output_queue.put(("line",t))
    def _flush_output_queue(self):
        while True:
            try:k,p=self.output_queue.get_nowait()
            except queue.Empty:break
            if k=="line":self._append_console(p+"\n")
            elif k=="__DONE__":
                self.run_button.config(state="normal",text="▶  Run")
                self.status_mode.config(text="READY",fg=self.C["accent"])
    def _ask_input(self,prompt):
        def show():
            # Flush interpreter output before the modal prompt takes focus.
            self._flush_output_queue()
            self.root.update_idletasks()
            v=simpledialog.askstring("Player Input",prompt,parent=self.root)
            self.input_result_queue.put(v if v is not None else "")
        self.root.after(0,show);return self.input_result_queue.get()
    def _poll_output_queue(self):
        self._flush_output_queue()
        self.root.after(60,self._poll_output_queue)
    def _append_console(self,t):
        self.console.config(state="normal");self.console.insert("end",t);self.console.see("end");self.console.config(state="disabled")
    def _clear_console(self):self.console.config(state="normal");self.console.delete("1.0","end");self.console.config(state="disabled")

    def toggle_minimap(self):self.settings["minimap"]=not self.settings["minimap"];self._save_settings();self._update_minimap()
    def toggle_line_numbers(self):self.settings["line_numbers"]=not self.settings["line_numbers"];self._save_settings();self._update_line_numbers()
    def toggle_addresses(self):self.settings["addresses"]=not self.settings["addresses"];self._save_settings();self._update_line_numbers()
    def toggle_wrap(self):self.settings["word_wrap"]=not self.settings["word_wrap"];self.editor.configure(wrap="word" if self.settings["word_wrap"] else "none");self._save_settings()

    def open_settings(self):
        w=tk.Toplevel(self.root);w.title("D&D Lang IDE Settings");w.transient(self.root);w.grab_set();w.resizable(False,False);C=self.C;w.configure(bg=C["panel"])
        frm=tk.Frame(w,bg=C["panel"],padx=16,pady=16);frm.pack(fill=tk.BOTH,expand=True)
        def row(label,widget,row):tk.Label(frm,text=label,bg=C["panel"],fg=C["text"],anchor="w",font=("Segoe UI",9)).grid(row=row,column=0,sticky="w",padx=(0,12),pady=6);widget.grid(row=row,column=1,sticky="ew",pady=6)
        frm.columnconfigure(1,weight=1)
        theme=tk.StringVar(value=self.settings["theme"]);font=tk.StringVar(value=self.settings["font"]);fs=tk.IntVar(value=self.settings["font_size"]);cs=tk.IntVar(value=self.settings["console_size"]);tabs=tk.IntVar(value=self.settings["tab_size"]);cursor=tk.StringVar(value=self.settings.get("cursor",DEFAULTS["cursor"]))
        cb=tk.OptionMenu(frm,theme,*THEMES);cb.configure(bg=C["button"],fg=C["text"],activebackground=C["button_hover"],highlightthickness=0);row("Theme",cb,0)
        fonts=["Consolas","Cascadia Mono","Courier New","Lucida Console","Segoe UI Mono"]
        fb=tk.OptionMenu(frm,font,*fonts);fb.configure(bg=C["button"],fg=C["text"],activebackground=C["button_hover"],highlightthickness=0);row("Editor font",fb,1)
        row("Editor size",tk.Spinbox(frm,from_=8,to=32,textvariable=fs,width=8),2);row("Console size",tk.Spinbox(frm,from_=8,to=28,textvariable=cs,width=8),3);row("Indent size",tk.Spinbox(frm,from_=1,to=8,textvariable=tabs,width=8),4)
        cf=tk.Frame(frm,bg=C["panel"]);tk.Entry(cf,textvariable=cursor,width=12).pack(side=tk.LEFT);tk.Button(cf,text="Pick",command=lambda:self._pick_setting_color(cursor),relief="flat",bd=0,bg=C["button"],fg=C["text"]).pack(side=tk.LEFT,padx=5);row("Cursor",cf,5)
        booleans=[("Line numbers","line_numbers"),("D&D addresses","addresses"),("Word wrap","word_wrap"),("Minimap","minimap"),("Current line","current_line"),("Bold keywords","bold_keywords")]
        vars_=[]
        for r,(label,key) in enumerate(booleans,6):v=tk.BooleanVar(value=self.settings[key]);tk.Checkbutton(frm,text=label,variable=v,bg=C["panel"],fg=C["text"],selectcolor=C["editor"],activebackground=C["panel"],activeforeground=C["text"]).grid(row=r,column=0,columnspan=2,sticky="w",pady=3);vars_.append((key,v))
        def save():
            self.settings.update({"theme":theme.get(),"font":font.get(),"font_size":fs.get(),"console_size":cs.get(),"tab_size":tabs.get(),"cursor":cursor.get()})
            for key,v in vars_:self.settings[key]=v.get()
            self._save_settings();self.editor.configure(wrap="word" if self.settings["word_wrap"] else "none");self._apply_theme();self._explorer_style();self._update_fonts();w.destroy()
        tk.Button(frm,text="Save",command=save,relief="flat",bd=0,bg=C["accent"],fg=C["editor"],padx=14,pady=6).grid(row=12,column=0,columnspan=2,pady=(14,0))
    def _pick_setting_color(self,var):
        c=colorchooser.askcolor(parent=self.root,title="Choose color")[1]
        if c:var.set(c)


def main():
    root=tk.Tk();DndIDE(root);root.mainloop()
if __name__=="__main__":main()
