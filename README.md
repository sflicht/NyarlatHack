# NyarlatHack

A dNetHack fork where something is watching. **The Crawling Chaos**, an avatar
of Nyarlathotep, notices what you do in the dungeon and bends the rules in
response: a companion that answers your whistle too eagerly, food that stops
filling you, wards that thin, a hound that walks where you walked. It always
warns you first, and it never cheats: the game engine checks and applies every
change, and every accepted change is logged so a run can be replayed.

## Play in three commands

On Debian or Ubuntu:

```sh
sudo apt-get install bison flex build-essential libncursesw5-dev pkg-config liblua5.4-dev
make -j4 install CHAOS=1
python3 -m chaos play --ordinary
```

Run these from the repository root. `--ordinary` starts a human Bard with a dog
and no wizard mode. Answer `n` to the inheritance question, then play normally.
No model, network or account is needed: the director runs offline from
hand-written packs. `--ordinary` turns on the echo hound and the next-use
program by default (see below); `--no-haunt` and `--no-next-use` turn them off.
The choice is recorded in the run directory, so resuming a game keeps the
choice it started with. Save with `S` as usual; the launcher prints a private run
directory, and `python3 -m chaos play --reuse-run-dir /that/path` resumes it.
`--ordinary` always uses the same character name, so while a saved game exists
a fresh `chaos play --ordinary` refuses to start: it exits with an error naming
the save file and, when it can find the save's run directory, prints the exact
`--reuse-run-dir` command to resume. To start fresh instead, finish or quit that
game, or move the named save file aside yourself; the launcher never touches it.

## What you might notice

The Chaos is **quiet for long stretches**. A character at full Sanity gives it
very little to spend, so most of what it does comes later, or not at all. What
you can meet today:

- **An omen on arrival.** `chaos play` opens with a warning, "A distant whisper
  brushes against your thoughts.", then "The shadows lean closer." Both are in
  Ctrl-P message history if they scroll past.
- **Your whistle, remembered.** Apply your tin whistle (on by default with
  `--ordinary`; `--no-next-use` turns it off). At a later safe moment, such as a
  prayer, you may be warned "The next whistle may call unusual attention." The
  next whistle may then pull your companion to you. Fountains have a matching
  warning: "The next fountain drink may take a different course."
- **Hunger and thinning wards.** Once your Sanity has fallen, the Chaos can
  double how fast you get hungry ("An unnatural hunger coils in your
  stomach.") or halve your wards ("The lines of your wards seem thin and
  uncertain."), each for a short time. The default launcher does not offer
  these; use `--backend random`, or see the quick wizard-mode demonstration in
  the [director guide](chaos/README.md#demonstrate-an-actual-rule-change).
- **The echo hound.** A jackal-bodied hound that hunts where you stood a few
  moves ago, after "Something has learned the rhythm of your footsteps." It
  is on by default with `--ordinary` (`--no-haunt` turns it off; `--haunt PACK`
  picks another Lua pack; the default is `chaos/packs/footsteps.lua`). To
  provoke it, pace back and forth in a room. It only appears more than four
  squares from your pet, so in a small starting room with the pet beside you
  it waits until the pet wanders off or you pace somewhere roomier. The game runs one hidden trial of the
  hound, and only lets it in if you could get away from it. That trial
  happens once per game; fewer than one in ten is refused, more often in a
  cramped, cluttered room. The hound can be killed, and it gives up after about
  60 turns or when you leave the level. It costs the Chaos's whole budget at
  full Sanity, so whichever of the hound and the whistle or fountain program
  is admitted first takes it. The hound is usually decided within the first
  dozen turns, so at full Sanity it usually wins (#164 measures this). See also
  [the First Haunting guide](docs/milestone2.md#play-it-with-no-model-call).
- **Dreamland echoes.** After a hound's trial run, fragments such as "You
  recall footsteps on a path you never took." can appear in Ctrl-P history.
  `NYARLATHACK_ECHOES=0` turns them off.
- **What watched you.** When a game ends after the Chaos did something, it
  offers to show what it did; the same list goes into the dumplog. For a page
  you can keep or share, run `python3 -m chaos chronicle RUN_DIR --out
  chronicle.html` (or `--format md`) on that game's run directory. It reads
  only the engine's own records (`reveal.json`, plus the game's xlogfile end
  record for the character's name and cause of death), works offline and
  writes nothing into the run directory.
- **Playtesting.** [The solo playtest kit](docs/playtest-kit.md): build,
  the play command with the model configured, what to expect, where the
  run's files land, save and resume, and a short notes template.

## Design rules

- **The engine is in charge.** The director only proposes; the C engine checks
  every request against fixed limits and applies it through normal game code.
- **Always a warning.** Every change is preceded by a fixed, truthful warning.
- **Replayable.** Every accepted change is logged next to the game's random
  seed, so a run can be reproduced. What has been measured is in
  [project status](docs/project-status.md).
- **No secrets.** The director sees what you did, not the dungeon's hidden
  state.
- **Offline by default.** Model-backed directors are optional, explicit and
  never a silent fallback.

## More

- [Director guide](chaos/README.md): packs, the random director, replay,
  restore and the optional model backend.
- [Project status, evidence scope and limitations](docs/project-status.md):
  what is implemented, what was measured, and what is not claimed.
- [The First Haunting](docs/milestone2.md): the echo hound, Dreamland echoes and
  the constrained Lua runtime.
- [Protocol](docs/chaos-protocol.md), including save compatibility and
  migration. **Answer NO to old-save deletion prompts** after upgrading.
- [Whistle and fountain in ordinary play](docs/next-use-ordinary.md).
- [Quality control](docs/quality-control.md) and verification tiers.

## Build notes

`CHAOS=1` is the default build. Without `NYARLATHACK_RUN_DIR`, the game performs
no director input/output. `make -j4 install CHAOS=0` removes director support;
changing the flag rebuilds the affected objects. **Keep each binary paired with
its matching `nhdat` game data.** Saves are not interchangeable across these
builds; stock saves require a stock-compatible build. To run the game without
the launcher: `cd dnethackdir && ./dnethack`.

## Verification

[GitHub Actions quality checks](https://github.com/sflicht/NyarlatHack/actions/workflows/quality.yml)
run lint, both native build modes, offline/native tests, and secret-history
scanning without model credentials. See [quality-control scope](docs/quality-control.md).

Fast protocol/director tests (real-game tests are explicitly skipped):

```sh
python3 -m unittest discover -s tests/chaos -p 'test_*.py' -v
```

For full native acceptance, use the maintained
[fresh reviewed-checkout recipe](docs/quality-control.md#local-equivalents).
Evidence scope and limits are in [project status](docs/project-status.md#verification-evidence).

## Lineage and licence


Based on [dNetHack](https://nethackwiki.com/wiki/DNetHack), using the
[dNAO sources](https://github.com/Chris-plus-alphanumericgibberish/dNAO), with
full upstream history preserved. `upstream` tracks `compat-3.26.0`; NyarlatHack
branched at `a6f0a1c43`. NyarlatHack additions use the NetHack General Public
License, as does the game; retain upstream notices and see `dat/license`.
The original installation README remains available as `README`.
