# Your D&D Language — v1 (core)

## How to run
1. Open this folder in VS Code (`File > Open Folder`).
2. Open the built-in terminal (`` Ctrl+` `` or `` Cmd+` ``).
3. Run: `python run.py examples/calculator.dnd`
4. Write your own `.dnd` files anywhere and run them the same way.

## What's implemented (v1 — core)
- `ability`, `summon` (basic), `narrate`, `player(...)`
- `attempt` / `or_attempt` / `fail`
- `adventure(n)`, `quit`
- `quest` / `embark` / `reword` / `init` (with quest isolation!)
- `honor` / `lie`, numbers, Scrolls (strings), lists
- math (`+ - * /`), comparisons (`== > < >= <=`)
- `roll(dX)` dice rolls
- Python-style indentation blocks
- DM-style error messages

## Not yet implemented (v2 — next)
- `homebrew` (character/item/monster/spell) + shape-based requirements
- `STATS` block and the six ability mechanics (`solve`, `force`, `sway`, `endure`, `perceive`)
- `initiative` code-reordering system

## Files
- `lexer.py` — turns source text into tokens
- `parser.py` — turns tokens into an AST
- `interpreter.py` — walks the AST and actually runs it
- `run.py` — entry point: `python run.py yourfile.dnd`
- `examples/` — sample programs

## Building a real .exe (Windows only)
This has to be built on Windows itself (it can't be cross-built from other systems). One-time setup:

1. Make sure Python is installed on your Windows machine.
2. Put this whole folder somewhere on your computer (Desktop, Documents, wherever).
3. Double-click **build_exe.bat**. It installs a tool called PyInstaller (only needed once) and builds the exe. This takes a minute or two.
4. When it's done, you'll find **DndLangIDE.exe** inside the new `dist` folder.

## Making a desktop shortcut with the d20 icon
1. Go into the `dist` folder and find `DndLangIDE.exe`.
2. Right-click it → **Send to** → **Desktop (create shortcut)**.
3. That's it — the icon is already baked into the exe itself (a purple d20 die), so the shortcut will show it automatically. Double-click the shortcut anytime to launch the IDE — no terminal, no typing commands.

If you ever change the code (`ide.py`, `interpreter.py`, etc.), just re-run `build_exe.bat` to rebuild the `.exe` with your changes.

## v2 — homebrew / STATS / auto-fill / hover
- `homebrew <kind> Name:` — kind is fixed (character/item/monster/spell), field names are free, values must be number/Scroll/honor-lie/list.
- Shape requirement (auto-filled silently if not met, never an error): each kind needs a minimum total field count spanning a minimum number of distinct types, with a cap on how many fields of one type count toward that.
- `summon x = Name()` creates an instance.
- `STATS:` block — 6 defaults (STR/DEX/CON/INT/WIS/CHA, default 10) plus `extra NAME = value` for custom stats. Every stat has `.number` and `.mod` (auto = floor((number-10)/2), overridable: `x.STATS.STR.mod = 5`).
- Stat mechanics, called on an instance:
  - `x.force.mod(n)` / `.number(n)` — STR, flat addition
  - `x.sway.mod(n)` / `.number(n)` — CHA, flat multiplication
  - `x.endure.mod(n, times)` / `.number(n, times)` — CON, repeated % reduction. Plain form: `endure(n, times, rate)`
  - `x.perceive.mod(list)` / `.number(list)` — WIS, average + stat. Plain form: `perceive(list)`
  - `x.solve.mod COMPARATOR(difficulty)` — INT, dice check. Comparator symbols: `/` greater, `_` equal, `\` less, combinable (`/_` = default, greater-or-equal; `\_` = less-or-equal). Example: `x.solve.mod \_(10)`
- `initiative` (DEX, code-line reordering) is still NOT implemented — it's the most complex mechanic and deserves its own dedicated pass.
- The IDE now shows a hover tooltip over any keyword/built-in with a description of what it does and an example.

## v3 — while / for-party / submit-consider / strings / renamed reward
- `reword` was renamed to **`reward`**.
- `continue` — skips to the next loop iteration (works in `adventure`, `while`, and `for`).
- `while condition:` — a loop that re-checks its condition every iteration.
- `for x in party(...):` — `party(n)` counts 0..n-1, `party(a, b)` ranges a..b-1, `party(list)` iterates a list, `party(someSTATS)` iterates stat names.
- `.member_N` — list indexing, e.g. `Scores.member_2`. Also supports a variable name instead of a literal: `Scores.member_player_num` looks up `player_num` and uses its value as the index.
- `+=` compound assignment, e.g. `turn_score += roll`.
- `!=` and `%` (modulo) added to comparisons/math.
- `submit:` / `consider issue X:` / `consider:` — try/except. `consider issue ValueError:` catches a specific error kind; a bare `consider:` catches anything. `num("text")` raises a catchable ValueError if the text isn't a real number.
- String methods: `.lower() .upper() .trim() .clean() .title() .starts(x) .ends(x) .contains(x) .empty() .words() .split(x) .join(list) .find(x) .count(x)` — chainable, e.g. `msg.trim().lower()`.
- Built-ins: `max(...)`, `min(...)`, `len(...)`, `num(scroll)`, `str(value)`.
- The IDE now shows a **line-number gutter** on the left using the language's own major.minor addressing — top-level lines are 0, 1, 2..., and anything nested gets major.minor (e.g. 2.0, 2.1), matching how `initiative` addresses lines.
- Curly braces `{ }` now auto-pair too, alongside `()`, `[]`, and `""`.

See `examples/pig_dice.dnd` for a full game using all of this together.

## v4 — DEX/CHA role swap: force (math) and sway (reordering)
- **`force`** is now general-purpose math (STR only), with an operator symbol as the first argument:
  `instance.force.mod(SYMBOL, x)` / `.number(SYMBOL, x)` where SYMBOL is `+ - * / %`. Example: `sword.force.mod(*, 10)`.
- **`sway`** replaces the old (never-implemented) `initiative` — it's CHA-driven code reordering, called directly on an instance (no `.mod`/`.number`):
  `instance.sway(address, shift)`. `address` is the target line's position in the **current block only** (a v1 scoping choice — see note below). `shift` can be:
  - an explicit signed number: `sword.sway(3, +2)`
  - the bare keyword `mod`/`number` → uses that instance's own CHA: `sword.sway(3, mod)`
  - `STATNAME.mod`/`STATNAME.number` → uses a different named stat instead of CHA: `sword.sway(3, LUCK.number)`
  - A bare `sway(...)`/`force(...)` with no instance uses a **global `STATS:` block** if one is declared at the top of the program (outside everything else); otherwise every stat defaults to 10/mod 0.
  - Only lines that **haven't executed yet** can be moved (the past can't un-happen) — moving an already-run line raises a DM error.
- **v1 scoping note:** `sway` currently only reorders statements at the top level of the block it's called from (the "major" number) — it doesn't yet reach into nested sub-blocks (the "minor" part of an address). This is a deliberate first pass to get a correct, working reordering system rather than a fragile complete one; extending it to nested addressing is a natural next step.
- `sway` (as CHA flat-multiplication) is retired — that concept no longer exists.
