import tkinter as tk
from tkinter import filedialog, simpledialog, colorchooser, messagebox
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
HOVER_DOCS={"ability":"Declares a normal value.","pouch":"Declares named key-value data.","vault":"Declares a file vault.","pass":"Does nothing. Useful as a placeholder.","raise":"Raises a DM error on purpose.","finally":"Runs after submit/consider.","submit":"Runs code that might fail.","consider":"Handles an error after submit.","issue":"Names the error kind.","none":"The empty value. Its language type is NoneType.","party":"Creates a D&D Lang sequence/range.","type":"Returns a D&D Lang type name.","bool":"Converts a value to honor/lie.","list":"Converts a value to a list.","sum":"Adds a sequence or supplied numbers.","sorted":"Returns a sorted copy.","reversed":"Returns a reversed copy.","reverse":"Reverses a list in place.","enumerate":"Returns pouches containing index and value.","zip":"Combines lists by matching positions.","map":"Applies a quest to each list item.","filter":"Keeps list items whose quest result is honor.","reduce":"Combines a list with a two-argument quest.","read":"Reads text from a vault or path.","write":"Writes text to a vault.","close":"Seals a vault.","append":"Adds to a list or vault.","forget":"Removes a named variable from scope.","memory":"Reports a small runtime memory estimate.","replace":"Scroll method: replaces matching text.","find":"Scroll method: finds text.","count":"Scroll method: counts matching text.","contains":"Checks whether a collection contains a value.","len":"Returns length.","num":"Converts to a number.","str":"Converts to a Scroll.","summon":"Creates a homebrew instance.","homebrew":"Defines a custom D&D type.","quest":"Defines a function-like quest.","embark":"Calls a quest.","reward":"Returns a value from a quest.","init":"Pulls a caller variable into an isolated quest.","narrate":"Prints output.","player":"Gets player input.","attempt":"Conditional block.","or_attempt":"Additional conditional branch.","fail":"Fallback branch.","adventure":"Repeats or iterates a block.","while":"Loops while a condition is honor.","for":"Starts a party loop.","quit":"Stops the nearest loop.","continue":"Skips the current loop iteration.","force":"Moves execution forward.","sway":"Reorders unexecuted code. Supports addresses such as 3 or 3.1."}

THEMES={
    "D&D Dark":{"bg":"#101318","panel":"#171b22","panel2":"#1d232d","editor":"#11151b","gutter":"#171b22","text":"#d9e1ea","muted":"#7f8b99","accent":"#d6a85f","accent2":"#8f6f3f","console":"#0b0f13","console_text":"#8fe388","select":"#334155","current":"#1a222d","button":"#202936","button_hover":"#2a3545"},
    "Midnight":{"bg":"#090b14","panel":"#111426","panel2":"#171b31","editor":"#0b0e1a","gutter":"#111426","text":"#dfe5ff","muted":"#737b9b","accent":"#8c7cff","accent2":"#5b52aa","console":"#080a12","console_text":"#7ee7ff","select":"#30365c","current":"#151a2d","button":"#1b2140","button_hover":"#28305a"},
    "Forest":{"bg":"#0d1511","panel":"#132019","panel2":"#1a2a21","editor":"#0d1712","gutter":"#132019","text":"#dce9df","muted":"#78907e","accent":"#7bc47f","accent2":"#4d8053","console":"#09100c","console_text":"#9be7a0","select":"#294335","current":"#16251b","button":"#1a2c21","button_hover":"#254031"},
    "Ember":{"bg":"#18100f","panel":"#241614","panel2":"#2e1c19","editor":"#170f0e","gutter":"#241614","text":"#f2e1da","muted":"#a48479","accent":"#ff9a62","accent2":"#a65b3b","console":"#100a09","console_text":"#ffc078","select":"#513026","current":"#281815","button":"#34201a","button_hover":"#4a2b21"},
    "Light":{"bg":"#eef1f5","panel":"#ffffff","panel2":"#e4e8ee","editor":"#fbfcfe","gutter":"#e9edf2","text":"#253041","muted":"#6d7786","accent":"#9a6b18","accent2":"#c59a45","console":"#20252c","console_text":"#a9f0a0","select":"#cbd7e8","current":"#edf2f8","button":"#e2e7ee","button_hover":"#d5dde8"}}
DEFAULTS={"theme":"D&D Dark","font":"Consolas","font_size":12,"console_size":11,"tab_size":4,"line_numbers":True,"addresses":True,"word_wrap":False,"minimap":True,"current_line":True,"bold_keywords":False,"cursor":"#ffffff","accent_override":None}

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
        self.root=root;self.current_path=None;self.output_queue=queue.Queue();self.input_result_queue=queue.Queue();self.tooltip=None;self._last_hover_word=None;self._highlight_job=None;self.settings=dict(DEFAULTS);self._load_settings();self.root.title("D&D Lang IDE — untitled.dnd");self.root.minsize(850,560);self._build_menu();self._build_layout();self._bind_keys();self._apply_theme();self._highlight();self._poll_output_queue()
    def _settings_path(self):return os.path.join(os.path.expanduser("~"),".dnd_lang_ide.json")
    def _load_settings(self):
        try:
            with open(self._settings_path(),"r",encoding="utf-8") as f:self.settings.update(json.load(f))
        except Exception:pass
        for key,value in DEFAULTS.items():
            self.settings.setdefault(key,value)
        if self.settings.get("theme") not in THEMES:self.settings["theme"]="D&D Dark"
    def _save_settings(self):
        try:
            with open(self._settings_path(),"w",encoding="utf-8") as f:json.dump(self.settings,f,indent=2)
        except Exception:pass
    @property
    def C(self):
        c=THEMES[self.settings["theme"]].copy()
        if self.settings.get("accent_override"):c["accent"]=self.settings["accent_override"]
        return c
    def _build_menu(self):
        m=tk.Menu(self.root);f=tk.Menu(m);f.add_command(label="New",command=self.new_file,accelerator="Ctrl+N");f.add_command(label="Open...",command=self.open_file,accelerator="Ctrl+O");f.add_command(label="Save",command=self.save_file,accelerator="Ctrl+S");f.add_command(label="Save As...",command=self.save_file_as,accelerator="Ctrl+Shift+S");f.add_separator();f.add_command(label="Settings...",command=self.open_settings);f.add_separator();f.add_command(label="Exit",command=self.root.quit);m.add_cascade(label="File",menu=f);r=tk.Menu(m);r.add_command(label="Run",command=self.run_code,accelerator="F5");r.add_command(label="Clear Console",command=self._clear_console,accelerator="Ctrl+L");m.add_cascade(label="Run",menu=r);v=tk.Menu(m);v.add_command(label="Settings...",command=self.open_settings);v.add_command(label="Toggle Minimap",command=self.toggle_minimap);v.add_command(label="Toggle Line Numbers",command=self.toggle_line_numbers);v.add_command(label="Toggle Addresses",command=self.toggle_addresses);v.add_command(label="Toggle Word Wrap",command=self.toggle_wrap);m.add_cascade(label="View",menu=v);self.root.config(menu=m)
    def _build_layout(self):
        self.top=tk.Frame(self.root,height=52);self.top.pack(fill=tk.X);self.top.pack_propagate(False);self.brand=tk.Label(self.top,text="⚔  D&D LANG",font=("Segoe UI",11,"bold"));self.brand.pack(side=tk.LEFT,padx=(16,12));self.file_label=tk.Label(self.top,text="untitled.dnd",font=("Segoe UI",10));self.file_label.pack(side=tk.LEFT);self.run_button=tk.Button(self.top,text="▶  Run",command=self.run_code,font=("Segoe UI",9,"bold"),relief="flat",bd=0,cursor="hand2",padx=14,pady=6);self.run_button.pack(side=tk.RIGHT,padx=(6,12),pady=8);self.settings_button=tk.Button(self.top,text="⚙",command=self.open_settings,font=("Segoe UI",13),relief="flat",bd=0,width=3,cursor="hand2");self.settings_button.pack(side=tk.RIGHT,pady=8);self.status_mode=tk.Label(self.top,text="READY",font=("Segoe UI",8,"bold"));self.status_mode.pack(side=tk.RIGHT,padx=10)
        body=tk.Frame(self.root);body.pack(fill=tk.BOTH,expand=True);self.sidebar=tk.Frame(body,width=185);self.sidebar.pack(side=tk.LEFT,fill=tk.Y);self.sidebar.pack_propagate(False);tk.Label(self.sidebar,text="EXPLORER",font=("Segoe UI",8,"bold"),anchor="w").pack(fill=tk.X,padx=14,pady=(16,8));self.side_file=tk.Label(self.sidebar,text="▸  untitled.dnd",anchor="w",font=("Segoe UI",9),padx=14,pady=7);self.side_file.pack(fill=tk.X);self.side_hint=tk.Label(self.sidebar,text="\nD&D Lang\nIDE v6",justify="left",anchor="w",font=("Segoe UI",8),padx=14,pady=14);self.side_hint.pack(side=tk.BOTTOM,fill=tk.X)
        center=tk.Frame(body);center.pack(side=tk.LEFT,fill=tk.BOTH,expand=True);self.pane=tk.PanedWindow(center,orient=tk.VERTICAL,sashwidth=5,bd=0,relief="flat");self.pane.pack(fill=tk.BOTH,expand=True);editor_wrap=tk.Frame(self.pane);self.linenumbers=tk.Text(editor_wrap,width=8,padx=7,border=0,state="disabled",wrap="none",font=(self.settings["font"],self.settings["font_size"]));self.linenumbers.pack(side=tk.LEFT,fill=tk.Y);self.editor=tk.Text(editor_wrap,wrap="none",undo=True,font=(self.settings["font"],self.settings["font_size"]),padx=12,pady=10,bd=0,highlightthickness=0,insertwidth=2,yscrollcommand=self._on_editor_yview);self.editor.pack(side=tk.LEFT,fill=tk.BOTH,expand=True);self.minimap=tk.Text(editor_wrap,width=18,wrap="none",state="disabled",bd=0,padx=7,pady=8,font=("Consolas",5));self.minimap.pack(side=tk.RIGHT,fill=tk.Y);self.pane.add(editor_wrap,minsize=250);console_wrap=tk.Frame(self.pane);con_head=tk.Frame(console_wrap,height=30);con_head.pack(fill=tk.X);con_head.pack_propagate(False);tk.Label(con_head,text="CONSOLE",font=("Segoe UI",8,"bold")).pack(side=tk.LEFT,padx=12);self.console_clear=tk.Button(con_head,text="Clear",command=self._clear_console,relief="flat",bd=0,font=("Segoe UI",8),padx=8);self.console_clear.pack(side=tk.RIGHT,padx=8,pady=4);self.console=tk.Text(console_wrap,height=9,wrap="word",bd=0,font=(self.settings["font"],self.settings["console_size"]),state="disabled",padx=12,pady=8);self.console.pack(fill=tk.BOTH,expand=True);self.pane.add(console_wrap,minsize=100)
        self.statusbar=tk.Frame(self.root,height=25);self.statusbar.pack(fill=tk.X);self.statusbar.pack_propagate(False);self.cursor_label=tk.Label(self.statusbar,text="Ln 1, Col 1",font=("Segoe UI",8));self.cursor_label.pack(side=tk.LEFT,padx=10);self.status_right=tk.Label(self.statusbar,text="D&D Lang  •  UTF-8  •  Spaces: 4",font=("Segoe UI",8));self.status_right.pack(side=tk.RIGHT,padx=10)
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
        C=self.C;self.root.configure(bg=C["bg"]);self.top.configure(bg=C["panel"]);self.sidebar.configure(bg=C["panel"]);self.brand.configure(bg=C["panel"],fg=C["accent"]);self.file_label.configure(bg=C["panel"],fg=C["muted"]);self.status_mode.configure(bg=C["panel"],fg=C["accent"]);self.settings_button.configure(bg=C["panel"],fg=C["muted"],activebackground=C["button_hover"]);self.run_button.configure(bg=C["accent"],fg=C["editor"],activebackground=C["accent2"]);self.side_file.configure(bg=C["panel2"],fg=C["text"]);self.side_hint.configure(bg=C["panel"],fg=C["muted"]);self.linenumbers.configure(bg=C["gutter"],fg=C["muted"]);self.editor.configure(bg=C["editor"],fg=C["text"],insertbackground=self.settings.get("cursor",DEFAULTS["cursor"]),selectbackground=C["select"],selectforeground=C["text"]);self.minimap.configure(bg=C["panel2"],fg=C["muted"]);self.console.configure(bg=C["console"],fg=C["console_text"],insertbackground=C["console_text"]);self.statusbar.configure(bg=C["panel2"]);self.cursor_label.configure(bg=C["panel2"],fg=C["muted"]);self.status_right.configure(bg=C["panel2"],fg=C["muted"]);self.console_clear.configure(bg=C["button"],fg=C["muted"],activebackground=C["button_hover"]);self._configure_tags();self._update_line_numbers();self._update_minimap()
