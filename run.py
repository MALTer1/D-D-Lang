import sys
from lexer import tokenize
from parser import parse
from interpreter import Interpreter, DMError

def main():
    if len(sys.argv) < 2:
        print("Usage: python run.py yourfile.dnd")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "r") as f:
        source = f.read()

    try:
        tokens = tokenize(source)
        ast = parse(tokens)
        Interpreter().run(ast)
    except (SyntaxError, DMError) as e:
        print(f"DM: {e}")

if __name__ == "__main__":
    main()
