# Model-authoring generation pilot

**Question:** if the configured xAI model writes NyarlatHack's model-authored
content from real recorded game histories, how often would the engine accept
it? How does it fail, how long does it take, and does the result read as
Gothic and responsive to the player, or as generic?

**Answer:**

- **Validity is high on every surface.**
  - Curios: 101 of 105 were admitted by the native curio hooks.
  - Hound modules, next-use programs and free-design hound modules: 152 of
    152 passed their native validators.
  - Reveal epilogues: 57 of 61 passed the display and number checks.
- **Calls are slow:** a median of 30 s to 3 minutes per call, by surface.
- **Responsiveness is the weak point.** It is thematic and, where the prompt
  prescribes the behaviour, absent. Details below.

Scope: Sam authorized testing on every surface over the xAI OAuth route
through Hermes, on the Hermes VPS. No API key was used, and
`chaos/ordinary_route.py` was not touched. Nothing here changes `chaos/` or
`src/`.

## Method

### Route

- Every request went to a local `hermes proxy start --provider xai`, which
  attaches the OAuth credential itself.
- The harness never reads, holds or sends a key. It sends no Authorization
  header at all.
- Provider, model and route are recorded in every ledger row and in each
  run's `run-meta.json`. The model id is the one configuration value
  `MODEL` in `pilot.py`.
- Every row reports the served model as the configured one, except the one
  transport failure, which has none.

### Inputs

There are 17 real recorded games, listed in `histories.json` and projected
in `histories-public.json`:

- 15 retained bot games from the #236 arc-later funnel sweep: Bard, Madman
  and Wizard starts on seeds 7, 23 and 41;
- the two committed ordinary captures under `docs/evidence/`.

Each game is projected with the repository's own `public_context()`
(`chaos/history.py:250`), so only what the player did and saw, plus sanity
and insight, reaches a prompt. Every history used has more than 100 turns.

### Surfaces and native validation

Validation uses the repository's own C code, unmodified. `build_validator.sh`
compiles `src/chaos_lua.c` and `src/chaos_next_use.c` into one shared
library, whose SHA-256 is recorded in `run-meta.json`.

| Surface | Prompt | Validation |
|---|---|---|
| `curio` | `chaos/curio.py` `compose_prompt`, unchanged; layers rotated over all 8 | `parse_envelope`, then the native admission calls (load, inspect, apply at charges 3, state 0, the history's sanity/insight), then 600 inspect/apply calls over a context grid |
| `curio_history` | the same, plus the public history projection as quoted data and a one-paragraph addendum | the same |
| `hound` | `chaos/prompts/haunting.txt`, unchanged; input is the public summary | `chaos_lua_step` (the per-decision call, `src/chaos_haunt.c:70`) over 120 synthetic trails; agreement with the hand-authored footsteps pack measured |
| `hound_free` | `haunting.txt` with its one prescribed-algorithm sentence replaced by "design the pursuit from this summary; keep it learnable and escapable" | the same |
| `next_use` | `chaos/next_use_author.py` instructions; input is the public context plus the capabilities for that history's families | the native author parser and shared-sandbox load (`NativeAuthorValidator`), then `on_action` over a 96-context grid per family, with the runtime's family rule |
| `flavour` | a pilot-written system prompt: a 2–4 line Crawling Chaos epilogue over the game's exact reveal lines | JSON shape; 2–4 lines of 1–160 printable ASCII characters; every number must appear in the reveal |

Two caveats on the table:

- **No product flavour surface exists.** The flavour prompt was written for
  this pilot. Telegraph lines are host-fixed (`TELEGRAPHS` in
  `chaos/_protocol_contract.py`), and model-written telegraphs were not
  piloted.
- **Some pilot prompts exceed today's production caps.**
  - `curio_history` prompts are 9.2–10.2 KB, against `chaos/curio.py`'s
    8192-byte cap.
  - `next_use` prompts are 12.5–13.5 KB, against `next_use_author.py`'s
    12288-byte cap, because this pilot passed the whole public context.

### Determinism and the ledger

- Every exact raw response is stored as `runs/<run>/responses/<sha256>.txt`,
  and every user prompt as `runs/<run>/prompts/<sha256>.json`.
- `pilot.py revalidate --lib <so> --out runs/<run>` re-checks every row from
  the stored bytes alone, without calling a model. It was run on all four run
  directories: 318 rows, 0 mismatches.
- `ledger.jsonl` has one row per job, with every HTTP attempt inside it.
  `attempts.jsonl` is written and fsynced **before** each request, so a
  killed request is still counted. It exists only for the runs started after
  it was added.
- The cap is 2000 jobs per ledger.

## Runs (all disclosed)

| Run | Jobs | Notes |
|---|---|---|
| `runs/smoke` | 5 | One job per surface. 180 s client timeout. |
| `runs/pilot-run0-stopped` | 7 curio | First main run; I stopped it after 7 rows to restart with more workers. 180 s timeout. |
| `runs/pilot` | 96 curio + curio_history | Rows 1–39 come from the second main run (180 s timeout). I stopped that run to raise the timeout to 420 s. The remaining 57 came from a `--skip-done` resume. |
| `runs/others` | 210 | hound 60, hound_free 30, next_use 60, flavour 60. 420 s timeout. |

About the resume of `runs/pilot`:

- I cut it to curio-only by mistake: I misread the authorization as covering
  curios alone. The orchestrator corrected this.
- The other surfaces then ran as `runs/others`, on the same histories, with
  the same validator library and the same harness code.

Totals: **318 completed jobs** and **348 HTTP attempts**.

- 27 attempts were client timeouts. All of them were under the 180 s limit
  and on curio prompts.
- 4 attempts got a 502 from the proxy.
- Only one job failed outright on transport (curio, four timeouts).
- No 429 was seen.

## Results

`summary.json` is the output of `analyze.py` over all four runs.

| Surface | Jobs | Valid | Failure kinds | Median / p90 / max latency | Median reasoning tokens |
|---|---|---|---|---|---|
| curio | 72 | 68 (94%) | non-JSON reply 1; source over 4096 bytes 1; note over 512 bytes 1; transport 1 | 138 / 188 / 294 s | 14.2k |
| curio_history | 33 | 33 | — | 182 / 252 / 298 s | 17.3k |
| hound | 61 | 61 | — | 32 / 44 / 208 s | 3.4k |
| hound_free | 30 | 30 | — | 93 / 199 / 234 s | 8.5k |
| next_use | 61 | 61 | — | 64 / 92 / 108 s | 6.6k |
| flavour | 61 | 57 | a line over 160 characters 4 | 47 / 161 / 256 s | 5.3k |

Notes on the curio failures:

- The envelope parser's message for both over-size cases names "utf bytes".
  The real causes were 4743 source bytes and 540 note bytes.
- The non-JSON reply was the single sentence "I will validate the module
  bounds and string lengths before returning the single JSON object."

Further results:

- **No admitted curio failed at run time.** Across 101 curios × 600 grid
  calls there were no inspect or apply failures.
  - Inspect texts vary with context: median 7 distinct texts per curio.
  - Apply results vary too: median 16–17 distinct per curio.
  - The first use requests −1 Sanity in 70 of 101 cases, 0 in 28, +1 in 2
    and −2 in 1.
- **hound:** all 61 modules match the hand-authored footsteps pack on every
  trail case. That is expected: `haunting.txt` prescribes the algorithm,
  and the model transcribes it (51 distinct source texts, one behaviour).
- **hound_free:** all 30 are valid and all 30 are different. Agreement with
  the footsteps pack ranges from 14% to 94% (median 56%). The models used
  their latitude: longer lag when the trail turns, periodic hesitation,
  midpoint targeting.
- **next_use:** all 61 are valid and none is idle. A median 25% of grid
  contexts produce an effect op, and 17 programs use `delay`. There were no
  wrong-family ops. The programs are short and similar: "act once on the
  first unwitnessed use, then count state".
- **flavour:** no epilogue used a number absent from its reveal, and no
  claim contradicted a reveal I checked by hand.

## Honest read

**Curios are Gothic, crafted and mostly generic.**

The register is right every time: small physical discrepancies, restrained
cadence, the layer's voice audible (Carroll's contrary cards, Wilde's gilt
mirrors, Hodgson's salt-stiff sounding lines). But the object vocabulary is
narrow. It is cards, reeds, brass squares, glasses, thimbles, cuffs; "a hair
late", "hairline", "salt" and "gilt" recur. Across the plain arm, one curio
could belong to any player. That is structural: plain `compose_prompt` gives
the model only sanity and insight.

**The history arm is responsive, but only thematically.**

- With the public history, 20 of 33 curios turn on sound, pitch or reeds.
  The plain arm does this in 10 of 68. The Bard histories are full of
  whistling, and the model picks that up.
- "Contrary Teaspoon" comes from a Wizard game with a fountain refresh, and
  its note says so. The note also says the spoon does not witness that
  event, which keeps it truthful.
- "visiting-card case, suited to a wizard" comes from a Wizard game.
- "The Recanting Card" (Madman) "rhymes with retraced steps".

These are the most interesting curios in the set. But the hooks still see
only sanity, insight, charges and state, so the responsiveness is in the
prose, fixed at generation time, not in behaviour.

**Hound: the prescribed prompt leaves the model nothing to author.**
`hound_free` shows it will design varied, valid, escapable pursuits when
allowed. Whether any of them feels better to play than footsteps is a
people question.

**Next-use programs are valid and dull.** They are near-identical small
state machines, because the capability set is tiny (whistle attention,
fountain refresh, delay, quiet). The interest has to come from the
host-written telegraph and the reveal, not the program.

**Flavour epilogues are truthful and flat.** Most restate the reveal in a
slightly older diction ("I remember turn one…"). The truthfulness rules make
the model cautious, so it interprets very little. Four of 61 broke the
160-character display bound.

## Reproduce

Run from the repo root on the VPS, under `hermes-heavy`, with
`hermes proxy start --provider xai --port 8771` running:

```sh
sh docs/measurements/model-authoring-pilot/build_validator.sh <scratch>/validator.so
python3 docs/measurements/model-authoring-pilot/pilot.py generate \
    --lib <scratch>/validator.so --out <scratch>/run --plan curio    # or: others, smoke, <surface>
python3 docs/measurements/model-authoring-pilot/pilot.py revalidate \
    --lib <scratch>/validator.so --out docs/measurements/model-authoring-pilot/runs/others
python3 docs/measurements/model-authoring-pilot/analyze.py docs/measurements/model-authoring-pilot/runs/*
```

Regenerating `histories-public.json` (`pilot.py histories --sweep-root <dir>`)
needs the retained #236 sweep runs, which are not in the repository. The
committed projection is the one every run used.

See `EXAMPLES.md` for verbatim outputs per surface, each with its history.
