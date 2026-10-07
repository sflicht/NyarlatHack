# Proposal: model-authored content in ordinary play

Status: proposal only. Docs only; no `chaos/` or `src/` change.
Verification tier B. Player-visible delta: none.

The evidence is the generation pilot in
`docs/measurements/model-authoring-pilot/` (PR #241): 318 generations over
six surfaces from 17 real recorded games, each checked with the repository's
own native validators.

## Why

Host-prescribed effects alone make "yet another NetHack variant". The point
of NyarlatHack is model-authored changes that respond to what this player
did, with Gothic flavour coming from the model's reading of that history.
Today every model-authored surface is either off in the default game or
reduced to a host template. This proposal says how each surface should
enter ordinary play, starting with **curios**, and what the pilot showed.

Terms used below:

- **Public history**: the allowlisted projection of the run's native event
  log, `public_context(state)` (`chaos/history.py:250`, capped at 6144
  bytes). It holds what the player did and saw, plus sanity and insight.
  Nothing hidden.
- **Admission**: the engine's native check that a model-written module
  loads, runs within limits and returns the right shapes, before anything
  reaches play.
- **Surface**: a place where the model writes something the player meets:
  the curio, the hound, a next-use program, end-of-game narration.
- **Literary layer**: one of the eight short style files in
  `chaos/prompts/curio/` (abbott, carroll, chambers, gilman, hodgson,
  mackay, poe, wilde) appended to the curio contract.

## 1. Inventory: what exists today

### 1.1 The shared sandbox

`src/chaos_lua.c` runs every model-written module.

- Each call gets a fresh Lua VM (:204, :212). No libraries or host functions
  are installed (:206-207), and only text chunks load (:142).
- Memory is capped at 256 KiB (:7) and execution at 20000 instructions (:8,
  :209). There is **no wall-clock limit**; the instruction cap bounds time.
- The model never touches game state. Every hook returns a small table that
  the C code range-checks and then applies through existing engine paths.

### 1.2 Curio

**Authoring (Python)**

- `chaos/curio.py` composes prompts and parses replies.
  - Caps at :39-43: source 4096 bytes, note 512, prior notes 6, response
    8192, prompt 8192.
  - `parse_envelope` (:114-132) requires exactly `{lua_source,
    continuity_note}` in strict JSON. It does not check Lua.
  - `compose_prompt` (:194-221) joins `contract.txt`,
    `mechanics-sanity-insight.txt`, `gothic.txt` and one layer file. Its
    public context is **only sanity and insight**, plus optional
    host-asserted role and race (:135-156).
- `chaos/curio_generation.py` `generate_curio` (:318-446) makes one explicit,
  ledgered live attempt.
  - Order: ledger preflight before any credential; byte-exact
    `raw-response.json`; store; register; receipt.
  - It never installs, and failures are not retried.
  - The CLI is `scripts/generate_curio.py`.
- `chaos/curio_store.py` keeps exact-byte bundles keyed by source SHA-256
  (:317-336). `install_saved_source` (:402-423) writes `curio.lua` into a
  run directory.
- `chaos/curio_continuity.py` is a hash-chained journal (:396-473).
  `prior_notes` (:476-494) feeds up to 6 earlier notes into a prompt.
- **Layer choice** is the fixed default `poe`. Nothing seeds or rotates it.

**Native hooks** (`src/chaos_lua.c`, `src/chaos_curio.c`)

- The module returns `{name, inspect, apply}`.
  - `name`: 1–48 printable ASCII characters.
  - Hook input: `{sanity, insight, charges 0..3, state 0..255}`.
  - `inspect` returns one string of 1–160 characters.
  - `apply` returns `{text, state, sanity_delta -2..+2}` (:157-176).
- **That is the whole capability set:** a message, a byte of state and a
  Sanity change of at most 2.
- **Inspect** (`chaos_curio.c:87-101`) runs only on a matching curio in
  inventory. A failure shows "This curio is inert."
- **Apply** (:104-146):
  - prints the requested delta and the text;
  - spends one of 3 charges and applies the delta with `change_usanity`;
  - logs `applied requested=N actual=M`;
  - on a runtime failure, disables the curio for good.

**Admission and placement**

- **Admission** is `chaos_curio_safe`, called at every safe point
  (`src/chaos_engine.c:259`).
  - Gates: phase VIRGIN; Dungeons of Doom DL1–2; budget at least 1.
  - The source is a private `curio.lua` in the run directory. If it is
    absent, admission simply retries at the next safe point (:298).
  - It runs load, inspect and a discarded dry-run apply, then snapshots
    `curio-used.lua`.
  - It debits **price 1** (`include/chaos_protocol.h:34-35`) and prints
    "An uncanny curio may appear on a later floor." (:328).
  - There are no refunds.
- **Expiry**: an unplaced curio expires at DL3 or deeper (:283-289).
- **Placement** happens on the first fresh, non-bones, ordinary-room level
  at DL2–3.
  - The square is chosen deterministically: the upstairs room first, then
    the square nearest the upstair (:197-235).
  - Placement prints nothing.
  - Whether `mksobj(WHISTLE)` draws RNG is unverified (`src/mkobj.c:754`).
- **Save and bones:**
  - The record rides in `struct you` and is re-validated in a fresh VM on
    restore, or the save is refused (`src/restore.c:476`).
  - Bones demote every curio to an inert remnant (`src/bones.c:76-84`).

**Launcher and evidence**

- **Launcher:** `--curio-source` and `--curio-bundle-root` (plus
  `--curio-candidate-id`) are mutually exclusive (`chaos/launcher.py:78-94`).
  Both are checked before any directory exists, and both default to none.
- **Default game:** `chaos play --ordinary` installs no curio.
- **Evidence:** `docs/evidence/curio/` holds review records only. The
  gameplay tests (`test_curio_gameplay` 8a–8e2) use handwritten sources.

### 1.3 Hound

- `chaos/prompts/haunting.txt` is the authoring prompt. It **prescribes the
  algorithm**: "Use the position three observations before the newest
  one…" (line 8).
- The module is one function. It receives `{mx, my, state, history[≤8]}`
  and returns `{dx, dy, state}` (`src/chaos_lua.c:216`). It is called per
  decision from `src/chaos_haunt.c:70`.
- The engine telegraphs "Something has learned the rhythm of your
  footsteps." (`src/chaos_haunt.c:259`). It snapshots `haunting-used.lua`
  (:244), and the shadow trial in `src/chaos_haunt.c:136` gates it.
- **In the default game** the hound is on (`chaos play --ordinary`, #198),
  and its module is the **hand-authored** `chaos/packs/footsteps.lua`
  (`HAUNT_DEFAULT`, `chaos/launcher.py:42`).
- The one real model output is `chaos/packs/luna-footsteps.lua`, kept
  verbatim (`docs/evidence/milestone2-luna-generation.json`).

### 1.4 Next-use programs

- Ordinary play runs next-use programs that the **host composes** from
  templates: `chaos/next_use_compose.py:98-135` writes the `on_action`
  source.
- The model-authoring path also exists.
  - `chaos/next_use_author.py` has its own prompt, a native parser
    (`NativeAuthorValidator`, :81) and caps (prompt 12288, response 8192,
    source 4096; :26-28).
  - `author_offline` (:206) accepts **only** the fake transport, so nothing
    authors a next-use program live today.
- Telegraphs are host-fixed strings (`TELEGRAPHS`,
  `chaos/_protocol_contract.py:280`).

### 1.5 End-of-game narration

The engine writes the reveal ("The Crawling Chaos remembers.",
`src/chaos_reveal.c`, `reveal.json`). `chaos/chronicle.py` formats it and
deliberately derives nothing. **There is no model-written narration
surface.** The pilot's epilogue prompt was written for the pilot.

### 1.6 Real model output and the adapter

Before the pilot, the real model output was:

- one curio, generated outside the repo on 2026-09-15 (openai-codex, layer
  poe, sanity and insight only). It was observed in a native run whose
  directory no longer exists. Nothing from it is committed.
- one hound module (`chaos/packs/luna-footsteps.lua`);
- one whisper smoke.

**The adapter is pinned to openai-codex.** `chaos/oauth.py:19-21` pins the
model, `PROVIDER="openai-codex"` and `LIMIT=20`, and `CURIO_LIMIT=2` is
at :32. It uses Hermes's `_build_codex_client`. `chaos/` has no xAI route.

**Proven:**

- the sandbox and every native admission path;
- curio inspect, apply, save and bones with handwritten sources in real
  ordinary play;
- the hound with a hand-authored pack.

**Only scaffolded:**

- any model-authored module in a default game;
- non-poe layers and prior notes in real use;
- live next-use authoring;
- seed-plus-log replay of a curio game;
- an xAI route.

## 2. What the pilot showed

The route was the configured xAI model over Hermes's xAI OAuth, through a
local Hermes proxy, with no API key. Full report:
`docs/measurements/model-authoring-pilot/README.md`.

| Surface | Valid | Median / p90 latency | Read |
|---|---|---|---|
| curio, current prompt | 68/72 | 138 / 188 s | Gothic, crafted, generic |
| curio + public history | 33/33 | 182 / 252 s | Thematically responsive |
| hound, current prompt | 61/61 | 32 / 44 s | Identical to the hand pack |
| hound, free design | 30/30 | 93 / 199 s | 30 distinct, valid pursuits |
| next-use program | 61/61 | 64 / 92 s | Valid, near-identical |
| epilogue (pilot prompt) | 57/61 | 47 / 161 s | Truthful, flat |

- **Validity is not the bottleneck.**
  - Curio failures were envelope-level: one non-JSON sentence, one source
    over 4096 bytes, one note over 512 bytes, and one transport failure.
  - Epilogue failures were 4 lines over 160 characters.
  - No admitted curio failed at run time across a 600-call context grid.
- **Latency is minutes.** Every surface has to be generated asynchronously,
  well ahead of use.
- **Responsiveness needs history in the prompt.**
  - With only sanity and insight, curios could belong to anyone.
  - With the public history, 20 of 33 curios turned on sound and reeds for
    whistling Bards, against 10 of 68 without it. A Wizard got "a visiting
    card case, suited to a wizard". A Madman got a card that "rhymes with
    retraced steps".
- **Where the prompt prescribes the behaviour, the model only transcribes
  it** (hound). Where the capability set is tiny, the programs converge
  (next-use).
- **Prompt sizes exceed today's caps:** curio + history is 9.2–10.2 KB
  against 8192; the pilot's next-use prompt is 12.5–13.5 KB against 12288.

## 3. Design: curios in the default game

### 3.1 When

**Trigger.** The director requests one curio per game, at the first safe
point where all of these hold:

- the public history shows at least 150 turns, and at least 2 completed
  episodes or 1 whisper the player saw;
- the game is on DL1–2;
- the budget is at least 1;
- the curio phase is VIRGIN.

**Asynchronous; never blocks.** Generation is a background task in the
director (`chaos/director.py:595-657` already polls with a deadline).

- The deadline is **8 minutes (480 s)**: raised to 8 minutes, Sam
  2026-10-04, after the rerun's 368/391 s responses.
- The lane enforces it on its own monotonic clock from the request, whatever
  the transport does, and a regeneration gets only the remainder. Past it the
  lane records `failed` / `deadline` / `LaneDeadline` and stops. A result that
  arrives later is written as that failure, never as ready, so nothing is
  published and no restore or replay can use it.
- On success the director runs the same native checks the engine will, then
  publishes `curio.lua` under the mailbox lock. The engine picks it up at the
  next safe point.
- If the player reaches DL3 first, native expiry closes the chance, and
  nothing is shown.

**Director runtime (decided).** Model authoring gets its own background
deadline of 8 minutes. All other director timing is unchanged, including
the launcher's 300 s director runtime default (`chaos/launcher.py:108-111`).

### 3.2 Grounding

**Prompt.** The prompt gets `public_context(state)` as quoted data:

- the observed summary (turn, sanity, insight, vitals, budget);
- recent public events (backtracking, applying, praying, eating,
  descending);
- completed whisper episodes with their notice evidence;
- prior whispers the player saw.

That satisfies rule 6: nothing comes from maps, monsters, the RNG or other
files. The hooks still see only sanity, insight, charges and state, so
responsiveness lives in the prose fixed at generation. That is honest, and
it is what the pilot measured.

**Code change (decided).** This needs one deliberate change in
`chaos/curio.py`:

- accept the projection as data;
- **raise the curio prompt cap from 8192 to 12288 bytes**, matching the
  next-use author's cap. The pilot's largest history prompt was 10240.

**Continuity (decided).** There is one curio per game. Cross-game notes
from the existing journal stay **off at launch**: a note is earlier model
free text, the one channel that could carry stale claims. Revisit after
Sam's solo playtests (§6).

### 3.3 Literary layer

Use **seeded rotation**, `layers[hash(game seed) % 8]`.

- It is replayable and needs no extra call.
- The pilot admitted all eight layers at the same rate, so no layer needs
  excluding.
- A history-matched choice adds a call for little gain.

### 3.4 Placement, telegraph and flavour

- **Placement:** keep the native placement unchanged.
- **Telegraph (rule 4):** the host-written admission line "An uncanny curio
  may appear on a later floor." comes before the object exists. Every use
  then prints the requested Sanity change before applying it.
- **Flavour:** the model writes the name, inspect text and apply text. That
  is already the curio. Add one host check before install: across the
  validation grid, no text may promise effects outside the capability set
  (items, teleports, damage, monsters, future events). The sandbox already
  keeps behaviour truthful; this check keeps the prose truthful.

### 3.5 Replay

**Run evidence.** The run directory records:

- the exact raw response and its SHA-256;
- the `lua_source` and its SHA-256 (the candidate id);
- the prompt SHA-256, the layer and the public-context hash;
- a receipt naming provider, model, route, latency and tokens.

**Replay installs from that log and never regenerates.** A curio replay
backend publishes the logged source at the logged safe point, reusing
`curio_store.install_saved_source` in verify mode. The engine's own
`curio-used.lua` is the cross-check.

**Before anyone claims seed-plus-log replay**, two things must hold:

- a test that a recorded curio game replays to identical events;
- an answer on whether `mksobj(WHISTLE)` draws RNG.

### 3.6 No model configured or reachable

The fallback is **no curio** (decided). A canned curio would blur what a
playtest shows about model content.

- With no provider configured (§5.1), or a configured provider whose
  credential is missing, the director never asks, and the player sees
  nothing.
- A configured provider that is unreachable is the transport rows of §3.8:
  no curio this game.
- Tests and the random and replay backends stay offline through the
  existing injectable `client_factory` seam.

### 3.7 Safety

- **Validator and capabilities:** the native validator, the sandbox limits
  and the capability bounds are unchanged. The director's pre-check is an
  early filter; the engine's admission remains the authority.
- **Display:** 48-character names and 160-character texts, printable ASCII.
- **No hidden information:** the prompt is the public projection only.
- **Budget:** price 1 with no refunds, shared with whispers. The director
  does not request a curio when a planned whisper needs the last unit.
- **Bones:** unchanged; a curio becomes an inert remnant.

### 3.8 Failure modes, and what the player sees

| Failure | Handling | Player sees |
|---|---|---|
| Provider error, 502, 429 | Up to 2 transport retries within the deadline; honour `Retry-After` | Nothing |
| Deadline passed | Abandon on the lane's clock (`LaneDeadline`); ledger records it | Nothing |
| Not JSON, or over size | Reject; at most 1 regeneration if time allows | Nothing |
| Invalid Lua or grid failure | Reject before install | Nothing |
| Prose promises a false effect | Reject before install | Nothing |
| Reached DL3 first | Native expiry | Nothing |
| Admitted, no square on DL2–3 | Native `placement_unavailable`, then expiry | The admission line; cost already paid (today's rule) |
| "Boring" | Shipped; judged in Sam's playtests | A dull, valid curio |

## 4. The other surfaces

Curios go first, and the free-design hound comes next (decided). Next-use
authoring and narration are each a later slice with its own Sam decision.

- **Hound.** The prompt is the problem, not the model.
  - Replace the prescribed sentence in `haunting.txt` with the pilot's
    "design the pursuit from this summary; keep it learnable and escapable".
  - Generate at the same asynchronous point, before the haunt's admission.
    A free-design module still has to pass the shadow trial (#190).
  - Keep `footsteps.lua` as the fallback when no model is configured or
    reachable, because the hound is already on by default.
  - The open question is whether varied pursuits play better. That needs
    people, not bots.
- **Next-use programs.** Authoring is valid but adds little while the
  capability set is four ops.
  - Wire `author_offline` to a real transport only if the capability set
    grows.
  - Otherwise keep host composition, and let the model write the
    *telegraph and reveal wording* within truthfulness checks instead.
- **End-of-game narration.** This would be a new surface.
  - The pilot shows the model stays truthful under a "numbers must appear in
    the reveal" check, but flat.
  - If wanted, it belongs in `chaos/chronicle.py`, as a separately labelled
    "Interpretation" beside the engine's reveal, never replacing it.
  - Its prompt needs room to interpret (motifs, the player's choices), and
    its checks need to enforce the 160-character bound.

## 5. Provider plan: configurable provider and model

### 5.1 Configuration

The shipped software hard-codes **neither the provider nor the model**.
Each is one setting, given by an executable flag or an environment
variable:

| Setting | Flag | Environment variable | Default |
|---|---|---|---|
| Provider | `--author-provider` | `NYARLATHACK_AUTHOR_PROVIDER` | none |
| Model | `--author-model` | `NYARLATHACK_AUTHOR_MODEL` | none |

**Precedence:** the flag wins over the environment variable, and the
environment variable wins over the default. An empty variable counts as
unset.

**Provider values at launch:**

- `xai-oauth`: the xAI OAuth login held by Hermes. `XaiOAuthBackend` in
  `chaos/oauth.py` uses Hermes's existing
  `agent.auxiliary_client._build_xai_oauth_aux_client(model)`, the same
  pattern as today's `_build_codex_client` (`chaos/oauth.py:24-28`).
  Hermes owns the credential pool and refresh. NyarlatHack never reads,
  copies or logs a token. Development and Sam's playtests use this value,
  launched through `scripts/hermes_play.py`, which runs the launcher under
  Hermes's runtime.
- `xai`: the xAI API with a key from the user's environment (below), for
  shipped software without Hermes.
- `openai-codex`: the existing Codex OAuth adapter through Hermes, kept as a
  value instead of a pin.

**Nothing configured.** With no provider, there is no model content: the
director never asks, every surface falls back offline (no curio;
`footsteps.lua` for the hound), and nothing is shown. This is the default.

**Partial or bad configuration.** A provider without a model, a model
without a provider, or an unknown provider value stops the launcher before
it creates a run directory, with an error naming the flag and variable to
set. A model id is never guessed or defaulted.

**Recording.** The resolved provider and model, and for API-key providers
the *name* of the key variable, go in the run's choice record and in every
ledger row and receipt. The key value never does.

### 5.2 API keys

An API key comes only from the user's environment at run time. **No API
key appears in the code.**

- **Which variable.** An API-key provider reads its provider-standard
  variable: `XAI_API_KEY` for `xai`. The existing `--api-key-env` pattern
  (`chaos/__main__.py:228`, "environment variable NAME, not a key") can
  override it. That flag names a variable and never holds a key.
  - The name must be a valid environment variable name.
  - `--api-key-env` is rejected for OAuth providers, which hold no key.
- The key is read with `os.environ` when the backend is built. This follows
  `ModelBackend`'s env-var-name pattern (`chaos/model.py:47-51`).
- No key literal, key-like placeholder or sample key goes in source, config
  files, tests, fixtures, docs or the pilot harness. A test that needs "a
  key is set" builds a throwaway value inside the test process and writes
  it nowhere.
- No key-loading code reads a file in the repository, and there is no
  `.env` support.
- The key is never logged, never written to run evidence or the ledger,
  never put in an exception message, and never committed. Errors name only
  the variable ("XAI_API_KEY is not set").
- A configured API-key provider whose variable is unset is "no model
  reachable": no model content, as in §3.6.
- The secret-history CI scan is the backstop, not the plan.

### 5.3 Files to change (later slices, not this PR)

- `chaos/oauth.py`: **remove the hard-coded `MODEL` / `PROVIDER` pin**
  (`chaos/oauth.py:19-21`) and read both from configuration (§5.1);
  `XaiOAuthBackend` and the `xai` API-key backend; ledger records per
  surface.
- `chaos/__main__.py` and `chaos/launcher.py`: `--author-provider`,
  `--author-model` and `--api-key-env`, with the environment fallbacks and
  precedence of §5.1.
- `chaos/curio.py`: history projection as data; the cap raised to 12288.
- `chaos/curio_generation.py`: called by the director, with a deadline;
  seeded layer selection; the prose truthfulness check.
- `chaos/director.py`: the background authoring task and the trigger.
- `chaos/launcher.py`: the ordinary default (on when a provider is
  configured and its credential is available); the 6-minute authoring
  deadline (§3.1); a choice-record field naming the authoring state,
  provider and model so restore follows it, as #198 did for the hound.
- A curio replay backend beside `chaos/director.py:520-594`.
- Tests: fake transports for every row of §3.8, and replay equivalence.

### 5.4 Ledger and cap

Each provider keeps its own ledger. The `$1, 20-attempt` openai-codex
ledger keeps its caps. The xAI providers get their own ledger beside it,
sized for real use:

- **Durability:** every HTTP attempt is reserved durably before it is sent
  (the pilot's `attempts.jsonl` pattern).
- **Per game:** 3 requests per surface (1 generation plus up to 2 transport
  retries).
- **Per day, per user:** 200 requests by default, configurable. This guards
  against runaway loops; it is not a spending limit, since Sam reports ample
  OAuth budget.
- **Per ledger file:** 2000 requests, as in the pilot.

What goes where:

- **Model ledger** (user data directory): provider, model, route, time,
  HTTP status, latency, token counts, prompt and response SHA-256, run id.
- **Run evidence** (run directory): the exact raw response, the source,
  hashes, the layer, the context hash and the receipt. That is everything
  replay needs.
- **Neither** holds credentials or request headers.

### 5.5 Latency and rate limits

- **Pilot traffic:** 6–8 concurrent calls through the local proxy over
  about two hours, with no 429.
- **Pilot failures:**
  - 27 client timeouts, all at the 180 s limit on curio prompts and none
    after it was raised to 420 s;
  - 4 proxy 502s, all recovered by retry.
- **In play:** one or two requests per game are far below any limit seen.
  A 429 means "no model content this game".

## 6. Measurement

**Primary: Sam's informal solo playtests** (decided 2026-10-07, §8). There
is no pool of players, so there is no people A/B, no arms and no seed
parity.

- Sam plays default games on the VPS with the model configured, following
  `docs/playtest-kit.md`.
- He keeps short notes per game with the kit's template: the turn, what
  happened, whether it seemed to know what he had done, and whether it was
  fun.
- Report his notes verbatim, without counts or significance claims.

**Secondary:**

- Rerun the generation pilot after each prompt change.
- Run bot sweeps only as safety regressions: no crash, save desync or curio
  in bones.

## 7. Slices

1. The pilot (#241) and this proposal. Docs and measurement only.
2. Configuration, transport and grounding:
   - remove the hard-coded `MODEL` / `PROVIDER` pin in `chaos/oauth.py`;
     read both from configuration (flag, then environment variable, then
     the no-model default);
   - `--api-key-env` for API-key providers;
   - `XaiOAuthBackend` and the `xai` API-key backend;
   - the ledger;
   - curio history grounding and the cap change;
   - the replay backend;
   - offline tests;
   - a pilot rerun.
3. Curios default-on in ordinary play: the trigger, the director task and
   the launcher default. Evidence is a real nonwizard `--ordinary` capture
   showing a model curio admitted, found and used.
4. The solo playtest setup: `make install` builds and installs the curio
   validator, and `docs/playtest-kit.md` is a short kit for Sam's informal
   solo play (replaces the people A/B, 2026-10-07).
5. The free-design hound (decided as next).
6. Then, each by Sam's decision: model-written telegraph and reveal
   wording, and narration.

## 8. Decisions (Sam, 2026-10-04)

Sam accepted all proposals.

1. **First surface:** curios first.
2. **Grounding:** curios get the public history, and the curio prompt cap
   rises to 12288 bytes (§3.2).
3. **Cross-game continuity notes:** off at launch; revisit after the A/B
   (§3.2).
4. **Fallback with no model configured or reachable:** no curio (§3.6).
5. **Director runtime:** model authoring gets its own background deadline,
   raised to 8 minutes, Sam 2026-10-04, after the rerun's 368/391 s responses.
   Other director timing is unchanged (§3.1).
6. **Key variable for API-key providers:** the provider-standard name
   (`XAI_API_KEY` for xAI), with an `--api-key-env` override that names a
   variable and never holds a key (§5.2).
7. **After curios:** the free-design hound comes next (§4, §7).

Provider and model are both configured by flag or environment variable,
with no hard-coded pin (§5.1), as Sam directed.

### Decisions (Sam, 2026-10-07)

1. **Order:** "Hound first, A/B later" (about 00:48Z).
2. **Measurement:** "I don't have a pool of players to AB test. I am just
   goung to play test imformally myself" (about 00:52Z). There is no formal
   people A/B; §6 and slice 4 are Sam's informal solo playtests.
3. **Model hound default:** "On by default (Recommended)" (about 10:18Z).
   With an xAI author configured, the model-designed hound replaces
   footsteps.lua by default; `--haunt PACK` and `--no-haunt` still opt out,
   and footsteps.lua stays the fallback when the hound lane fails (§4,
   slice 5a).
