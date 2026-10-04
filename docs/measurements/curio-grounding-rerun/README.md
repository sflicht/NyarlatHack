# Curio rerun through the product path (slice 2b)

Grok 4.7 over `xai-oauth`, generating curios through the new product path:
`chaos.curio_author`. This is the authorized rerun of #241's curio pilot
(`docs/measurements/model-authoring-pilot/`), on the same 17 recorded
histories. It is a Tier B measurement.

- Revision: branch `feat/curio-grounding-replay`. Generation ran with
  commit `50dedcdef`'s `chaos/`, which predates the late-response guard (see
  Latency). The analysis and this report are at the PR head.
- Run: 2026-10-04 21:24–21:54 UTC, 34 jobs, 4 workers, inside `hermes-heavy`.
- Validator library SHA-256: `199b29ad…` (in `runs/rerun/run-meta.json`),
  built by `docs/measurements/model-authoring-pilot/build_validator.sh`.

## What the product path does per job

Each job is one `curio_author.author_curio` call, exactly as a game will make
it in slice 3:

1. **Configuration.** `AuthorConfig` `xai-oauth` / `grok-4.7` →
   `XaiOAuthBackend`, built before any ledger row. One ledger row is reserved
   before the request is sent (`runs/rerun/xai-ledger.jsonl`).
2. **Prompt.** `public_context(state)` of the recorded history as quoted JSON
   (`public_history`), plus the history addendum
   (`chaos/prompts/curio/history.txt`). There are no continuity notes. The
   prompt cap is 12288 bytes; the prompts here were 9.4–10.5 KB.
3. **Layer.** `curio.seeded_layer(seed)`: SHA-256 of the seed, mod 8.
   - The recorded histories carry no game seed, so job *i* (sorted history
     *i*, replicate *r*) gets the synthetic seed `1000·r + 17·i + 1`.
   - All 8 layers occurred: abbott 7, chambers 7, carroll 5, poe 5, mackay 3,
     wilde 3, gilman 2, hodgson 2.
   - The rotation follows the hash, not a round-robin.
4. **Deadline.** 360 seconds (Sam).
5. **Native validation.** `chaos.curio_native.CurioValidator`: the engine's
   own `chaos_lua_curio_load`, `inspect` and `apply` at the history's
   sanity/insight (the admission calls), then a 600-call grid.
6. **Truthfulness check.** `chaos.curio_truth` with
   `chaos/prompts/curio/truthfulness.json`, over the name and every
   inspect/apply text the grid produced.
7. **Evidence.** One directory per job (`runs/rerun/jobs/<job>/`):
   - `prompt.json`: the instructions, prompt, layer, seed, prompt SHA-256 and
     public-context SHA-256;
   - `raw-response.txt`: the exact bytes;
   - `source.lua`;
   - `receipt.json`: the outcome, every hash, the native result, the truth
     hits and the ledger row.

   `rerun.py analyze` re-verifies every ready job's hash chain
   (`curio_author.read_evidence`). It also re-applies the rules to the stored
   texts, which reproduced every receipt.

## Results

| | Count |
|---|---|
| Jobs | 34 (17 histories × 2) |
| Envelope parsed | 34 |
| Native admission + grid | **34 / 34** (0 grid failures) |
| Truthfulness rejections | **1** (judged a false positive, below) |
| Ready, as recorded | 33 |
| Late (over 360 s) | 2, now `deadline` under the current code |
| Ready under the current code | **31** |

### Every truthfulness rejection, verbatim

One. `madman-00023-r0`, "Crooked Winder" (Poe layer), apply text:

> You give the key a half-turn. No clock answers. Under the thumb the oval is,
> already, deeper.

Rule `item_gain` matched "give the key". **False positive:** the player turns
a winding key, and nothing is given to them. The rule's clause
`(gives?|grants?|bestows?|yields?|drops?) (you|a|an|some|the) (… key …)`
cannot tell "give the key a half-turn" from "gives the key to you". One false rejection in 34 jobs, where all 34 curios
were honest by my reading, is 3% of jobs.

I also ran the rules over #241's 92 admitted curio texts (32 history-arm
curios and 60 plain-arm curios): 0 rejections. Across both sets that is 1
false rejection in 126 curios. No rejected text was actually false, so
these sets measure only false rejections. The miss rate is unmeasured.

I left the rule unchanged. A fix such as excluding "give the X a …" belongs
with Sam's review of the rule list, not tuned to this run. Proposed narrowing,
for Sam to judge: keep only the form with a recipient,
`(gives?|grants?|bestows?|yields?|drops?) you (a|an|some|the) (…)`, and drop
the bare "give the …" form.

### Latency against the 6-minute deadline

| Median | p90 | Max | Over 360 s |
|---|---|---|---|
| 200 s | 299 s | 391 s | 2 / 34 |

The two late jobs:

- `bard-00023-r0`, 391 s;
- `bard-inherited-00023-r0`, 368 s.

`XaiBackend`'s timeout bounds each socket wait, not the whole response, so a
slow response could finish after 360 s, and the run recorded them as `ready`.
This run found that bug, and this PR fixes it: `author_curio` now marks any
response that arrives after the deadline as `deadline` (`LateResponse`). The
response is kept as evidence but never validated or installed. Test:
`test_response_after_the_deadline_is_never_ready`. The receipts above are
left as recorded; `summary.json` reports both counts
(`outcomes_under_current_code`).

Token use from the ledger:

- prompt tokens: median 3835;
- completion tokens: median 20.4k (10.4k–42.8k).

The xai-oauth route reports reasoning inside completion tokens.

### Comparison with #241's `curio_history` arm

| | #241 `curio_history` | This rerun |
|---|---|---|
| Transport | Hermes proxy on 127.0.0.1:8771 (pilot harness) | `XaiOAuthBackend` in the product path |
| Prompt | the pilot's history arm (9.2–10.2 KB, over the old 8192 cap) | product `compose_prompt(history=…)`, 9.4–10.5 KB, under the 12288 cap |
| Layer | rotated by the pilot | `seeded_layer(seed)` |
| Jobs in ledger | 32 | 34 |
| Valid (native + grid) | 32 / 32 | 34 / 34 |
| Truth-check rejections | 0 (rules applied after the fact) | 1 (false positive) |
| Latency median / max | 182 / 298 s | 200 / 391 s |
| Over 360 s | 0 | 2 |
| First-use Sanity delta | −1: 18, 0: 13, +1: 1 | −1: 25, 0: 6, +1: 2, −2: 1 |
| Distinct inspect / apply texts per curio (median) | 7.5 / 17.5 | 8 / 10 |
| Sound-themed curios (name, inspect or first apply; pattern below) | 20 / 32 | 22 / 34 |
| Plain arm, same pattern | 15 / 60 | — |

"Sound-themed" uses this regular expression, the same for every row, over
the name, the admission inspect text and the first apply text:

```
\b(whistl\w*|pitch\w*|reed\w*|note\w*|sound\w*|tone\w*|hum\w*|chime\w*|bell\w*|echo\w*|trill\w*|pipe\w*|breath\w*|key)\b
```

The product path reproduces the pilot's quality. Every curio validated, and
history-grounded curios lean on sound about as often as the pilot's history
arm did: two thirds, against a quarter in the plain arm. Bard histories,
which are full of whistling, give reeds, pitch-pipes and fermatas; Wizard and
Madman histories give rules, cards and slips. All 34 names are distinct.

The addendum is followed. No ready curio claims to have witnessed or to
remember an event, and several continuity notes say so unprompted ("No
history is treated as witnessed"; "not testimony that the object witnessed
any earlier event").

The responses are slower than the pilot's: median 200 s against 182 s, and 2
over the deadline. With 4 parallel workers, that suggests 6 minutes is
adequate but not generous for Grok 4.7 at this prompt size.

## Examples

`EXAMPLES.md` has five curios, each with its history summary, layer, seed and
both texts, verbatim.

## Files

- `rerun.py`: the harness. Its `generate` mode needs the xAI OAuth login;
  `analyze` is offline.
- `runs/rerun/run-meta.json`, `summary.json` (the `analyze` output),
  `xai-ledger.jsonl` (68 rows: a reservation and a completion per job).
- `runs/rerun/jobs/<job>/`: the evidence directory for each job. There are no
  proxy logs; the route is Hermes's in-process client.

No credential, token or key appears anywhere under `runs/`. That was checked
by scanning for bearer and token patterns.

## Reproduce

```sh
sh docs/measurements/model-authoring-pilot/build_validator.sh <scratch>/validator.so
# Under Hermes's runtime: a launcher that imports hermes_bootstrap first.
hermes-heavy run --project NyarlatHack --label curio-rerun -- \
  <hermes-python> -I <launcher> generate --lib <scratch>/validator.so \
  --out <scratch>/rerun --model grok-4.7 --workers 4
python3 docs/measurements/curio-grounding-rerun/rerun.py analyze <scratch>/rerun
```

The sweep histories (`sweep:` entries in the pilot's `histories.json`) come
from the retained #236 runs. `rerun.py` checks each one's SHA-256 against the
pilot's committed `histories-public.json` before use.

## Limits

- 34 generations: one model, one provider, one day.
- The seed rule is exercised with synthetic seeds, because the recorded
  histories carry none.
- The truthfulness rules were narrowed once against #241's texts before this
  run (`calibration` in the rules file). This run is the first on unseen text.
- No curio here was installed in a game. Installation and replay are proven
  separately with a handwritten source (`docs/evidence/curio-grounding-replay/`).
