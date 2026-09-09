"""Enable D&D Lang v5 extensions for normal Python entry points.

Python automatically imports sitecustomize when this repository directory is
on sys.path. This lets the existing IDE (which imports lexer/interpreter
 directly) receive the same v5 behavior as run.py without duplicating the
interpreter implementation.
"""

import interpreter as _interpreter
import lexer as _lexer

from v5_runtime import V5Interpreter, expand_v5_syntax


_original_tokenize = _lexer.tokenize


def _tokenize_v5(source):
    return _original_tokenize(expand_v5_syntax(source))


_lexer.tokenize = _tokenize_v5
_interpreter.Interpreter = V5Interpreter
