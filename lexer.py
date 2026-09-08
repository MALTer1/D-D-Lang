"""
Lexer (tokenizer) for the D&D-themed language.
Turns raw source text into a flat list of tokens, including INDENT/DEDENT/NEWLINE
tokens so the parser can understand Python-style block structure.
"""

import re

KEYWORDS = {
    "ability", "summon", "homebrew", "quest", "embark", "reward", "init",
    "narrate", "player", "attempt", "or_attempt", "fail", "adventure",
    "quit", "continue", "while", "for", "in", "party",
    "submit", "consider", "issue",
    "honor", "lie", "extra",
}

TOKEN_SPEC = [
    ("NUMBER",   r"\d+(\.\d+)?"),
    ("STRING",   r'"[^"]*"'),
    ("DICE",     r"d\d+"),
    ("ID",       r"[A-Za-z_][A-Za-z0-9_]*"),
    ("OP",       r"==|!=|>=|<=|\+=|[=+\-*/%(),.:\[\]{}><\\]"),
    ("SKIP",     r"[ \t]+"),
]

MASTER_PATTERN = re.compile("|".join(f"(?P<{name}>{pattern})" for name, pattern in TOKEN_SPEC))


class Token:
    def __init__(self, type_, value, line):
        self.type = type_
        self.value = value
        self.line = line

    def __repr__(self):
        return f"Token({self.type!r}, {self.value!r})"


def strip_comments(line):
    # Comments are wrapped in -- ... --
    while "--" in line:
        start = line.find("--")
        end = line.find("--", start + 2)
        if end == -1:
            # comment runs to end of line
            line = line[:start]
            break
        else:
            line = line[:start] + line[end + 2:]
    return line


def tokenize(source):
    tokens = []
    indent_stack = [0]
    lines = source.split("\n")

    for line_num, raw_line in enumerate(lines, start=1):
        line = strip_comments(raw_line)
        if line.strip() == "":
            continue  # blank/comment-only lines don't affect indentation

        # measure indentation (count leading spaces; treat tabs as 4 spaces)
        stripped = line.lstrip(" \t")
        indent = len(line) - len(stripped)

        if indent > indent_stack[-1]:
            indent_stack.append(indent)
            tokens.append(Token("INDENT", indent, line_num))
        while indent < indent_stack[-1]:
            indent_stack.pop()
            tokens.append(Token("DEDENT", indent, line_num))

        # tokenize the rest of the line
        pos = 0
        while pos < len(stripped):
            match = MASTER_PATTERN.match(stripped, pos)
            if not match:
                raise SyntaxError(f"The DM doesn't understand '{stripped[pos]}' at line {line_num}.")
            kind = match.lastgroup
            value = match.group()
            pos = match.end()
            if kind == "SKIP":
                continue
            elif kind == "NUMBER":
                value = float(value) if "." in value else int(value)
                tokens.append(Token("NUMBER", value, line_num))
            elif kind == "STRING":
                tokens.append(Token("STRING", value[1:-1], line_num))
            elif kind == "DICE":
                tokens.append(Token("DICE", int(value[1:]), line_num))
            elif kind == "ID":
                if value == "_":
                    tokens.append(Token("_", "_", line_num))
                elif value in KEYWORDS:
                    tokens.append(Token(value, value, line_num))
                else:
                    tokens.append(Token("ID", value, line_num))
            elif kind == "OP":
                tokens.append(Token(value, value, line_num))

        tokens.append(Token("NEWLINE", None, line_num))

    while len(indent_stack) > 1:
        indent_stack.pop()
        tokens.append(Token("DEDENT", 0, len(lines)))

    tokens.append(Token("EOF", None, len(lines)))
    return tokens
