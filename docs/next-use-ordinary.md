# Next-use ordinary path

This is host-built selection, not authored composition and not a claim that a player has recognized a cause.

## What was demonstrated

One ordinary nonwizard Bard, fixed test clock, no wizard flag and no seed search, applied the starting tin whistle. `play --ordinary --next-use` published one envelope from the origin schedule. The retained selection was `whistle_attention`, not quiet. The next prayer safe point admitted it once and showed the engine warning. Fountain did not occur in that start. A separate restore of that save kept one receipt; that restore is not in the automated test because the quit prompt was racy. Do not treat this as authored composition or as a recurring haunting.

## What is connected

`play --next-use` publishes at most one envelope when a ready origin schedule matches the public menu. A persistent `RandomHistoryBackend` uses the declared director seed (`--seed`, default 0), not a new seed on each poll. Quiet and abstention are valid decisions; seed 0 in the retained whistle example selects `whistle_attention`. It sets observations and admission on the game process only. It does not call a model. Default `play` does not do this.

The schedule file is `next_use-schedule.jsonl`. `move` is monstermoves, not the observation turn. The consumer matches exact family/root/notice/end references, takes the latest public qualifying origin per family (matching the engine's owned slots), then chooses the earliest completed matching family. Unrelated records do not prevent selection; duplicate or conflicting identities fail. The safe index and program ID come from the selected completion's checked history. A missed safe point is not retimed, and a decision is not retried or substituted.

Both inputs use the existing secure incremental reader: schedule limits are 16 KiB, 32 records and 256 bytes per line, including newline; history retains its 16 MiB/50,000-record bounds. An incomplete bounded suffix may complete on a later poll. Diagnostics distinguish `pending`, `no_eligible_origin`, `abstained`, `envelope_published_not_admitted`, and `already_published`; malformed or unsafe inputs raise through the launcher's failure path. The launcher reuses its held mailbox lock and never replaces an existing envelope.

The engine writer uses a nonblocking file lock, private regular-file checks, bounded reads/appends, short-I/O handling, and file/directory synchronization. A failed append attempts to restore the old prefix. This is **not** a crash-atomic transaction: close or rollback failure can leave ambiguous bytes. Any writer failure disables further next-use scheduling/admission for that engine process without disabling observation logging. Publication is not admission: the production boundary still independently checks the engine-owned origin, run, level and native clock.

## Schedule/transport regression scope (#143)

`test_next_use_schedule_robustness.py` reuses `episode_scopes.c` to generate real engine history and schedule bytes for two W origins and a W/F pair before polling. It passes the selected, unchanged envelope into `next_use_safe.c`'s production `on_safe` wrapper, checking exact source bytes, one admission, one charge and one telegraph callback, plus invalid origin/clock/run/level controls. Partial real schedule bytes complete once without a duplicate publication or charge. These helpers stub game-host state and delivery; they do **not** establish native gameplay consequences, delivery, consumption/expiry or replay required by #66.

Run from the repository root (generated native headers and Lua 5.4 development files are prerequisites):

```sh
python3 -m unittest discover -s tests/chaos -p 'test_next_use_schedule*.py' -v
```

The multi-record regression also checks that the latest W root, not its evicted predecessor, is selected. The failed-writer regression was observed failing before the engine's ignored writer-return value was fixed: a FIFO schedule still exposed a ready owned origin. It now checks that observations remain complete but no owned origin is bound. Complete required CI and independent review at the proposed merge head remain publication gates; these focused tests are not a substitute.
