# Generated Curio — approved prototype contract

**Approved by Sam in Discord message `1549133159038189651`. Implementation authorized, including the new CHAOS save format and rejection of older CHAOS-on saves. This contract is approved; the feature is not yet implemented.**

C is the game's implementation language; Lua is the embedded scripting language. CHAOS is the build option enabling NyarlatHack extensions. Sanity is the game's mental-stability statistic; Insight is its occult-perception statistic. The prototype adds no new inference allowance: use GPT 5.6 Luna (`gpt-5.6-luna`) through ChatGPT OAuth (Open Authorization), provider `openai-codex`, with at most two new attempts within the existing shared 20-request / $1 authorization. Subscription usage is not an application programming interface (API) usage bill. Stop on failed safety/review gates or exhausted allowance rather than switching providers or inventing a demonstration.

## Purpose and choice of first slice

Prove that the large language model (LLM) can author a new Gothic object and its behavior through Lua, without adding story-specific C code. The literary examples are creative anchors, not items to hardcode.

Object-first is recommended because it exercises authorship, conditional behavior, owned state, actual effects and persistence together. Generation-only probability profiles are smaller but do not prove interactive authorship. A moving companion or cross-level enemy first would add substantially more combat, display and lifecycle risk.

## Deliverable

One generated curio per game, eligible for placement on a genuinely new, ordinary main-dungeon level 2 or 3. It has a model-authored name and Lua inspect/apply functions. A single explicit authoring operation produces the candidate before play; subsequent inspection and use run locally, with no model request per interaction. A saved candidate can be played offline.

There is no guarantee of placement when both early floors are bones, scripted or otherwise ineligible. Placement, visible presentation and actual player attention are different claims. The prototype must demonstrate early discovery in ordinary eligible play, not count an unseen object as success.

## Initial capability contract

- Exact Lua source: at most 4,096 bytes, using a fresh bounded virtual machine, no libraries, host access, engine pointers, randomness or hidden-map queries.
- The source defines a name, an inspect function and an apply function. Proposed hook names are `inspect` and `apply`; these are new interfaces, not claims about the current movement-only interface.
- The name is printable ASCII (American Standard Code for Information Interchange), at most 48 bytes. Inspection/application prose is at most 160 printable ASCII bytes. Control characters and malformed output reject; model strings are never format strings.
- Copied input includes the player's allowed Sanity and Insight, remaining uses and one owned state integer from zero through 255. The program cannot change its charge counter.
- Inspect returns text only. It consumes no charge, time, random draw or persistent state update.
- Apply returns text, a new bounded state integer and a Sanity change from minus two through plus two. The engine gives the object three uses. No dice, temporary attribute bonuses, map revelation, creation of other items or spawned actors in this first version.
- Validate the entire result before any effect or owned-state update. Successful use consumes an ordinary action and one use. Invalid/depleted/orphaned use gives a fixed inert response without a charge or turn; it never falls through to the carrier's native ability.
- Here `delta` denotes the requested Sanity change and `FALSE` disables the additional acute-madness random check. Call `change_usanity(delta, FALSE)` rather than editing player statistics directly. This retains native bounds, glyph updates and maximum-health/energy recalculation while omitting the additional acute-madness random check. Log requested and actual change; this is not a promise that Sanity is an isolated scalar.

The small effect limits are proposed prototype limits, not a claim of finished balance. Richer native actions can be added to the same interface after this slice works.

## Admission, placement and budget

One accepted candidate costs one engine-owned cruelty point within the existing lifetime ceiling. No refill or increased ceiling is included. Admission is exact-source and precedes placement; it is not proof of discovery. A failed or late candidate does not block normal play.

Keep admission separate from level generation using a saved one-shot placement record. At the end of eligible native generation, try bounded native placement without altering existing room-generation weights. Capture genuine-first-generation status before the engine clears discarded-level flags. Do not modify bones, scripted/prototype maps, revisits or reconstructed previously visited levels.

Prefer an ordinary room near the arrival stairs where feasible; use a dry legal cell, excluding traps, existing objects, monsters and shops. Invoke native object creation/placement only after admission. If neither eligible early floor can place the object, retire the placement opportunity without rerolling maps or replacing a later-destroyed object. Preserve inactive/empty-mailbox/CHAOS-off random-call order.

## Object identity and carrier hardening

Use one fixed-size, pointer-free program record in player-save state and an explicit object tag: ordinary, generated, or inert generated remnant. Do not use names, native charge/auxiliary fields (`spe` and `ovar1`) or artifact identity as the discriminator. Binding requires generated tag, matching object identifier, expected carrier type, quantity one and actual player inventory ownership.

Use the native whistle object type (`WHISTLE`) only as an internal carrier, not as a whistle the player can secretly activate. Intercept tagged use unconditionally before native artifact/whistle dispatch. Suppress carrier-specific Andromalius offering behavior. Give tagged items generated-specific names and descriptions, and explicit no-sale/no-billing treatment; setting a price to zero alone is insufficient.

Do not pass generated names through `oname()`, which can create or transform artifacts. Block native renaming for this first slice, avoid carrier encyclopedia text, and do not identify ordinary whistles through the generated item. Reject merging tagged objects. Ordinary carrying, dropping, throwing and destruction remain physical engine interactions; the object is not claimed to be mechanically inert.

Drop, theft, containers and level unload retain binding. Save/unload must not be mistaken for destruction. Copies do not receive executable ownership. Polymorph ends the generated identity rather than transferring the program to the replacement. Bones output and ghostly input demote generated tags to permanently inert remnants; do not clear them into functional ordinary whistles.

## Persistence consequence requiring approval

The player record and object tag require an explicit new CHAOS save-format discriminator. Older CHAOS-on saves will be rejected rather than silently interpreted or migrated. Merely relying on the engine's packed structure-size checks is insufficient. Ordinary CHAOS-off behavior remains supported and separately tested.

## Authoring prompts and continuity

Use the trusted capability/output contract, shared Gothic prompt, one primary literary layer and bounded public context—not the whole library on every call. The model authors original source and descriptions; do not teach it a fixed portrait or raven implementation.

Store a compact editorial continuity note separately from the C request/source admission. Proposed limit: 512 bytes per note and the six latest notes in prompt context. Bind each to candidate identity and host-assigned status. Plans, rejected proposals, admitted programs and actually presented events remain distinct. Notes are fallible quoted context, not instructions or authority to enlarge permissions. Preserve raw generation response and exact decoded Lua bytes with provenance.

Continuity comments are explicit creative summaries, not hidden scratch reasoning. No extra model call is made solely to maintain them. Rollback or inconsistent evidence must not feed a future narrative back as current fact.

## Acceptance gate

1. A hand-authored fixture exercises inspect/apply, both Sanity directions and owned-state transitions through the actual engine.
2. Tests cover invalid/resource-exhausted programs, charges, output validation, both inspection modes, artifact-name attacks, tagging/copies, naming/identification, shops/offerings, drop/unload/restore, polymorph, bones and generation exclusions.
3. Both build modes and inactive/empty-mailbox behavior pass; genuine terminal inspection/use and save/restore produce correct effects and clean director logs.
4. Freeze the hook contract, then make at most two new live authoring attempts under the existing shared request ceiling, without resetting it or changing provider. At least one new model-authored program must pass validation and work in the real game without a story-specific engine edit. Compare behavior across supplied contexts, not only filenames or source hashes.
5. Independent specification and correctness/security review pass before publishing. GitHub Actions runs the offline checks; it receives no model credentials.

## Explicitly later

Fountain/sink promotion, persistent visual ravens, bell presentation receipts, amontillado naming, temporary Charisma/telepathy, dice-based checks, mirror enemies, pursuit and quest-stage expansion are later capabilities—not hidden promises in this object prototype. Their literary motifs can inspire supported descriptions, but text must not pretend an unavailable mechanic was implemented.
