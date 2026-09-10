"""
A simple IDE for the D&D-themed language, built with Tkinter (bundled with Python,
no extra installs needed).

Features:
- Code editor with basic syntax highlighting (keywords, strings, numbers, comments)
- Run button that executes the current code and shows output in a console panel
- player(...) input shows as a popup dialog instead of needing a terminal
- Open / Save / Save As for .dnd files

Run this file directly: python ide.py
"""

import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
import threading
import queue
import re

from lexer import tokenize
from parser import parse
from interpreter import Interpreter, DMError

KEYWORDS = [
    "ability", "summon", "homebrew", "quest", "embark", "reward", "init",
    "narrate", "player", "attempt", "or_attempt", "fail", "adventure",
    "quit", "continue", "while", "for", "in", "party",
    "submit", "consider", "issue", "honor", "lie", "extra",
]

# Categorized word groups, each gets its own highlight color.
DECL_WORDS = ["ability", "summon", "homebrew", "quest", "init", "extra", "STATS"]
CONTROL_WORDS = ["attempt", "or_attempt", "fail", "adventure", "while", "for", "in",
                  "party", "quit", "continue", "submit", "consider", "issue"]
IO_WORDS = ["narrate", "player", "embark", "reward"]
BOOL_WORDS = ["honor", "lie"]
BUILTIN_WORDS = ["force", "sway", "endure", "perceive", "solve", "roll",
                  "max", "min", "len", "num", "str", "append", "push", "pop",
                  "map", "filter", "index",
                  "lower", "upper", "trim", "clean", "title", "starts", "ends",
                  "contains", "empty", "words", "split", "join", "find", "count"]
STAT_NAME_WORDS = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
KIND_WORDS = ["character", "item", "monster", "spell"]

def _word_pattern(words):
    return r"\b(" + "|".join(words) + r")\b"

DECL_PATTERN = _word_pattern(DECL_WORDS)
CONTROL_PATTERN = _word_pattern(CONTROL_WORDS)
IO_PATTERN = _word_pattern(IO_WORDS)
BOOL_PATTERN = _word_pattern(BOOL_WORDS)
BUILTIN_PATTERN = _word_pattern(BUILTIN_WORDS)
STAT_NAME_PATTERN = _word_pattern(STAT_NAME_WORDS)
KIND_PATTERN = _word_pattern(KIND_WORDS)
STRING_PATTERN = r'"[^"]*"'
NUMBER_PATTERN = r"\b\d+(\.\d+)?\b"
COMMENT_PATTERN = r"--.*?--|--.*$"


def compute_line_addresses(text):
    """Computes the major/minor address for every visual line, matching the
    language's own addressing scheme: top-level statements are 0, 1, 2, ...
    and any indented (nested) line gets major.minor, e.g. 2.0, 2.1, 2.2."""
    from lexer import strip_comments

    addresses = []
    major = -1
    minor = None
    for raw_line in text.split("\n"):
        code_only = strip_comments(raw_line)
        if code_only.strip() == "":
            addresses.append("")
            continue
        indent = len(code_only) - len(code_only.lstrip(" \t"))
        if indent == 0:
            major += 1
            minor = None
            addresses.append(str(major))
        else:
            minor = 0 if minor is None else minor + 1
            addresses.append(f"{major}.{minor}" if major >= 0 else "")
    return addresses

# Word-under-cursor reference used for hover tooltips.
HOVER_DOCS = {
    "ability":    "Declares a new variable. Example: ability x = 5",
    "summon":     "Creates an instance of a homebrew. Example: summon hero = Hero()",
    "homebrew":   "Defines a custom type. Kind must be character/item/monster/spell.\nhomebrew character Hero:\n    hp = 20",
    "quest":      "Defines a function. Isolated scope by default — use parameters or 'init' to reach outer variables.",
    "embark":     "Calls a quest. Example: embark MyQuest(a, b)",
    "reward":     "Returns a value from a quest.",
    "init":       "Pulls a variable from the caller's scope into an isolated quest. Example: init a, b",
    "narrate":    "Prints output. Example: narrate(\"Hello\") or narrate x",
    "player":     "Gets input from the person running the program. Example: player(\"Name: \")",
    "attempt":    "If-statement. Example: attempt (x > 5):",
    "or_attempt": "Elif-statement. Follows an attempt block.",
    "fail":       "Else-statement. Follows attempt/or_attempt blocks.",
    "adventure":  "Repeats a block n times. Example: adventure (3): or iterates: adventure card in deck:",
    "quit":       "Breaks out of the nearest adventure/while/for loop.",
    "continue":   "Skips to the next iteration of the nearest loop.",
    "while":      "A loop that re-checks its condition each time. Example: while (x < 10):",
    "for":        "Starts a party for-loop. Example: for p in party(5):",
    "party":      "Used with 'for': party(n) counts 0..n-1, party(a, b) ranges a..b-1, party(list) iterates a list, party(STATS) iterates stat names.",
    "submit":     "Try-block: runs code that might fail. Pair with 'consider'.",
    "consider":   "Catch-block after 'submit'. 'consider issue ValueError:' catches a specific error; bare 'consider:' catches anything.",
    "issue":      "Names the error type to catch after 'consider'. Example: consider issue ValueError:",
    "honor":      "The boolean value 'true'.",
    "lie":        "The boolean value 'false'.",
    "extra":      "Adds a custom stat inside a STATS block, beyond the 6 defaults.",
    "STATS":      "Built-in block on any homebrew. 6 default stats (STR/DEX/CON/INT/WIS/CHA), each with .number and .mod.",
    "STR":        "Strength stat. Used by 'force' (x + STR value) — flat addition.",
    "DEX":        "Dexterity stat. Will drive 'initiative' (code reordering) — not implemented yet.",
    "CON":        "Constitution stat. Used by 'endure' (repeated % reduction over multiple hits).",
    "INT":        "Intelligence stat. Used by 'solve' (dice check vs a difficulty).",
    "WIS":        "Wisdom stat. Used by 'perceive' (average of a list, adjusted by WIS).",
    "CHA":        "Charisma stat. Used by 'sway' (x * CHA value) — flat multiplication.",
    "force":      "STR mechanic: instance.force.mod(x) or .number(x) → x + STR value.",
    "sway":       "CHA mechanic: instance.sway.mod(x) or .number(x) → x * CHA value.",
    "endure":     "CON mechanic: instance.endure.mod(x, times) applies a repeated % reduction. Plain form: endure(x, times, rate).",
    "perceive":   "WIS mechanic: instance.perceive.mod(list) averages a list then adds WIS value. Plain form: perceive(list).",
    "solve":      "INT mechanic (dice check): instance.solve.mod \\_(difficulty) — rolls a die sized by INT's number/mod, compares with a comparator.",
    "roll":       "Rolls a die. Example: roll(d6) returns 1–6. d0 always returns 0.",
    "max":        "Returns the largest number. max(list) or max(a, b, ...).",
    "min":        "Returns the smallest number. min(list) or min(a, b, ...).",
    "len":        "Returns the length of a list or Scroll.",
    "num":        "Converts a Scroll to a number. Raises a ValueError if it isn't valid.",
    "str":        "Converts any value to a Scroll (text).",
    "append":     "Adds a value to the end of a list. Example: append(deck, card)",
    "push":       "Adds a value to the end of a list. Example: push(deck, card)",
    "pop":        "Removes and returns an item from a list. pop(list) removes the last item; pop(list, index) removes a position.",
    "map":        "Applies a quest to every item in a list and returns the results.",
    "filter":     "Keeps list items for which a quest returns honor.",
    "index":      "Returns the position of a value in a list, or -1 if it isn't there.",
    "character":  "One of the 4 fixed homebrew kinds. Needs 3 fields spanning 2+ types (max 2 of one type counted).",
    "item":       "One of the 4 fixed homebrew kinds. Needs 2 fields spanning 2+ types (max 1 of one type counted).",
    "monster":    "One of the 4 fixed homebrew kinds. Needs 2 fields spanning 2+ types (max 1 of one type counted).",
    "spell":      "One of the 4 fixed homebrew kinds. Needs 2 fields spanning 2+ types (max 1 of one type counted).",
    "lower":      "String method: returns the text in lowercase.",
    "upper":      "String method: returns the text in uppercase.",
    "trim":       "String method: removes leading/trailing whitespace.",
    "clean":      "String method: collapses repeated whitespace into single spaces.",
    "title":      "String method: capitalizes each word.",
    "starts":     "String method: starts(\"x\") → honor/lie, does the text start with x?",
    "ends":       "String method: ends(\"x\") → honor/lie, does the text end with x?",
    "contains":   "String method: contains(\"x\") → honor/lie, does the text contain x?",
    "empty":      "String method: empty() → honor/lie, is the text empty?",
    "words":      "String method: splits the text into a list of words.",
    "split":      "String method: split(\"x\") splits the text on x into a list.",
    "join":       "String method: join(list) joins a list of values using this text as the separator.",
    "find":       "String method: find(\"x\") returns the position of x, or -1 if not found.",
    "count":      "String method: count(\"x\") returns how many times x appears.",
}

# member_N field access note (shown when hovering 'member'):
HOVER_DOCS["member"] = (
    "List indexing: list.member_2 gets index 2, and list.member_someVar uses "
    "the value of 'someVar' as the index. Bracket form also works: list[someVar]."
)


class DndIDE:
    def __init__(self, root):
        self.root = root
        self.root.title("D&D Lang IDE — untitled.dnd")
        self.current_path = None
        self.output_queue = queue.Queue()
        self.input_result_queue = queue.Queue()
        self._check_after_id = None
        self.tooltip = None
        self._last_hover_word = None

        self._build_menu()
        self._build_layout()
        self._highlight()
        self._poll_output_queue()

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New", command=self.new_file, accelerator="Ctrl+N")
        file_menu.add_command(label="Open...", command=self.open_file, accelerator="Ctrl+O")
        file_menu.add_command(label="Save", command=self.save_file, accelerator="Ctrl+S")
        file_menu.add_command(label="Save As...", command=self.save_file_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        run_menu = tk.Menu(menubar, tearoff=0)
        run_menu.add_command(label="Run", command=self.run_code, accelerator="F5")
        menubar.add_cascade(label="Run", menu=run_menu)

        self.root.config(menu=menubar)
        self.root.bind("<Control-n>", lambda e: self.new_file())
        self.root.bind("<Control-o>", lambda e: self.open_file())
        self.root.bind("<Control-s>", lambda e: self.save_file())
        self.root.bind("<F5>", lambda e: self.run_code())

    def _build_layout(self):
        toolbar = tk.Frame(self.root)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        run_btn = tk.Button(toolbar, text="Run (F5)", command=self.run_code, bg="#4CAF50", fg="white")
        run_btn.pack(side=tk.LEFT, padx=4, pady=4)
        self.run_button = run_btn

        paned = tk.PanedWindow(self.root, orient=tk.VERTICAL, sashwidth=6)
        paned.pack(fill=tk.BOTH, expand=True)

        editor_frame = tk.Frame(paned)
        self.linenumbers = tk.Text(editor_frame, width=6, padx=6, pady=0, takefocus=0,
                                    border=0, background="#252526", foreground="#7a7a7a",
                                    font=("Consolas", 12), state="disabled", wrap="none")
        self.linenumbers.pack(side=tk.LEFT, fill=tk.Y)

        self.editor = tk.Text(editor_frame, wrap="none", undo=True, font=("Consolas", 12),
                               bg="#1e1e1e", fg="#d4d4d4", insertbackground="white",
                               yscrollcommand=self._on_editor_yview)
        self.editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.editor.bind("<KeyRelease>", self._on_key_release)
        self.editor.bind("<Return>", self._on_return)
        self.editor.bind("(", self._on_open_paren)
        self.editor.bind(")", self._on_close_paren)
        self.editor.bind('"', self._on_quote)
        self.editor.bind("[", self._on_open_bracket)
        self.editor.bind("]", self._on_close_bracket)
        self.editor.bind("{", self._on_open_brace)
        self.editor.bind("}", self._on_close_brace)
        self.editor.bind("<Motion>", self._on_hover)
        self.editor.bind("<Leave>", lambda e: self._hide_tooltip())
        self._configure_tags()
        paned.add(editor_frame, minsize=200)

        console_frame = tk.Frame(paned)
        tk.Label(console_frame, text="Console").pack(anchor="w")
        self.console = tk.Text(console_frame, height=10, bg="black", fg="#00ff00",
                                font=("Consolas", 11), state="disabled")
        self.console.pack(fill=tk.BOTH, expand=True)
        paned.add(console_frame, minsize=100)

    def _configure_tags(self):
        self.editor.tag_configure("decl", foreground="#569CD6")
        self.editor.tag_configure("control", foreground="#C586C0")
        self.editor.tag_configure("io", foreground="#4EC9B0")
        self.editor.tag_configure("bool", foreground="#D19A66")
        self.editor.tag_configure("builtin", foreground="#DCDCAA")
        self.editor.tag_configure("statname", foreground="#4FC1FF")
        self.editor.tag_configure("kind", foreground="#D7BA7D")
        self.editor.tag_configure("string", foreground="#CE9178")
        self.editor.tag_configure("number", foreground="#B5CEA8")
        self.editor.tag_configure("comment", foreground="#6A9955")
        self.editor.tag_raise("string", "number")

    ALL_TAGS = ("decl", "control", "io", "bool", "builtin", "statname",
                "kind", "string", "number", "comment")

    def _on_key_release(self, event=None):
        self._highlight()

    def _on_editor_yview(self, first, last):
        self.linenumbers.yview_moveto(float(first))

    def _on_return(self, event):
        """Auto-indent: keep the current line's indentation on the new line,
        and add one extra level if the line being left ends with ':'."""
        cursor = self.editor.index(tk.INSERT)
        line_start = cursor.split(".")[0] + ".0"
        line_up_to_cursor = self.editor.get(line_start, cursor)
        leading_ws = re.match(r"[ \t]*", line_up_to_cursor).group()
        extra = "    " if line_up_to_cursor.rstrip().endswith(":") else ""
        self.editor.insert(tk.INSERT, "\n" + leading_ws + extra)
        return "break"

    def _on_open_paren(self, event):
        self.editor.insert(tk.INSERT, "()")
        self.editor.mark_set(tk.INSERT, f"{tk.INSERT}-1c")
        return "break"

    def _on_close_paren(self, event):
        idx = self.editor.index(tk.INSERT)
        next_char = self.editor.get(idx, f"{idx}+1c")
        if next_char == ")":
            self.editor.mark_set(tk.INSERT, f"{idx}+1c")
            return "break"
        return None

    def _on_open_bracket(self, event):
        self.editor.insert(tk.INSERT, "[]")
        self.editor.mark_set(tk.INSERT, f"{tk.INSERT}-1c")
        return "break"

    def _on_close_bracket(self, event):
        idx = self.editor.index(tk.INSERT)
        next_char = self.editor.get(idx, f"{idx}+1c")
        if next_char == "]":
            self.editor.mark_set(tk.INSERT, f"{idx}+1c")
            return "break"
        return None

    def _on_open_brace(self, event):
        self.editor.insert(tk.INSERT, "{}")
        self.editor.mark_set(tk.INSERT, f"{tk.INSERT}-1c")
        return "break"

    def _on_close_brace(self, event):
        idx = self.editor.index(tk.INSERT)
        next_char = self.editor.get(idx, f"{idx}+1c")
        if next_char == "}":
            self.editor.mark_set(tk.INSERT, f"{idx}+1c")
            return "break"
        return None

    def _on_quote(self, event):
        idx = self.editor.index(tk.INSERT)
        next_char = self.editor.get(idx, f"{idx}+1c")
        if next_char == '"':
            self.editor.mark_set(tk.INSERT, f"{idx}+1c")
            return "break"
        self.editor.insert(tk.INSERT, '""')
        self.editor.mark_set(tk.INSERT, f"{tk.INSERT}-1c")
        return "break"

    def _highlight(self):
        text = self.editor.get("1.0", "end-1c")
        for tag in self.ALL_TAGS:
            self.editor.tag_remove(tag, "1.0", "end")

        # Find protected regions first. Nothing else is allowed to paint over
        # quoted Scrolls or comments.
        protected = []
        for pattern in (STRING_PATTERN, COMMENT_PATTERN):
            for m in re.finditer(pattern, text, re.MULTILINE):
                protected.append((m.start(), m.end()))

        def is_protected(match):
            start, end = match.start(), match.end()
            return any(start < p_end and end > p_start for p_start, p_end in protected)

        # Apply ordinary syntax colors only outside protected regions.
        for pattern, tag in [
            (NUMBER_PATTERN, "number"),
            (DECL_PATTERN, "decl"),
            (CONTROL_PATTERN, "control"),
            (IO_PATTERN, "io"),
            (BOOL_PATTERN, "bool"),
            (BUILTIN_PATTERN, "builtin"),
            (STAT_NAME_PATTERN, "statname"),
            (KIND_PATTERN, "kind"),
        ]:
            for m in re.finditer(pattern, text):
                if is_protected(m):
                    continue
                start = f"1.0+{m.start()}c"
                end = f"1.0+{m.end()}c"
                self.editor.tag_add(tag, start, end)

        # Scrolls and comments are painted last and explicitly protected.
        for m in re.finditer(STRING_PATTERN, text):
            start = f"1.0+{m.start()}c"
            end = f"1.0+{m.end()}c"
            self.editor.tag_add("string", start, end)

        for m in re.finditer(COMMENT_PATTERN, text, re.MULTILINE):
            start = f"1.0+{m.start()}c"
            end = f"1.0+{m.end()}c"
            self.editor.tag_add("comment", start, end)

        self._update_line_numbers(text)

    def _update_line_numbers(self, text=None):
        if text is None:
            text = self.editor.get("1.0", "end-1c")
        addresses = compute_line_addresses(text)
        self.linenumbers.config(state="normal")
        self.linenumbers.delete("1.0", "end")
        self.linenumbers.insert("1.0", "\n".join(addresses))
        self.linenumbers.config(state="disabled")
        self.linenumbers.yview_moveto(self.editor.yview()[0])

    def _on_hover(self, event):
        idx = self.editor.index(f"@{event.x},{event.y}")
        word = self._word_at_index(idx)

        if word == self._last_hover_word:
            return
        self._last_hover_word = word

        if word in HOVER_DOCS:
            self._show_tooltip(event.x_root, event.y_root, word, HOVER_DOCS[word])
        elif word.startswith("member_") and len(word) > len("member_"):
            self._show_tooltip(event.x_root, event.y_root, word, HOVER_DOCS["member"])
        else:
            self._hide_tooltip()

    def _word_at_index(self, idx):
        line_start = idx.split(".")[0] + ".0"
        line_text = self.editor.get(line_start, f"{line_start} lineend")
        col = int(idx.split(".")[1])
        if col > len(line_text):
            return ""
        start = col
        while start > 0 and (line_text[start - 1].isalnum() or line_text[start - 1] == "_"):
            start -= 1
        end = col
        while end < len(line_text) and (line_text[end].isalnum() or line_text[end] == "_"):
            end += 1
        return line_text[start:end]

    def _show_tooltip(self, x_root, y_root, word, text):
        self._hide_tooltip()
        self.tooltip = tk.Toplevel(self.root)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x_root + 14}+{y_root + 16}")
        frame = tk.Frame(self.tooltip, background="#ffffe0", relief="solid", borderwidth=1)
        frame.pack()
        tk.Label(frame, text=word, background="#ffffe0", font=("Consolas", 10, "bold"),
                 anchor="w", justify="left").pack(fill="x", padx=6, pady=(4, 0))
        tk.Label(frame, text=text, background="#ffffe0", font=("Consolas", 9),
                 wraplength=380, justify="left", anchor="w").pack(fill="x", padx=6, pady=(0, 4))

    def _hide_tooltip(self):
        if self.tooltip is not None:
            self.tooltip.destroy()
            self.tooltip = None
        self._last_hover_word = None

    def new_file(self):
        self.editor.delete("1.0", "end")
        self.current_path = None
        self.root.title("D&D Lang IDE — untitled.dnd")
        self._update_line_numbers("")

    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[("D&D files", "*.dnd"), ("All files", "*.*")])
        if not path:
            return
        with open(path, "r") as f:
            content = f.read()
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", content)
        self.current_path = path
        self.root.title(f"D&D Lang IDE — {path}")
        self._highlight()

    def save_file(self):
        if self.current_path is None:
            self.save_file_as()
            return
        with open(self.current_path, "w") as f:
            f.write(self.editor.get("1.0", "end-1c"))

    def save_file_as(self):
        path = filedialog.asksaveasfilename(defaultextension=".dnd",
                                             filetypes=[("D&D files", "*.dnd"), ("All files", "*.*")])
        if not path:
            return
        self.current_path = path
        self.root.title(f"D&D Lang IDE — {path}")
        self.save_file()

    def run_code(self):
        source = self.editor.get("1.0", "end-1c")
        self._clear_console()
        self.run_button.config(state="disabled", text="Running...")
        thread = threading.Thread(target=self._run_in_thread, args=(source,), daemon=True)
        thread.start()

    def _run_in_thread(self, source):
        try:
            tokens = tokenize(source)
            ast = parse(tokens)
            interp = Interpreter(output_func=self._queue_output, input_func=self._ask_input)
            interp.run(ast)
        except (SyntaxError, DMError) as e:
            self._queue_output(f"DM: {e}")
        except Exception as e:
            self._queue_output(f"DM: something went very wrong ({e})")
        finally:
            self.output_queue.put(("__DONE__", None))

    def _queue_output(self, text):
        self.output_queue.put(("line", text))

    def _ask_input(self, prompt):
        """Called from the worker thread. Shows a popup on the main thread and
        blocks the worker thread until the player answers."""
        def show_dialog():
            val = simpledialog.askstring("Player Input", prompt, parent=self.root)
            self.input_result_queue.put(val if val is not None else "")
        self.root.after(0, show_dialog)
        return self.input_result_queue.get()

    def _poll_output_queue(self):
        try:
            while True:
                kind, payload = self.output_queue.get_nowait()
                if kind == "line":
                    self._append_console(payload + "\n")
                elif kind == "__DONE__":
                    self.run_button.config(state="normal", text="Run (F5)")
        except queue.Empty:
            pass
        self.root.after(50, self._poll_output_queue)

    def _append_console(self, text):
        self.console.config(state="normal")
        self.console.insert("end", text)
        self.console.see("end")
        self.console.config(state="disabled")

    def _clear_console(self):
        self.console.config(state="normal")
        self.console.delete("1.0", "end")
        self.console.config(state="disabled")


def main():
    root = tk.Tk()
    root.geometry("900x700")
    app = DndIDE(root)
    root.mainloop()


if __name__ == "__main__":
    main()
