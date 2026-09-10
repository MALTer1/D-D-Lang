import re

KEYWORDS = {
    "ability", "pouch", "vault", "summon", "homebrew", "quest", "embark", "reward", "init",
    "narrate", "player", "attempt", "or_attempt", "fail", "finally", "adventure", "pass", "raise",
    "quit", "continue", "while", "for", "in", "party", "submit", "consider", "issue",
    "honor", "lie", "extra", "none",
}

TOKEN_SPEC = [
    ("NUMBER", r"\d+(\.\d+)?"),
    ("STRING", r'"(?:\\.|[^"\\])*"'),
    ("DICE", r"d\d+"),
    ("ID", r"[A-Za-z_][A-Za-z0-9_]*"),
    ("OP", r"==|!=|>=|<=|\+=|->|[=+\-*/%(),.:\[\]{}><\\]"),
    ("SKIP", r"[ \t]+"),
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
    out = []
    in_string = False
    escaped = False
    i = 0
    while i < len(line):
        ch = line[i]
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == '-' and i + 1 < len(line) and line[i + 1] == '-':
            end = line.find('--', i + 2)
            if end == -1:
                break
            i = end + 2
            continue
        out.append(ch)
        i += 1
    return ''.join(out)

def _decode_string(raw):
    body = raw[1:-1]
    return bytes(body, 'utf-8').decode('unicode_escape')

def tokenize(source):
    tokens = []
    indent_stack = [0]
    lines = source.split("\n")
    major = -1
    minor = None
    for line_num, raw_line in enumerate(lines, start=1):
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
            m = MASTER_PATTERN.match(stripped, pos)
            if not m:
                raise SyntaxError(f"The DM doesn't understand '{stripped[pos]}' at line {line_num} (address {address}).")
            kind = m.lastgroup
            value = m.group()
            pos = m.end()
            if kind == "SKIP":
                continue
            if kind == "NUMBER":
                value = float(value) if "." in value else int(value)
                tokens.append(Token("NUMBER", value, line_num, address))
            elif kind == "STRING":
                tokens.append(Token("STRING", _decode_string(value), line_num, address))
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
            else:
                tokens.append(Token(value, value, line_num, address))
        tokens.append(Token("NEWLINE", None, line_num, address))
    while len(indent_stack) > 1:
        indent_stack.pop()
        tokens.append(Token("DEDENT", 0, len(lines), ""))
    tokens.append(Token("EOF", None, len(lines), ""))
    return tokens
