# Next-use Lua contract

Bound: main `fe9bab051`. Comparison cites NetHack 3.7
`b63ec1faa7ed7589c5d3f2dc19c154ab6e13f800` (`dat/nhcore.lua`, `dat/nhlib.lua`,
`src/nhlua.c`). This is not a runtime replacement.

## Evidence

Upstream Lua has named callbacks, explicit saved variables, helpers, and a
sandbox. Exposed upstream functions can mutate the game while Lua runs.
NyarlatHack generated candidates compute a typed proposal from a copied public
context plus host-owned state. C validates, admits, and applies.

## Recommendations

Reuse conceptually: named callback `on_action`, explicit state 0..3, fresh
per-call evaluation, protected failure before any native effect.

Do not port: `luaL_openlibs`, package loading, I/O, game RNG, nh/des mutation
APIs, interpreter caches, or a second privileged VM.

Globals, upvalues, and closures reset between calls. Cross-call memory uses
the returned `state` field only. Do not enlarge 0..3 here; that belongs to
#63/#67 with demonstrated need. Optional pure helpers stay out of production
until #67 shows need and binds helper bytes into replay identity.

## Deferred

#19 capability catalogue, #20 remaining authoring scale, #63 persistence of
explicit DATA (not the Lua heap), #67 nonconstant programs over the same W/F
adapters. This note does not close those issues.
