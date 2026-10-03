# Replay, PTY play and ordinary-play experiments

Covers `chaos play`, the `tests/chaos/gameplay_support.py` `Game` PTY driver,
controlled replay and ordinary (nonwizard) experiments. Deeper topic notes:
`native-evidence/pty-acceptance.md`, `native-evidence/save-restore.md`.

## Entropy and clock

- Controlled replay depends on the test-only clock/entropy shim
  (`tests/chaos/replay_clock.c`), inputs, options, and the exact binary/data, not
  a seed alone. `check_reseed()` (`src/rnd.c`) reads `/dev/urandom` for new seeds
  and reseed intervals; `src/hacklib.c` uses time for seeding and moon/night.
- Use the shim only as test instrumentation, equally for stock and fork. Never
  install it for normal play or feed private replay manifests to a model.
- Native saves do not contain RNG state. Record the actual clock/entropy/
  restart policy; a fixture with per-effect resets is not ordinary replay.
- Inherited external inputs (for example `MAIL`) can break replay even under
  fixed clock/entropy. Use an owned empty private mailbox (0700 dir, 0600 file).

## Driving the game

- `python3 -m chaos play` (not `launch`). `--ordinary` starts a nonwizard Bard.
  Inspect `--help` before composing commands. Offline play doesn't author new
  curios; authoring is a separately authorized model operation.
- A fresh `--ordinary` start refuses while its save exists (fixed character
  name); resume with `--reuse-run-dir` or move the save aside. Every start opens
  the inheritance menu ("Which artifact did you inherit?"): answer `n`.
- Set `Game(launcher_fresh=False)` explicitly before reuse/restore; never infer
  the mode from path existence.
- Next-use safe points fire only at level enter, pray, sleep and the Sanity
  threshold, not every turn. `#pray` is an ordinary way to reach one.
- Handle inheritance, `--More--`, wizard save-retention and incompatible-save
  prompts explicitly. Never send guessed keystrokes that become game actions.
  Drain `--More--` and wait for the acknowledgement before `#quit`, or it is
  swallowed. Confirm exit status and the death/quit event.
- Wizard fountain drinks can ask `Dry up fountain? [yn] (n)`: answer it
  explicitly with the native default and record it as a prompt-only response.
- `Game.more` may return only the last page. Read full per-action raw slices;
  normalize whitespace only for prose matching (warnings wrap), keep raw bytes.
- A read buffer contains already-answered questions. Classify the pending prompt
  from the current unanswered tail, not the whole buffer. Regress real
  completed-response bytes before changing the detector.
- Drive routes from rendered screen output only (a terminal emulator such as
  pyte can reconstruct it); hidden map/object coordinates can't back an
  ordinary-discovery claim.
- Read dNetHack's current `mapglyph.c` and tty renderer before interpreting pet
  highlights: `hilite_pet` uses a blue background, not vanilla-style inverse
  video. Preserve SGR backgrounds across split reads and clear them on erase or
  repaint; never infer tameness from a dog/kitten letter alone. Put pet-aware
  decisions in a separately named sensitivity policy, explicitly configure and
  record its public display options, and leave the gate policy unchanged.

## Ordinary replay procedure

1. Before launch, freeze a bounded public-input policy, clock/entropy policy,
   attempt cap, failure conditions, controls and source/build/helper hashes.
   Keep unqualified/negative runs; no seed hunting, no private-diagnostic rescue.
2. Record natural qualifying action, episode, host-built selection, envelope,
   admission/debit, readable warning, actual effect/delivery, consumption, and
   real save → process exit → restore.
3. Replay from the same admitted native save and exact prefix. Copy into owned
   private files (distinct inodes, originals unchanged in bytes and mode); each
   continuation restores its own newly produced save.
4. Guard every input byte before sending, including paging and automatic prompt
   replies. Verify no new selection/admission/debit and no resurrection.
   Replayed prefixes must stay byte-identical before a repaired exchange resumes.
5. Verify source/binding hashes and acknowledged journal integrity alongside
   physical outcomes. Expected effects are comparison targets, not instructions.
6. Preserve raw terminal streams. If only known launcher directory announcements
   differ, enumerate those spans and prove the rest agrees; report raw inequality.
   Never add a broad normalizer or repair a historical comparator.
7. Include loss/negative controls: missing effect, lost witness, dropped programme,
   absent/invalid candidate, supervised director failure. A test terminates only
   its own identified child.
8. Label synthetic history-removal experiments; never feed fabricated history into
   a positive native run. Automated wall time is not human pacing.

## Comparing dumplogs

Stock-baseline and current-build dumplogs differ in the
`Playing dNetHack ..., last build ...` banner (`src/end.c`); mask that one line
(`tests/chaos/test_gameplay.py` does). Same-binary inactive and empty-mailbox runs
must match byte for byte. Other allowed differences only via
`docs/turnloop-dump-comparison-contract.md`, with the strict result preserved.

## Diagnosing a blocked ordinary run

Start from the saved checkpoint and exact recorded suffix. Read-only
instrumentation must not write state, draw randomness or steer inputs. Match the
original trace before blaming a predicate. Failed/unqualified procedures must
exit nonzero; script exit, native session exit and effect acceptance are
separate.
