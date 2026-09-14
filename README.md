# NyarlatHack

*d² ≠ 0.*

NyarlatHack is a fork of [dNetHack](https://nethackwiki.com/wiki/DNetHack)
(the [dNAO](https://github.com/Chris-plus-alphanumericgibberish/dNAO) sources,
NetHack 3.4.3 lineage) in which a language model — **the Crawling Chaos** —
watches what the player does and alters the dungeon's actual rules in response.
Not the flavour text: the spawn tables, the monster behaviour, the reliability
of your wards, the meaning of your spoilers.

dNetHack already has a Sanity stat, a Madman role, Binder spirits, shoggoths
and priests of Ghaunadaur. It already whispers that the rules you learned are
lying to you. NyarlatHack makes that literally true, and makes *your* choices
the reason.

## Design in one paragraph

The C engine stays deterministic and stays in charge. It emits a structured
event stream (what you killed, ate, read, prayed for, where your Sanity went).
A sidecar process — the Crawling Chaos — reads that stream, consults a language
model, and returns **whispers**: mutations drawn from a finite, validated,
engine-defined action space. The engine applies whispers only at safe points
(level change, prayer, sleep, Sanity thresholds), logs every one alongside the
RNG seed so any run can be replayed exactly, and never lets the model touch
memory, code, or state directly. The model *chooses*; the engine *executes*.

## Fairness is a mechanic, not an apology

Roguelikes tolerate cruelty but not arbitrariness. Three rules keep this a game:

1. **Every whisper telegraphs.** A message, an engraving, a dream, a change in
   the "You hear…" ambience — something fires before the effect does. The
   player can learn *that* the world bends and *where*.
2. **Cruelty has a budget, and the budget is your Sanity.** At full Sanity the
   Chaos can barely nudge the dungeon. As Sanity falls its latitude grows. Only
   your own madness makes the world unreliable.
3. **Determinism survives.** Seed + whisper log = the same game. Bugs are
   reproducible; runs are shareable; the director can be swapped for a replay.

## Roadmap

### Milestone 1 — Tier 2: the director over a bounded mutation API  ← *current*

The Crawling Chaos picks from a menu the engine already knows how to honour.

- [ ] **Event stream.** Engine appends JSON-lines events to a per-game file at
      existing seams (kill, eat, read/zap/apply, pray, level enter/leave,
      Sanity/Insight change, death). Zero behaviour change; the game plays
      identically with the stream on.
- [ ] **Mutation API in C.** A registry of named mutations with typed
      parameters and bounds, e.g. `spawn_bias(class, weight)`,
      `ward_efficacy(ward, pct)`, `intrinsic_duration(intr, scale)`,
      `ambient(msg_id)`, `disposition(shk|priest, delta)`,
      `levelgen_param(key, value)`. Each is validated on load and applied through
      the engine's existing code paths — never by poking structs from outside.
- [ ] **Mailbox + safe points.** Engine polls a whisper file at level change,
      prayer, sleep, and Sanity thresholds; applies valid whispers; logs them.
- [ ] **Sanity budget.** Each mutation carries a cruelty cost; the budget the
      director may spend is a function of lost Sanity.
- [ ] **Telegraph requirement.** A whisper without a registered telegraph is
      rejected at load.
- [ ] **The Crawling Chaos (sidecar).** Python process: tails the event stream,
      builds a compact game summary, prompts a model with the mutation schema
      and the budget, validates the response against the schema, writes the
      whisper file. Pluggable model backend; a `replay` backend that just
      re-emits a logged whisper file; a `random` backend for testing without a
      model.
- [ ] **Replay + regression.** `seed + whispers.jsonl` reproduces a run
      headlessly. A small bot-driven smoke test proves the engine with the
      stream and mailbox on behaves identically to upstream when no whispers
      arrive.
- [ ] **A playable build** with a handful of hand-written whisper packs
      (no model needed) so the mechanics can be felt before the model is wired
      in.

### Milestone 2 — Tier 3 (constrained runtime): the Dreamlands

Later. The director stops picking from a menu and starts *composing*: small
sandboxed scripts (Lua is the leading candidate; NetHack 3.7's `nhlua.c` is
the crib sheet) registered against ~10 engine hooks — monster decision, attack
resolution, object use, level enter, prayer, Sanity change. Whitelisted
getters/setters only; instruction and memory caps; game RNG in place of
`math.random`; any script error means the mutation "fails to manifest" and
reality shudders but holds. Before a script goes live it runs in **the
Dreamlands** — a forked headless copy of the game — where a bot plays a few
hundred turns and property checks (stairs reachable, no instant death, damage
per turn under cap, script terminates) accept or reject it. Not before
Milestone 1 ships.

### Explicitly out of scope for now

- Rewriting C source between lives (the "rule drift across deaths" idea).
- Whispers riding along in bones files. Delicious; opt-in; later.
- Any public-server deployment.

## Building

Same as dNetHack. On Debian/Ubuntu:

```
apt install bison flex build-essential libncursesw5-dev pkg-config
make install          # builds into ./dnethackdir
cd dnethackdir && ./dnethack
```

`./dnethack -D -u wizard` for wizard mode. Options live in `~/.dnethackrc`.
The NyarlatHack sidecar will live under `chaos/` and have its own README.

## Lineage and licence

Upstream is tracked as the `upstream` remote (`compat-3.26.0` branch);
NyarlatHack's `main` branches from upstream commit `a6f0a1c43`. Everything
upstream is © the dNetHack and NetHack authors under the NetHack General Public
License (see `dat/license`); NyarlatHack additions are released under the same
licence.

The name: Nyarlathotep is the Crawling Chaos — the one Outer God who takes a
thousand forms, walks among mortals, and *speaks*.
