# NyarlatHack

A dNetHack fork whose rules can respond to the player's actions.

**Milestone 1: playable Tier 2 prototype.** The C engine now accepts bounded rule
changes from a separate Python director, **the Crawling Chaos**. A **whisper**
is one validated request. The director chooses; the engine decides whether it
is eligible and executes it. Generated scripts and source rewriting are absent.

## What works now

- [x] **Event stream:** newline-delimited JavaScript Object Notation (JSON)
  observations for eating, reading, zapping, applying, prayer, kills, level
  transitions, sleep, Sanity, Insight and final termination. Actions are generic
  attempts, not claims of success or disclosures of unidentified items. Sanity
  and Insight changes are observed at turn-loop boundaries.
- [x] **Bounded mutation application programming interface (API):**
  `ward_efficacy` halves completed ward counts in monster fear checks;
  `hunger_rate` doubles ordinary food consumption; `ambient` displays a fixed
  message. These are the initial supported registry, not every example in the
  original proposal. Spawn weighting and other categories are not implemented.
- [x] **Mailbox and safe points:** one bounded request at level entry, confirmed
  prayer, pre-sleep, or observed Sanity thresholds. No waiting for a model.
- [x] **Engine-owned cruelty budget:** costs depend on mutation type; capacity
  grows as Sanity falls. The current conservative prototype uses a **lifetime**
  spending allowance of at most 12 points. Expiry does not refund spending.
  Consequently the director can run out of interventions early; this is not
  tuned game balance.
- [x] **Telegraphs:** fixed warnings precede admitted effects. Invalid requests
  fail closed; no model-generated terminal text or executable commands.
- [x] **Python director:** hand-authored packs, seeded random proposals,
  acknowledgement-backed schedule replay, and an opt-in OpenAI-compatible model
  connection. No credentials or network are needed for the offline modes.
- [x] **Regression and bounded replay tests:** actual terminal sessions compare
  stock, inactive and empty-mailbox play; an accepted hunger schedule replays
  identically under explicitly controlled clock, entropy, options and inputs.
  This is **not** a claim that arbitrary ordinary play can be reproduced from a
  starting seed alone.
- [x] **Playable build:** built with director support on and off; actual
  save/restore preserves active and pending whispers and rejects incompatible
  save layouts. Linked-engine tests measure both real rule changes and expiry.

The model connection has been tested with a **local fake HTTP (Hypertext
Transfer Protocol) server**, not a live language model. Live-model gameplay,
long-run balance and adversarial public-server hosting remain unvalidated.

## Build

On Debian/Ubuntu, install the compiler and build dependencies:

```sh
sudo apt-get install bison flex build-essential libncursesw5-dev pkg-config
make -j4 install CHAOS=1
cd dnethackdir
./dnethack
```

`CHAOS=1` is the default build. Without `NYARLATHACK_RUN_DIR`, the game performs
no director input/output. `make -j4 install CHAOS=0` removes director support;
changing the flag rebuilds the affected objects. **Keep each binary paired with
its matching `nhdat` game data.** Saves are not interchangeable across these
builds; stock saves require a stock-compatible build.

## Try one whisper, with no model

From the repository root:

```sh
RUN=$(mktemp -d)
python3 -m chaos pack ambient --run-dir "$RUN" --install-only
(cd dnethackdir && NYARLATHACK_RUN_DIR="$RUN" ./dnethack)
```

The initial level-entry safe point admits the ambient request and displays its
warning and message. `--install-only` confirms publication, **not acceptance**;
the game records acceptance in the run directory's `events.jsonl`.

See [the director guide](chaos/README.md) for the ward/hunger demonstration,
random director, model configuration, replay and operational limits.

## Verification

Fast protocol/director tests (real-game tests are explicitly skipped):

```sh
python3 -m unittest discover -s tests/chaos -p 'test_*.py' -v
```

Full acceptance, after building `CHAOS=1`; supply an unmodified stock build
installation containing `dnethack`, `nhdat`, and `license`:

```sh
NYARLATHACK_STOCK_DIR=/absolute/path/to/stock-install \
NYARLATHACK_GAME_TESTS=1 \
python3 -m unittest discover -s tests/chaos -p 'test_*.py' -v
```

The terminal harness is Linux-specific and uses a test-only preload library.
It records actual input bytes, terminal output, event logs, score logs and
binary/data hashes in temporary artifact directories. Neither the test clock
nor the test fixtures are enabled in the normal game. See
[validation evidence and limitations](docs/milestone1-validation.md) and
[the exact protocol](docs/chaos-protocol.md).

## Deferred: constrained runtime scripting and the Dreamlands

Tier 3 remains unimplemented. The proposed **Dreamlands** would test candidate
scripts in a separate game simulation before admission. Such bounded testing
would provide evidence, not prove universal safety or fairness.

**Dreamland echoes are an explicit future design requirement:** actual shadow
activity, including rejected timelines, should sometimes produce purely
cosmetic recollections in the main game. Those echoes must not change turns,
randomness, player state, budgets or prompts, nor reveal hidden information.
They are separate from mandatory mutation warnings. See
[Tier 3 notes](docs/tier3-notes.md).

No script-bearing bones files, public-server deployment or between-lives C
rewriting is included.

## Lineage and licence

Based on [dNetHack](https://nethackwiki.com/wiki/DNetHack), using the
[dNAO sources](https://github.com/Chris-plus-alphanumericgibberish/dNAO), with
full upstream history preserved. `upstream` tracks `compat-3.26.0`; NyarlatHack
branched at `a6f0a1c43`. NyarlatHack additions use the NetHack General Public
License, as does the game; retain upstream notices and see `dat/license`.
The original installation README remains available as `README`.
