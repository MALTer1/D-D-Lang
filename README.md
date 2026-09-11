# D&D Lang

A small programming language inspired by Dungeons & Dragons, designed to feel like a programming language while keeping its own vocabulary and style.

Current release: **v6**

## How to run

1. Open this folder in VS Code (`File > Open Folder`).
2. Open the built-in terminal (`Ctrl+`` or `Cmd+``).
3. Run:

```text
python run.py Projects/Calc.dnd
```

4. Write your own `.dnd` files and run them the same way.

You can also launch the Tkinter IDE with:

```text
python ide.py
```

## Language philosophy

D&D Lang borrows useful programming ideas from languages such as Python, but it does not try to become Python with renamed keywords.

Examples:

- `party()` is D&D Lang's range/iteration primitive.
- `Scroll` means text/string data.
- `pouch` means key-value data.
- `Vault` means external file storage.
- `submit` / `consider` provide the language's try/catch-style error handling.
- `quest` / `embark` provide the language's function system.
- `reward` returns a value from a quest.

The goal is to keep familiar programming concepts while making them feel native to D&D Lang.

---

# Current Language Reference

## Variables and values

### `ability`

Declares a normal value.

```dnd
ability name = "Hero"
ability hp = 20
ability alive = honor
```

D&D Lang values include:

- numbers
- Scrolls
- `honor` / `lie`
- lists
- pouches
- `none`
- quest results
- homebrew instances

### `honor` and `lie`

The built-in boolean values.

```dnd
ability alive = honor
ability dead = lie
```

### `none`

Represents the absence of a value.

```dnd
ability result = none
```

`none` has the language type name `NoneType`.

```dnd
narrate(type(none))
```

---

# Scrolls

Scrolls are strings/text.

```dnd
ability message = "Welcome to the dungeon!"
```

Supported Scroll methods:

```text
lower()
upper()
trim()
clean()
title()
starts(x)
ends(x)
contains(x)
empty()
words()
split(x)
join(list)
find(x)
count(x)
replace(x, y)
```

Example:

```dnd
ability message = "  The Dragon Guards The Gate  "

narrate(message.trim().lower())
narrate(message.contains("Dragon"))
narrate(message.find("Dragon"))
narrate(message.count("The"))
narrate(message.replace("Dragon", "Goblin"))
```

Scroll methods are chainable:

```dnd
narrate("  HELLO WORLD  ".trim().lower())
```

---

# Lists

Lists use square brackets.

```dnd
ability cards = ["A", "K", "Q"]
```

List items can be accessed with either bracket indexing or the language's `member_N` form.

```dnd
narrate(cards[0])
narrate(cards.member_1)
```

A variable can also be used as an index:

```dnd
ability index = 2
narrate(cards[index])
narrate(cards.member_index)
```

Lists automatically grow when assigning beyond their current end. Missing positions are filled with `none`.

```dnd
ability scores = []
scores[3] = 20
```

Built-in list operations:

```text
append(list, value)
push(list, value)
pop(list)
pop(list, index)
contains(list, value)
index(list, value)
```

---

# Pouches

A `pouch` is D&D Lang's key-value collection.

```dnd
pouch hero = {
    "name": "Aria",
    "hp": 20,
    "class": "Wizard"
}
```

Access values with brackets:

```dnd
narrate(hero["name"])
narrate(hero["hp"])
```

Pouch values can be changed:

```dnd
hero["hp"] = 15
```

Pouches can contain other pouches:

```dnd
pouch hero = {
    "name": "Aria",
    "stats": {
        "hp": 20,
        "mana": 10
    }
}
```

Pouches are useful for structured data such as characters, cards, enemies, configuration, and saved game state.

---

# Type utilities and conversion

The main type names are:

```text
number
Scroll
honor/lie
list
pouch
NoneType
```

Use `type()` to inspect a value.

```dnd
narrate(type(10))
narrate(type("hello"))
narrate(type(none))
```

Conversion built-ins:

```text
num(value)
str(value)
bool(value)
list(value)
pouch(value)
```

`num()` converts text to a number and raises a catchable `ValueError` when conversion fails.

```dnd
ability score = num("42")
narrate(score)
```

---

# Control flow

## `attempt`, `or_attempt`, `fail`

D&D Lang's normal conditional form.

```dnd
attempt (hp > 0):
    narrate("Still standing!")
or_attempt (hp == 0):
    narrate("At zero.")
fail:
    narrate("Defeated.")
```

## `while`

Repeats while its condition remains true.

```dnd
ability hp = 5

while (hp > 0):
    narrate(hp)
    hp -= 1
```

## `adventure`

Repeats a block a fixed number of times:

```dnd
adventure (3):
    narrate("A new round begins.")
```

It can also iterate through a collection:

```dnd
adventure card in deck:
    narrate(card)
```

## `for ... in party(...)`

`party()` is D&D Lang's range/iteration primitive.

```dnd
for i in party(5):
    narrate(i)
```

This produces:

```text
0
1
2
3
4
```

Other forms include:

```dnd
party(2, 5)
party(cards)
party(STATS)
```

## `continue`

Skips to the next loop iteration.

```dnd
adventure (10):
    continue
```

## `quit`

Stops the nearest loop.

```dnd
while (honor):
    quit
```

## `pass`

Does nothing.

Useful for placeholders or intentionally empty branches:

```dnd
attempt (ready):
    pass
```

---

# Quests

`quest` defines a function-like block.

```dnd
quest greet(name):
    narrate(name)
```

Invoke it with `embark`:

```dnd
embark greet("Hero")
```

Quest bodies are isolated by default.

Parameters are available automatically, and `init` can explicitly pull values from the caller's scope.

```dnd
quest show_score():
    init score
    narrate(score)
```

## `reward`

Returns a value from a quest.

```dnd
quest add(a, b):
    reward a + b

ability result = embark add(4, 6)
narrate(result)
```

---

# Error handling

D&D Lang keeps its `submit` / `consider` system instead of copying Python's `try` / `except` syntax.

## `submit`

Runs code that may fail.

```dnd
submit:
    ability number = num("not a number")
```

## `consider`

Catches an error.

```dnd
submit:
    ability number = num("not a number")
consider issue ValueError:
    narrate("That wasn't a number.")
```

A bare `consider:` catches an ordinary error from the submitted section.

## `raise`

Deliberately raises a D&D Lang runtime error.

```dnd
raise "The quest cannot continue."
```

This can be caught by `consider`.

## `finally`

Runs after the protected section finishes, whether it succeeds or an error is handled.

```dnd
submit:
    narrate("Doing work...")
consider:
    narrate("Something went wrong.")
finally:
    narrate("The quest is finished.")
```

This is especially useful for cleanup.

---

# Sequences and functional programming

## Sequence helpers

```text
len()
sum()
max()
min()
sorted()
reversed()
reverse()
any()
all()
zip()
enumerate()
```

Example:

```dnd
ability rolls = [4, 8, 3, 10]

narrate(sum(rolls))
narrate(max(rolls))
narrate(sorted(rolls))
```

## Functional helpers

```text
map()
filter()
reduce()
```

`map()` and `filter()` use named quests as their operations.

Example:

```dnd
quest double(x):
    reward x * 2

ability numbers = [1, 2, 3]
ability doubled = map(numbers, double)
narrate(doubled)
```

---

# Built-in utilities

General-purpose helpers include:

```text
abs()
round()
len()
max()
min()
sum()
type()
num()
str()
bool()
list()
pouch()
```

Runtime/debugging helpers include:

```text
forget()
memory()
```

`memory()` provides a small interpreter-side memory estimate intended for debugging rather than manual memory allocation.

---

# Vaults and file handling

A `Vault` represents an external file.

Example:

```dnd
vault save = "save.txt"
```

Supported file operations include:

```text
read()
write()
append()
close()
seal()
exists()
remove()
```

Vaults are intended for persistent data outside the program, while pouches are intended for structured in-memory data.

---

# Homebrew

Homebrew definitions create custom D&D-flavored types.

Supported fixed kinds:

```text
character
item
monster
spell
```

Example:

```dnd
homebrew character Hero:
    hp = 20
    name = "Aria"
    inventory = ["staff", "potion"]
```

Homebrew definitions can also contain a `STATS:` block.

Instances are created with `summon`:

```dnd
summon hero = Hero()
```

---

# STATS

Every homebrew instance has the six standard stats:

```text
STR
DEX
CON
INT
WIS
CHA
```

Each stat has:

```text
.number
.mod
```

Stats default to 10 unless changed.

Custom stats can be added with `extra`.

```dnd
STATS:
    STR = 12
    extra LUCK = 15
```

---

# Ability mechanics

D&D Lang's six standard stats drive language-specific mechanics.

## `force`

STR-based mathematics.

```dnd
sword.force.mod(+, 10)
sword.force.number(*, 2)
```

## `sway`

CHA-based code reordering.

```dnd
sword.sway(3, +2)
sword.sway(3, mod)
sword.sway(3, LUCK.number)
```

`Sway` currently operates within the current block.

Only statements that have not already executed can be moved.

## `endure`

CON-based repeated reduction.

```dnd
hero.endure.mod(100, 3)
hero.endure.number(100, 3)
```

## `perceive`

WIS-based list perception.

```dnd
hero.perceive.mod(scores)
hero.perceive.number(scores)
```

## `solve`

INT-based dice checks.

```dnd
hero.solve.mod /_(10)
```

The comparator system supports greater-than, equal, less-than, and the combined greater-or-equal / less-or-equal forms.

---

# Encounters

`encounter` is the named encounter form of a quest.

```dnd
encounter Goblins():
    narrate("Goblins appear!")
```

`fight` invokes an encounter:

```dnd
fight Goblins()
```

Encounter naming also provides an addressable scope for nested work.

---

# Lists, cards, and Blackjack

D&D Lang is being developed with real projects in mind.

One current project is Blackjack.

For example:

```dnd
ability cards = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
ability suits = ["S", "H", "D", "C"]
ability deck = []

adventure suit in suits:
    adventure card in cards:
        append(deck, card + suit)

narrate(deck)
```

The Blackjack work also serves as a regression test for list iteration and indexing.

---

# IDE

The Tkinter IDE includes:

- syntax highlighting
- Scroll/string highlighting
- number highlighting
- comment highlighting
- keyword categories
- line/address gutter
- hover documentation
- automatic indentation
- automatic pairing for `()`, `[]`, `{}`, and `""`
- Run button / F5
- Open / Save / Save As
- player-input dialogs
- integrated console

## Syntax highlighting rules

The editor scans source text while tracking whether it is inside a Scroll or comment.

A quoted Scroll:

```dnd
"Level 10"
```

keeps all of its contents as Scroll text, so the `10` is not highlighted as a number.

Comments support both:

```dnd
-- this is a comment --
```

and:

```dnd
-- this is a comment that ends at the line
```

The editor recognizes `--` outside a Scroll as the start of a comment and ends the comment at the next `--` or at the end of the line.

---

# Source addresses and diagnostics

D&D Lang uses major/minor source addresses.

Top-level lines use:

```text
0
1
2
3
```

Nested lines use:

```text
2.0
2.1
2.2
```

These addresses are also used by the IDE gutter and the current `sway` implementation.

Runtime errors include the relevant source address when available.

---

# Version history

## v1 — Core

Added the original language core:

- `ability`
- basic `summon`
- `narrate`
- `player(...)`
- `attempt` / `or_attempt` / `fail`
- `adventure(n)`
- `quit`
- `quest` / `embark`
- `reward` evolved from the original `reword`
- `init`
- `honor` / `lie`
- numbers
- Scrolls
- lists
- basic mathematics
- comparisons
- dice rolls
- Python-style indentation blocks
- DM-style error messages

**Status: complete.**

## v2 — Homebrew / STATS

Added:

- homebrew definitions
- fixed homebrew kinds
- shape requirements
- automatic filler fields
- `summon` instances
- `STATS`
- six standard stats
- custom `extra` stats
- `.number` and `.mod`
- `force`
- `endure`
- `perceive`
- `solve`
- the early DEX/initiative concept that later became `sway`
- IDE hover documentation

**Status: complete.**

## v3 — Control flow / strings

Added:

- `while`
- `for ... in party(...)`
- `party()` list/range/stat iteration
- `continue`
- `submit`
- `consider`
- specific error handling
- list member access
- `+=`
- `!=`
- `%`
- expanded Scroll utilities
- line/address gutter
- bracket auto-pairing

**Status: complete.**

## v4 — Force / Sway

Redesigned the DEX/CHA mechanics:

- `force` became general STR-based mathematics
- `sway` replaced the old unimplemented `initiative` idea
- source-address-based code reordering was introduced
- moving already-executed statements was disallowed

**Status: core complete. One major enhancement remains: fully generalized nested `sway` addressing.**

## v5 — Lists / iteration / encounters

Added:

- automatic list growth
- `none` list fillers
- `append`
- `push`
- `pop`
- `map`
- `filter`
- `contains`
- `index`
- `adventure item in collection`
- `encounter`
- `fight`
- encounter addressing
- list indexing with `[]`

**Status: essentially complete.**

## v6 — Language expansion

Added:

- `pouch`
- key-value collections
- `none` / `NoneType`
- `pass`
- `raise`
- `finally`
- Vault file handling
- type inspection
- type conversion
- sequence utilities
- functional utilities
- extra Scroll utilities
- runtime/miscellaneous helpers
- protected-region IDE syntax scanning

**Status: complete for the current v6 feature set.**

---

# What is actually unfinished?

Most of the old roadmap is already complete. Several older ideas were replaced with better designs rather than simply left unfinished.

## Remaining older roadmap work

### 1. Fully generalized nested `sway`

Current `sway` can reorder statements in the current block, but the original addressing system was intended to support deeper major/minor targeting.

Future work could allow `sway` to reason about nested addresses without breaking the current behavior.

### 2. Source-address cleanup

The source-address system works, but it has grown alongside the interpreter.

A future maintenance pass could unify:

- lexer addresses
- parser statement locations
- IDE addresses
- runtime error locations
- `sway` addressing

into one cleaner model.

### 3. IDE polish

The IDE works, but future improvements could include:

- stronger autocomplete
- better error highlighting
- source-location navigation from console errors
- richer documentation/help
- more debugging tools

These are polish items rather than missing core language features.

---

# Future development philosophy

Large language additions should be introduced carefully.

A new feature should generally get:

1. a clear syntax design
2. parser support
3. interpreter support
4. IDE support when appropriate
5. a small `.dnd` regression project in `Projects/`
6. documentation in this README
7. a test against older language features

v6 was a large expansion. Future versions should not assume that every useful Python feature needs to be added immediately.

The language should continue to grow around actual projects and useful programming concepts while keeping its own D&D identity.

---

# Project files

Core files:

- `lexer.py` — turns source text into tokens
- `parser.py` — turns tokens into an AST
- `interpreter.py` — executes the AST
- `run.py` — command-line entry point
- `ide.py` — Tkinter IDE
- `README.md` — language documentation

Projects and regression tests live under:

```text
Projects/
```

---

# Building the Windows executable

This project includes the files needed to build the IDE as a Windows executable.

Build it on Windows:

1. Make sure Python is installed.
2. Put the whole project folder somewhere on your computer.
3. Double-click `build_exe.bat`.
4. The built executable will appear in the `dist` folder.

If the source code changes, run the build again to include the new language/IDE behavior.

---

# Current status

**D&D Lang v6 is the current stable feature set.**

The language now has:

```text
values
lists
pouches
Scrolls
Vaults
quests
homebrew
STATS
control flow
error handling
functional tools
sequence tools
type conversion
source addressing
IDE support
```

The next major language version is intentionally being kept separate from this v6 work so the current language can stabilize before another large expansion.
