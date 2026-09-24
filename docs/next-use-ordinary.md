# Next-use ordinary path

This is host-built selection, not authored composition and not a claim that a player has recognized a cause.

## Earlier publication-only evidence

One ordinary nonwizard Bard, fixed test clock, no wizard flag and no seed search, applied the starting tin whistle. `play --ordinary --next-use` published one envelope from the origin schedule. The retained selection was `whistle_attention`, not quiet. The next prayer safe point admitted it once and showed the engine warning. Fountain did not occur in that start. A separate restore of that save kept one receipt; that restore is not in the automated test because the quit prompt was racy. Do not treat this as authored composition or as a recurring haunting.

## Native effect and replay acceptance

The expanded `test_next_use_ordinary.py` now carries that same ordinary Bard
path through an actual whistle-attention effect. W means whistle attention;
F means fountain refresh. W naturally qualifies here; F does not, and no
fountain or companion is injected to manufacture a second family.

The engine uses normal compiled game objects, including `rnd.o`, `dogmove.o`
and `unixmain.o`. A test-only observer wraps the real startup/observation hooks,
reads state after the real hooks return, and never writes game state or draws
random values. Its private output is inspected only after all public input
policies finish. No wizard flag, bootstrap mutation, hidden-state input
selection, `ordinary_route` import or execution, provider credentials or model
call is involved. The original fixed clock/entropy shim remains in use; this
is not arbitrary saved-random-stream replay or a measured ordinary success rate.

The declared sequence is public inventory inspection, the starting tin whistle,
one confirmed prayer, a second whistle, and a native save/process exit. The
saved programme is then restored for a fixed look/pickup and movement policy.
A real displaced, publicly delivered companion manifestation must appear;
warning-only execution fails the positive oracle. The programme terminates,
is saved again, and remains consumed after another actual restore.

A second continuation copies the **same admitted native save and run prefix**,
then replays every recorded input byte, including automatic prompt replies,
through the existing launcher. It makes no new choice: both restore sessions
report `already_published` before history selection. Exact source/envelope,
one admission/debit, engine events, acknowledged journal, read-only native
observations and final native log agree. Independent source/binding digests
and journal decoding remain required. The raw terminal files are retained:
only their two launcher announcements differ, because each names its own
private directory; every intervening byte must agree. No historical comparator
or evidence file is changed to obtain this result.

The measured baseline has 48 replayed suffix input chunks and 41 acknowledged
transitions, with one delivered W manifestation at monster-clock tick 9.
`ordinary-result.json` records qualification/publication and effect milestones
in wall-clock seconds from the start of the positive test, including its prefix
and continuations. Automated wall time is not human pacing. It also retains native saves, inputs, journals, receipts, source identity
and normal-object hashes under the printed `ORDINARY_NEXT_USE_ARTIFACTS` path.

Controls are part of the same test invocation:

- The previously unqualified no-look/no-pickup public policy uses the same
  admitted save and fixed movement but fails the positive witness oracle. The
  pickup changes time and random-number evolution too; this does not isolate
  pickup causality. Older negative trials remain valid evidence, not discarded
  seeds or repaired goldens.
- A labelled synthetic copy of the actual qualifying public history removes
  the whistle observations. Remaining observed state and director seed 0 stay
  fixed: the W menu disappears. The original history permits both quiet and
  attention. These counterfactual records are never fed to the native game.
- The test terminates only its own supervised director after normal game
  startup. With either no candidate or an invalid candidate, ordinary play
  continues to a normal exit without admission, spend or a warning.

Run the production launcher with one command:

```sh
python3 -m chaos play --ordinary --next-use
```

Run the bounded development demonstration and its controls from a built checkout:

```sh
make -j2 install CHAOS=1
NYARLATHACK_GAME_TESTS=1 python3 -B -m unittest discover -s tests/chaos -p test_next_use_ordinary.py -v
```

A failed or unqualified run is retained and fails its oracle; the driver does
not hunt a different seed or rescue the game. Existing limits and the choice
of host-built rather than authored source are unchanged. This establishes a
bounded ordinary path, not player causal recognition, broad continuity, a
recurring haunting or full-run balance. Those remain separate from #66.

## What is connected

`play --next-use` publishes at most one envelope when a ready origin schedule matches the public menu. A persistent `RandomHistoryBackend` uses the declared director seed (`--seed`, default 0), not a new seed on each poll. Quiet and abstention are valid decisions; seed 0 in the retained whistle example selects `whistle_attention`. It sets observations and admission on the game process only. It does not call a model. Default `play` does not do this.

The schedule file is `next_use-schedule.jsonl`. `move` is monstermoves, not the observation turn. The consumer matches exact family/root/notice/end references, takes the latest public qualifying origin per family (matching the engine's owned slots), then chooses the earliest completed matching family. Exact references come from the checked history's existing 32-root chronology, **not** the sampled episode summary. A newer qualifying notice immediately supersedes the previous origin; its family is unavailable until that same origin completes. Other families remain independently eligible. A nonqualifying later notice does not replace an eligible origin. Unrelated records do not prevent selection; duplicate or conflicting identities fail. The safe index and program ID come from the selected completion's checked history. A missed safe point is not retimed, and a decision is not retried or substituted.

Both inputs use the existing secure incremental reader: schedule limits are 16 KiB, 32 records and 256 bytes per line, including newline; history retains its 16 MiB/50,000-record bounds. An incomplete bounded suffix may complete on a later poll. Diagnostics distinguish `pending`, `no_eligible_origin`, `abstained`, `envelope_published_not_admitted`, and `already_published`; malformed or unsafe inputs raise through the launcher's failure path. The launcher reuses its held mailbox lock and never replaces an existing envelope.

The engine writer uses a nonblocking file lock, private regular-file checks, bounded reads/appends, short-I/O handling, and file/directory synchronization. A failed append attempts to restore the old prefix. This is **not** a crash-atomic transaction: close or rollback failure can leave ambiguous bytes. Any writer failure disables further next-use scheduling/admission for that engine process without disabling observation logging. Publication is not admission: the production boundary still independently checks the engine-owned origin, run, level and native clock.

## Schedule/transport regression scope (#143)

`test_next_use_schedule_robustness.py` reuses `episode_scopes.c` to generate real engine history and schedule bytes for two W origins and a W/F pair before polling. It passes the selected, unchanged envelope into `next_use_safe.c`'s production `on_safe` wrapper, checking exact source bytes, one admission, one charge and one telegraph callback, plus invalid origin/clock/run/level controls. Partial real schedule bytes complete once without a duplicate publication or charge. These helpers stub game-host state and delivery; they do **not** establish native gameplay consequences, delivery, consumption/expiry or replay required by #66.

Run from the repository root (generated native headers and Lua 5.4 development files are prerequisites):

```sh
python3 -m unittest discover -s tests/chaos -p 'test_next_use_schedule*.py' -v
```

The multi-record regression also checks that the latest W root, not its evicted predecessor, is selected. The failed-writer regression was observed failing before the engine's ignored writer-return value was fixed: a FIFO schedule still exposed a ready owned origin. It now checks that observations remain complete but no owned origin is bound. Complete required CI and independent review at the proposed merge head remain publication gates; these focused tests are not a substitute.
