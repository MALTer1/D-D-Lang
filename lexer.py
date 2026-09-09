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
    def __init__(self, type_, value, line, address=None):
        self.type = type_
        self.value = value
        self.line = line
        self.address = address

    def __repr__(self):
        return f"Token({self.type!r}, {self.value!r})"


def strip_comments(line):
    # Comments are wrapped in -- ... --
    while "--" in line:
        start = line.find("--")
        end = line.find("--", start + 2)
        if end == -1:
            line = line[:start]
            break
        line = line[:start] + line[end + 2:]
    return line


def tokenize(source):
    tokens = []
    indent_stack = [0]
    lines = source.split("\n")
    major = -1
    minor = None

    for line_num, raw_line in enumerate(lines, start=1):
        adventure_match = re.match(
            r"^(?P<indent>[ \t]*)adventure\s+(?P<var>[A-Za-z_][A-Za-z0-9_]*)"
            r"\s+in\s+(?P<total>.+):\s*$",
            raw_line,
        )
        if adventure_match:
            raw_line = (
                f"{adventure_match.group('indent')}for {adventure_match.group('var')} "
                f"in party({adventure_match.group('total')}):"
            )

        line = strip_comments(raw_line)
        if line.strip() == "":
            continue

        stripped = line.lstrip(" \t")
        indent = len(line) - len(stripped)

        if indent == 0:
            major += 1
            minor = None
            address = str(major)
        else:
            minor = 0 if minor is None else minor + 1
            address = f"{major}.{minor}" if major >= 0 else ""

        if indent > indent_stack[-1]:
            indent_stack.append(indent)
            tokens.append(Token("INDENT", indent, line_num, address))
        while indent < indent_stack[-1]:
            indent_stack.pop()
            tokens.append(Token("DEDENT", indent, line_num, address))

        pos = 0
        while pos < len(stripped):
            match = MASTER_PATTERN.match(stripped, pos)
            if not match:
                raise SyntaxError(f"The DM doesn't understand '{stripped[pos]}' at line {address}.")
            kind = match.lastgroup
            value = match.group()
            pos = match.end()
            if kind == "SKIP":
                continue
            if kind == "NUMBER":
                value = float(value) if "." in value else int(value)
                tokens.append(Token("NUMBER", value, line_num, address))
            elif kind == "STRING":
                tokens.append(Token("STRING", value[1:-1], line_num, address))
            elif kind == "DICE":
                tokens.append(Token("DICE", int(value[1:]), line_num, address))
            elif kind == "ID":
                if value == "_":
                    tokens.append(Token("_", "_", line_num, address))
                elif value == "encounter":
                    tokens.append(Token("quest", value, line_num, address))
                elif value == "fight":
                    tokens.append(Token("embark", value, line_num, address))
                elif value in KEYWORDS:
                    tokens.append(Token(value, value, line_num, address))
                else:
                    tokens.append(Token("ID", value, line_num, address))
            elif kind == "OP":
                tokens.append(Token(value, value, line_num, address))

        tokens.append(Token("NEWLINE", None, line_num, address))

    while len(indent_stack) > 1:
        indent_stack.pop()
        tokens.append(Token("DEDENT", 0, len(lines), ""))

    tokens.append(Token("EOF", None, len(lines), ""))
    return tokens
