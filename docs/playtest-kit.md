# Playtest kit (#44)

This is for a small human pilot: does a player notice what the Chaos does, and
do they connect it to what they did? It uses the ordinary default path and
existing logs only. It needs no model, network, account or new tool.

This kit is preparation. It contains no results. Results come only from real
sessions with real people; see "What this kit does not claim" below.

## 1. Build and record the build id

From the repository root, on Debian or Ubuntu:

```sh
sudo apt-get install bison flex build-essential libncursesw5-dev pkg-config liblua5.4-dev
make -j4 install CHAOS=1
git rev-parse --short=12 HEAD; git status --porcelain | wc -l; sha256sum dnethackdir/dnethack | cut -c1-16
```

The last line prints three values: the revision, the number of uncommitted
changes (it should be `0`), and the first 16 hex digits of the game binary's
sha256. Copy all three into the report form. Every session in one pilot uses
the same build id; if it changes, that is a new pilot.

## 2. Start a session (one command)

```sh
python3 -m chaos play --ordinary --max-runtime 86400
```

- This is the ordinary default: a human Bard with a dog, no wizard mode, with
  the echo hound and the next-use program on (#198) and pacing at its default
  (#164).
- `--max-runtime 86400` keeps the offline director running for up to a day.
  Without it the director stops after 300 seconds; the game keeps going, but
  no further next-use program is scheduled for the rest of the session.
- Answer `n` to the inheritance question, then play normally.
- The launcher prints the session's private run directory. Copy that path into
  the report form.
- To pause, save with `S`; resume with
  `python3 -m chaos play --reuse-run-dir <run directory> --max-runtime 86400`.
  Record every save and resume on the form.

This condition is the **fixed-menu baseline**: the hound comes from a
hand-written pack and the next-use program is host-built, with no model. Do
not describe it as authored-content testing; that comparison waits on #45.

## 3. During the session

The facilitator watches and says nothing about the mechanics: do not explain,
hint or point at the screen. Note, in the player's own words where possible,
anything they react to, and the in-game turn (the `T:` value on the status
line) when they do.

Do not rescue, restart or discard a session because nothing happened. A session
with no effect, or one the player did not notice, is a result.

## 4. After the session, before any explanation

Ask these questions in this order, and write down the answers verbatim before
saying anything about how the game works:

1. What changed?
2. What do you think caused it?
3. Did you change what you did next?
4. Was the behaviour understandable, frustrating, or easy to exploit?

Only after the answers are written down, check them against the record.

## 5. Check against the record

Two existing read-only views of the run directory:

- **What the engine admitted and delivered:**

  ```sh
  python3 -m chaos chronicle <run directory> --format md --out chronicle.md
  ```

  If nothing was admitted, it says there is no `reveal.json`; record that.

- **Where an opportunity was lost, and the first felt consequence**
  (qualifying action, candidate, published, admitted, trigger, native effect,
  delivered, the main loss reason, and the hound). The sweep's analyser reads
  a directory that contains the run as `run`, so link it into a fresh
  temporary directory for each session:

  ```sh
  pilot=$(mktemp -d) && ln -s <run directory> "$pilot/run"
  PYTHONPATH=tests/chaos python3 -c 'import json, sys, sweep_funnel; a = sweep_funnel.analyse(sys.argv[1], felt=True); print(json.dumps({k: a[k] for k in ("counts", "loss", "qualifying_actions", "last_turn", "first_felt", "haunt", "haunt_steps")}, indent=1))' "$pilot"
  ```

  How the output maps onto the form:

  - `haunt`: counts of the hound's recorded stages, for example
    `{"accepted": 1, "pre_admitted": 1}`. `accepted` means the hound was let
    in; `{}` means no hound stage was recorded. `haunt_steps`: hound steps the player
    could see.
  - `first_felt`: the turn and kind (`hound`, `next_use_W` or `next_use_F`) of
    the first delivered, on-screen consequence, or `null` if there was none.
    It has no Dlvl: the analyser does not know which level the player was on
    at that turn. Leave the Dlvl to the facilitator's notes.
  - `counts`, `loss` and `qualifying_actions`: the next-use line.

A displayed line is not proof of notice, and delivery is not attribution. The
last three stages on the form (noticed, attributed, changed decision) come only
from the player's answers.

## 6. Report form

Copy this block once per session, fill it in, and post it as a comment on #44.
Keep every session, including ones with no effect, no notice or a technical
failure.

```text
Session: <pilot name> / <n>          Date:
Build id: <revision> / <uncommitted count> / <binary sha256 prefix>
Run directory: <path, kept until the pilot is written up>
Condition: fixed-menu baseline (ordinary default)
Player familiarity with the mechanic: none / heard of it / knows how it works
  (a player who knows the mechanism is not blind; say so)
Length: <real minutes>, <last turn T:>, deepest Dlvl <n>, how it ended <died / quit / saved>
Saves and resumes: <count; any problem>
Technical interruptions: <none / describe>

Player's answers (verbatim, before any explanation)
  1. What changed?
  2. What do you think caused it?
  3. Did you change what you did next?
  4. Understandable, frustrating, or easy to exploit?

Record (from step 5; write "not observed" rather than leaving a gap)
  Hound (haunt, haunt_steps): accepted?      visible steps
  First felt consequence (first_felt): turn     kind      Dlvl (facilitator's notes, if known)
  Next-use: qualifying actions  W __ F __   admitted?   delivered?   turn
  Main loss reason (from the analyser):
  Chronicle: <admitted n, delivered n>

Stages (yes / no / not observed)
  Engine delivered:           
  Player noticed:             
  Correct causal attribution: 
  Changed decision:           
  Meaningful surprise:        
  Felt repetitive or farmable:

Facilitator notes (what the player reacted to, with T: turn):
Usability defect this suggests, if any (one line; file separately):
```

## What this kit does not claim

- A pilot of a few sessions is a qualitative check, not a rate. Do not quote
  percentages from it.
- Do not tune cruelty, add effects or change the build during a pilot. A fix
  suggested by a session gets its own reviewed change afterwards, and the next
  pilot records the new build id.
- #44's human-execution items stay open until real reports exist.
