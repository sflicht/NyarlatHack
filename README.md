# NyarlatHack

A dNetHack fork whose rules can respond to the player's actions.

**Milestone 2: The First Haunting.** The C engine accepts bounded requests from
a separate Python director, **the Crawling Chaos**, and now supports one narrowly
constrained Lua movement encounter. A **whisper** is a validated request; the
engine remains authoritative. GPT-5.6 Luna through ChatGPT OAuth has generated
an exact-source candidate that passed shadow validation and real-game replay.

See [the First Haunting guide](docs/milestone2.md) for the playable echo hound,
cosmetic Dreamland echoes, subscription connection, evidence and limitations.
This is not general source rewriting or an unrestricted scripting system.

## Tier 2 foundation (Milestone 1)

- [x] **Event stream:** newline-delimited JavaScript Object Notation (JSON)
  observations for eating, reading, zapping, applying, prayer, kills, level
  transitions, sleep, Sanity, Insight and final termination. Actions are generic
  attempts, not claims of success or disclosures of unidentified items. Sanity
  and Insight changes are observed at turn-loop boundaries. The review-foundation
  extension adds player-known status vitals and explicit prayer cancellation;
  model context still excludes hidden identities and arbitrary detail strings.
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
  Ambient uses a separate prototype: three lifetime deliveries, each existing
  message once, at least 50 native moves apart, no mechanical debit. It does not
  promise full-run presence. Current state/save2, event3/observation4 and journal
  policy2 require a new game on the new build; request grammar remains v1.
  **Answer NO to old-save deletion prompts** and retain the matching old
  binary/data/save. See [policy, migration and pending native gates](docs/chaos-protocol.md#cosmetic-pacing-prototype-and-migration).
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

The generic model connection retains its local fake HTTP (Hypertext Transfer
Protocol) tests. The separate pinned ChatGPT OAuth route has now been exercised
with real GPT-5.6 Luna calls. Long-run balance and adversarial public-server
hosting remain unvalidated.

## Phase-one observation foundation

An optional version-4 event extension records selected whistle actions and
confirmed fountain drinks, with delivered public notices and bounded offline
episode summaries. Current ordinary events are version3; the whisper request API
remains version1. Historical v1/v2 logs remain readable but not current-replay
inputs. The ordinary director still rejects observation logs;
use the [offline observation guide](chaos/README.md#offline-selected-action-observations)
or the separate opt-in pilot below. The foundation itself adds no mechanic,
fountain remapping, companion behavior, Lua or budget change.

### History-conditioned whisper pilot

The new explicit `chaos history` command connects a completed delivered fountain
refresh to the existing hunger rule: double ordinary food consumption for 10 or
20 turns. Prior accepted hunger suppresses another proposal, even after expiry.
There is no new native mechanic, larger budget or default launcher change.

Controlled native development runs measured both an offline-selected effect and
a genuine GPT-5.6 Luna-selected effect, with expiry, empty controls and exact
replay. See the [pilot guide and evidence](docs/history-conditioned-whispers.md)
for commands, distinct acceptance scopes and limitations. This is one bounded
consequential use of history—not completion of the broader vision in #26 or
closure of #21, #22 or #27.

## Build

On Debian/Ubuntu, install the compiler and build dependencies:

```sh
sudo apt-get install bison flex build-essential libncursesw5-dev pkg-config liblua5.4-dev
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
python3 -m chaos play
python3 -m chaos play --ordinary
```

`--ordinary` starts a human Bard (frozen test identity, no wizard mode). Other
roles still work without that flag.

The initial level-entry safe point admits the ambient request and displays its
warning and message. The launcher prints and preserves a private run directory,
supervises a separate offline director, and leaves play running if that director
finishes early. Readiness confirms publication, **not acceptance**; the game
records acceptance in `events.jsonl`. Use `--backend random --seed 7` for the
random director. No model or credentials are needed. Explicit restore and the
manual two-terminal alternative are documented in the director guide.

See [the director guide](chaos/README.md) for the ward/hunger demonstration,
random director, model configuration, replay and operational limits.

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
The configured native suite and selected-command turn-loop gate are independently
accepted locally at `8f317763a3560bd774d0b61e134e7028a744412a`, under the approved
provenance-validated dump contract. Literal strict cross-build comparison remains
**FAILED**; the successful suite and failed reporting wrapper are separate results.
Hosted continuous integration passed for foundation PR #28 and its merged main
revision; whole-phase sign-off is not implied. The new pilot has separate
acceptance evidence. See the
[bounded evidence ledger](docs/haunting-observations-evidence.md).

The terminal harness is Linux-specific and uses a test-only preload library.
It records actual input bytes, terminal output, event logs, score logs and
binary/data hashes in temporary artifact directories. Neither the test clock
nor the test fixtures are enabled in the normal game. See
[validation evidence and limitations](docs/milestone1-validation.md) and
[the exact protocol](docs/chaos-protocol.md).

## The First Haunting: constrained runtime and Dreamlands

```sh
RUN=$(mktemp -d)
python3 -m chaos haunt --run-dir "$RUN" --source chaos/packs/luna-footsteps.lua
(cd dnethackdir && NYARLATHACK_RUN_DIR="$RUN" ./dnethack -D -u wizard)
```

In the terminal window port, choose a human Wizard with no inheritance, set
Sanity to 60 using `#setsanity`, and backtrack across open floor. An eligible
candidate runs first in a forked, headless, system-call-restricted copy of the
C simulation. If its targeted trial passes, a warning precedes an echo hound
whose movement follows delayed footsteps. Use Ctrl-P to see a cosmetic dream
fragment in message history. No model call is made by installing the saved pack.

The verified surface is one movement handler, one candidate per game, and
targeted shadow trials—not the complete normal turn loop or proof of safety for
every dungeon. Echo insertion changes history only, not gameplay or unsolicited
prompts. Continuous script generation, all-window-port rendering, script-bearing
bones, public hosting and between-lives C rewriting remain deferred.
See [Milestone 2](docs/milestone2.md) and the original [Tier 3 notes](docs/tier3-notes.md).

## Lineage and licence

Based on [dNetHack](https://nethackwiki.com/wiki/DNetHack), using the
[dNAO sources](https://github.com/Chris-plus-alphanumericgibberish/dNAO), with
full upstream history preserved. `upstream` tracks `compat-3.26.0`; NyarlatHack
branched at `a6f0a1c43`. NyarlatHack additions use the NetHack General Public
License, as does the game; retain upstream notices and see `dat/license`.
The original installation README remains available as `README`.
