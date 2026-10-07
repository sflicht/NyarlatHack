# Solo playtest kit

For Sam, playing informally on this VPS. Spoilers are fine. There is no A/B
and no form; the notes template at the end is enough.

No feedback yet.

## Build

From a checkout of `main`:

```sh
make install
```

`make install` builds the game and the native curio validator, and installs
both into `dnethackdir/`. Without `dnethackdir/curio-validator.so` the
launcher prints `chaos: model authoring unavailable (no_validator)` and the
game has no curio. A `CHAOS=0` build installs neither the Chaos engine nor
the validator.

Note the build:

```sh
git rev-parse --short=9 HEAD; git status --porcelain | wc -l
```

## Play

The model is Grok 4.7 through the xAI OAuth login Hermes holds, so the
launcher runs under Hermes's runtime via `scripts/hermes_play.py`:

```sh
python3 scripts/hermes_play.py play --ordinary --max-runtime 86400 \
  --author-provider xai-oauth --author-model grok-4.7
```

The two variables do the same as the flags:

```sh
export NYARLATHACK_AUTHOR_PROVIDER=xai-oauth NYARLATHACK_AUTHOR_MODEL=grok-4.7
python3 scripts/hermes_play.py play --ordinary --max-runtime 86400
```

- You play a human Bard with a dog. Answer `n` to the inheritance question.
- The first line on stderr names the **run directory**:
  `chaos: run directory "<path>" (preserved on exit)`. Note it.
- `--max-runtime 86400` keeps the whisper director scheduling for a day;
  the default stops it after 300 s. The curio lane has its own clock.
- `scripts/hermes_play.py` looks for Hermes in `~/.hermes/hermes-agent`;
  set `HERMES_AGENT_DIR` to use another checkout. Plain
  `python3 -m chaos play ...` with the same flags runs the same game but
  cannot reach the OAuth login, so it prints
  `model authoring unavailable (no_model_reachable)` and has no curio.
- Requests are capped by the xAI ledger: 3 per surface per game, 200 per
  day. A normal game makes one.

## Save and resume

Save with `S` (then `y`). Resume the same game from the same run directory:

```sh
python3 scripts/hermes_play.py play --reuse-run-dir <run directory> --max-runtime 86400
```

Restore follows what the run recorded (`ordinary-choice.json`), including
the provider and model, so the author flags are not needed again; if given,
they must match. Starting a fresh game while a save exists is refused, with
the resume command printed.

## What to expect

- **Turn 1, the omen:** "A distant whisper brushes against your thoughts."
  then "The shadows lean closer." No rule changes.
- **The hound** (most games, early): "Something has learned the rhythm of
  your footsteps." A jackal-bodied hound then hunts where you stood a few
  moves ago. It can be killed, and gives up after about 60 turns or when you
  leave the level.
- **The curio request.** At the first safe point after at least 150 turns,
  with some history (2 completed episodes or 1 whisper you saw), while you
  are on DL1–2, the director sends one request with your public history.
  Grok usually answers in 2–6 minutes of real time; the lane gives up at
  480 s. Nothing is shown while it waits.
- **The telegraph:** if the curio passes the native checks and is admitted,
  you see "An uncanny curio may appear on a later floor."
- **Placement:** the curio is placed when a new main-dungeon level DL2 or
  DL3 is generated after the admission. It is an ordinary-looking tool with
  a model-written name ("a glass reed locket" in the live capture). If you
  reach DL3 before it is ready or placed, the chance closes and nothing is
  shown. Lingering on DL1–2 gives it time.
- **Using it:** `I` (Describe) shows its inspect text; apply prints the
  requested Sanity change before applying it ("The curio requests a Sanity
  change of -1; native limits may reduce it. This spends one use."), then
  the model's text. Three uses, then it is inert.
- **Other effects** you may meet: door reluctance ("The doors of this place
  seem to lean against you."), hunger, thin wards, a whistle that rings on
  after you stop, fountain water that may not run true.
- **The reveal:** at the end, "Do you want to know what watched you? [ynq]
  (n)". Answer `y` to see what was admitted and delivered, with turns, and
  the curio by the name you saw. The same list goes into the dumplog either
  way.

## Where things land

In the run directory:

- `curio-lane.json`: the curio lane's state (`idle`, `requested`, `ready`,
  `failed`, `no_model`, with its outcome);
- `curio-evidence/`: `prompt.json`, `raw-response.txt`, `source.lua`,
  `receipt.json` (and `curio-evidence-2/` if a regeneration ran);
- `curio-used.lua`: the source the engine admitted;
- `events.jsonl`, `whispers.jsonl`: what the engine recorded, with turns;
- `reveal.json`: the end-of-game reveal (only after the game ends);
- `ordinary-choice.json`, `director.log`.

Elsewhere: the dumplog in `dnethackdir/dumplog/` (newest file, section "The
Crawling Chaos remembers"), the game's line in `dnethackdir/xlogfile`, and
the ledger row in `~/.local/share/nyarlathack/xai-ledger.jsonl`. None of
these holds a credential.

A readable page of the game:

```sh
python3 -m chaos chronicle <run directory> --format md --out chronicle.md
```

## Notes template

One block per game; a line per moment worth keeping.

```text
Build: <short rev> / <uncommitted count>     Date:
Run directory:
Ended: <died / quit / saved>, last turn T:<n>, deepest Dlvl <n>

T:<turn>  What happened:
          Did it seem to know what I'd done?  yes / no / unsure — why:
          Fun or not:

Overall, fun or not:
Anything broken:
```
