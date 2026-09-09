# D&D Lang — Lists and Built-ins (20-item reference)

1. `[...]` — Creates a list literal.
   Example: `ability loot = ["sword", "potion"]`

2. `.member_N` — Reads a list item by numeric index.
   Example: `loot.member_1`

3. `.member_variable` — Uses a variable's value as the list index.
   Example: `ability i = 1` then `loot.member_i`

4. Auto-growing assignment — Writing beyond the current end expands the list.
   Missing positions are filled with `none` internally.
   Example: `loot.member_5 = "shield"`

5. `append(list, value)` — Adds one value to the end and returns the list.

6. `push(list, value)` — Alias for `append`.

7. `pop(list)` — Removes and returns the last item.

8. `pop(list, index)` — Removes and returns the item at an index.

9. `map(list, operation)` — Runs a one-argument quest over every item and returns a new list.
   Example: `ability doubled = map(scores, double)` where `double(x)` uses `reward`.

10. `filter(list, operation)` — Runs a one-argument quest and keeps items whose returned value is true.

11. `contains(list, value)` — Returns `honor` when the list contains the value, otherwise `lie`.

12. `index(list, value)` — Returns the first matching index, or `-1` if absent.

13. `len(value)` — Returns the length of a list or Scroll.

14. `max(list)` — Returns the largest value in a list. It also supports `max(a, b, ...)`.

15. `min(list)` — Returns the smallest value in a list. It also supports `min(a, b, ...)`.

16. `str(value)` — Converts a value to a Scroll, preserving `honor`/`lie` wording.

17. `num(scroll)` — Converts a numeric Scroll to a number. Invalid text raises a catchable `ValueError`.

18. `for x in party(list):` — Iterates over every item in a list.

19. `adventure i in total:` — Iterates `i` from `0` through `total - 1`, using the same loop controls as other loops.

20. `+=` with lists — Uses normal `+` semantics, so lists can be extended by adding another list.
   Example: `loot += new_loot`

## Map/filter operations

`map` and `filter` take the name of a one-argument quest as their operation. The name can be bare (`double`) or passed as a Scroll (`"double"`). The quest is invoked in its normal isolated scope, with the current list item supplied as its first parameter.

## Encounter syntax in the same v5 runtime

`encounter Name(...):` is the named-encounter spelling of a quest definition, and `fight Name(...)` invokes it. The first v5 pass reuses quest isolation and `embark` behavior; deeper encounter addressing/debug/sorting with major.minor paths is reserved for the next pass.
