# Playtest kit (#44), build `788499dfd`

A small human pilot. The question is whether a player notices what the Chaos
does **without being told it exists**, and whether they connect it to what
they did. No model, network or account is needed.

The kit has two parts. **Give the player only Part 1.** Part 2 is for the
facilitator and contains spoilers. The one-page
[report form](playtest-report-form.md) is filled in after each session.

This kit contains no results. No playtest has been run with it yet.

---

## Part 1: Player brief (spoiler-free)

You are playing dNetHack, a hard roguelike, in a lightly modified build. Play
the way you normally would. There is nothing special you need to do or look
for.

### Build (once)

On Debian or Ubuntu:

```sh
sudo apt-get install bison flex build-essential libncursesw5-dev pkg-config liblua5.4-dev
git clone https://github.com/sflicht/NyarlatHack.git
cd NyarlatHack
git checkout 788499dfd
make install
```

Then send the facilitator the output of this line:

```sh
git rev-parse --short=9 HEAD; git status --porcelain | wc -l; sha256sum dnethackdir/dnethack | cut -c1-16
```

### Start a session

From the `NyarlatHack` directory:

```sh
python3 -m chaos play --ordinary --max-runtime 86400
```

- You play a human Bard with a dog.
- When asked about inheritance, answer `n`.
- The first line printed names a **run directory**. Copy it down; the
  facilitator needs it afterwards.

### How long

About **20–30 minutes**, or until your character dies, whichever comes
first. When time is up, end the game with `#quit` (type `#quit`, then Enter,
then `y`), unless you and the facilitator plan to continue later. In that case,
save with `S` and resume later with
`python3 -m chaos play --reuse-run-dir <run directory> --max-runtime 86400`.

**When the game ends it asks several questions. Answer `n` to all of them.**
You will go through them with the facilitator.

### During the session

- Play normally. Don't try to test or break anything.
- Keep a few short notes as you go: anything that surprised you, and the turn
  number (`T:` on the bottom line) if you can.
- The facilitator will not answer questions about the game while you play.

---

## Part 2: Facilitator notes (spoilers)

**Do not show this part to a player before their session and report form are
done.** The pilot measures unprompted notice. Do not hint, point at the
screen, or explain what happened during the session.

### What `--max-runtime 86400` is for

It keeps the offline director running for up to a day. Without it, the
director stops after 300 seconds and no new next-use program is scheduled for
the rest of the session. The gate sweep used the same setting.

### What can happen in a default game today

All of these come from the ordinary default (`--ordinary`, with the hound,
next-use and pacing on). Most games see only some of them. Exact on-screen
lines are quoted.

- **The omen** (every game, turn 1):
  "A distant whisper brushes against your thoughts." then
  "The shadows lean closer." No rule changes.
- **The echo hound** (decided early; admitted in 88 of 100 default-path sweep
  games):
  - Telegraph: "Something has learned the rhythm of your footsteps."
  - A jackal-bodied hound hunts where the player stood a few moves ago. It
    appears only more than four squares from the pet, after one hidden trial
    showing the player could escape.
  - It can be killed. It gives up after about 60 turns or when the player
    leaves the level.
- **Door reluctance** (possible after the player first leaves Dlvl 1):
  - Telegraph: "The doors of this place seem to lean against you."
  - Closed doors resist the player's own attempts to open them more often
    ("The door resists!"), for up to 300 turns.
- **Hunger** (possible after leaving Dlvl 1, once Sanity has fallen to 90 or
  below):
  - Telegraph: "An unnatural hunger coils in your stomach."
  - The player gets hungry twice as fast, for up to 50 turns.
- **Thin wards** are also on that menu (Sanity 80 or below): "The lines of
  your wards seem thin and uncertain." The sweeps do not measure them.
- **Ring** (a whistle program; the Bard starts with a tin whistle in most
  games, and sometimes a bell instead):
  - Admitted at a later safe moment, such as a prayer or arriving on a level,
    after the player has used the whistle. Telegraph, first program:
    "For a while, your whistles may ring on after you stop."
    Later programs (up to 3 per game): "Again, a whistle may ring on after
    you stop."
  - On a later whistle: "Your whistle's note goes on ringing inside your
    head." The status line shows `Conf` for 5 moves, then the normal
    "You feel less confused now."
  - Each program rings at most twice. It lasts 100 moves (the first program)
    or 300 (later ones), across levels.
  - Nothing happens on a whistle while the player is confused, stunned,
    hallucinating or engulfed, at a third of max HP or less, or next to a
    monster they can see, or to water or lava. The program keeps waiting.
- **The fountain effect** (a fountain program):
  - Telegraph: "For a while, fountain water you drink may not run true."
    Later: "Again, the fountain's water may not run true."
  - A fountain drink is turned into a refreshing one: "The cool draught
    refreshes you." Like ring, at most twice per program. Dipping does
    nothing.
  - No sweep has ever recorded this effect being felt. Expect it to be rare.
- **The reveal** (at the end of every game, because the omen is always
  admitted): "Do you want to know what watched you? [ynq] (n)". The player
  brief tells players to answer `n`, so the report form comes first. The same
  list is written to the game's dumplog either way.

### After the session

1. Fill in the [report form](playtest-report-form.md), asking questions 1–3
   **before** any explanation.
2. Then show the reveal. It is in the game's dumplog
   (`dnethackdir/dumplog/`, the newest file, section "The Crawling Chaos
   remembers"), or as a page:

   ```sh
   python3 -m chaos chronicle <run directory> --format md --out chronicle.md
   ```

   The reveal is written only when the game ends. A session that ended in a
   save has none until the game is finished.
3. Ask questions 4–6.

**What the engine recorded** (optional, read-only):

```sh
pilot=$(mktemp -d) && ln -s <run directory> "$pilot/run"
PYTHONPATH=tests/chaos python3 -c 'import json, sys, sweep_funnel; a = sweep_funnel.analyse(sys.argv[1], felt=True); print(json.dumps({k: a[k] for k in ("counts", "loss", "qualifying_actions", "last_turn", "first_felt", "haunt", "haunt_steps")}, indent=1))' "$pilot"
```

`first_felt` gives the turn and kind (`hound`, `next_use_W`, `next_use_F`,
`door` or `hunger`) of the first on-screen consequence, or `null`. A
displayed line is not proof of notice. Notice, attribution and changed
decisions come only from the player's answers.

### Collecting the run directory

Copy the whole run directory the launcher printed, plus the session's dumplog
file and its last line of `dnethackdir/xlogfile`. The files that matter:

- `events.jsonl`: what the engine recorded the player did, with turns;
- `whispers.jsonl`, `whisper.json`: the whispers offered and their results;
- `reveal.json`: the engine's own end-of-game record (only after the game
  ends);
- `next_use-*` files: the whistle and fountain programs, if any;
- `ordinary-choice.json`, `director.log`, `haunting.lua`: what was switched
  on, the director's status lines, and the hound's script.

None of them holds a secret: there are no keys, tokens or credentials, and
no model is called. **One holds a path:** `ordinary-choice.json` records the
absolute path of the hound pack (`haunt_pack`), which includes where the player
cloned the repository and may include their user name. Redact that value
before sharing the files. The dumplog and xlogfile line hold the numeric
user id and the fixed character name `ChaosReview`.

### What this kit does not claim

- A pilot of a few sessions is a qualitative check, not a rate. Do not quote
  percentages from it.
- Do not tune cruelty, add effects or change the build during a pilot. A fix
  suggested by a session gets its own reviewed change, and the next pilot uses
  the new build.
- #44's human-execution items stay open until real reports exist.
