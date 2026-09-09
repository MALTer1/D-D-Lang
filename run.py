import sys
from lexer import tokenize
from parser import parse
from interpreter import DMError
from v5_runtime import V5Interpreter, expand_v5_syntax


def main():
    if len(sys.argv) < 2:
        print("Usage: python run.py yourfile.dnd")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "r") as f:
        source = f.read()

    try:
        source = expand_v5_syntax(source)
        tokens = tokenize(source)
        ast = parse(tokens)
        V5Interpreter().run(ast)
    except (SyntaxError, DMError) as e:
        print(f"DM: {e}")


if __name__ == "__main__":
    main()
