# #178: the funnel's later stages checked on real delivering games

Tier B measurement. It checks that `tests/chaos/sweep_funnel.py` counts the
later funnel stages (trigger, native effect, delivered) and `first_felt`
correctly on real games, not only on synthetic rows.

## Terms

- **Next-use program:** a one-shot Lua program the director publishes. The
  engine admits it at a safe point and runs it on the player's next matching
  action. W is the whistle family and F is the fountain family.
- **Trigger:** the engine's intent row (private record kind 3). The program's
  callback ran on a qualifying action.
- **Native effect:** an effect row (kind 4) whose outcome is `W_ARMED` (1) or
  `F_REMAPPED` (12). The engine armed the change.
- **Delivered:** an effect row whose outcome is `W_WITNESSED` (3) or
  `F_REMAPPED` (12). The player saw the consequence.
- **first_felt:** the turn and kind of the first on-screen consequence: a
  visible hound step, the whistle-attention notice, or a fountain remap.

## Games checked

Both games come from `docs/measurements/seed-sweep-v2-179/baseline-v2-seeds-1-100.json`.

| Start | Seed | Why this game |
|---|---:|---|
| bard | 40 | A next-use W program was delivered (whistle attention seen at turn 200). |
| bard-default-path | 21 | The default path: an early echo hound (first felt at turn 7), then a delivered W program. |

In the v2 report, 29 of 400 games delivered (bard 14, bard-default-path 10,
bard-inherited 5), all through W. No F program delivered (0 games with an
`F_REMAPPED` row), so there is no real F game to check. The F branch keeps only its
synthetic unit tests.

## Replay

Both seeds were replayed under `hermes-heavy`, at the report's revision
`003dbcb66930a443ad9466c9985194fbb2bc537b`, with the report's own command:

```
python3 scripts/seed_sweep.py --seeds <n>-<n> --policy baseline-v2 --starts <start> --out <stem>
```

The build had 0 warnings. `nhdat` matched the report's hash
(`004084722d17…`). The per-game entry of each replay is identical to the
committed entry: the whole `games[]` object, compared with `==`.

The `dnethack` binary hash differs from the report's (`d76f355a…` against
`29c43b8e…`). `util/makedefs.c` writes the wall-clock `BUILD_DATE` and
`BUILD_TIME` into `date.h`, so every build of the same revision hashes
differently. The `nhdat` hash and every per-game result match.

## What was compared by hand

For each game, the raw files were read directly: the decoded
`next_use-journal.jsonl` (structurally complete), `events.jsonl`,
`next_use-receipt.jsonl` and `next_use-envelope.json`. The analyser's
counts were then compared with them.

| Check | bard 40 | bard-default-path 21 |
|---|---|---|
| Admission row (kind 2) and receipt kind 2 | 1 at move 118 | 1 at move 320 |
| Trigger (intent rows, kind 3) | 1 at move 195 | 1 at move 339 |
| Effect outcomes, in order | 1 armed (195), 3 witnessed (200), 4 ended after witness (205) | 1 (339), 3 (344), 4 (349) |
| Native effect (outcome 1 or 12) | 1 | 1 |
| Delivered (outcome 3 or 12) | 1 | 1 |
| Public `whistle_attention` notice | turn 200 | turn 344 |
| Witnessed row turn = notice turn | yes | yes |
| Termination (kind 5) | reason 1, completed | reason 1, completed |
| Visible hound steps (`haunt_step`) | 0 | 2 (turns 7 and 8) |
| first_felt | turn 200, next_use_W | turn 7, hound |
| Analyser agrees | yes | yes |

The analyser's outcome codes were also checked against
`enum chaos_next_use_effect_outcome` in `include/chaos_next_use_runtime.h`.
They match.

## Result

The counts are right, so the committed reports are unaffected. The two
games are kept as a regression fixture:

- `tests/chaos/funnel_fixtures/v2-bard-40.json`
- `tests/chaos/funnel_fixtures/v2-bard-default-path-21.json`
- `tests/chaos/test_funnel_real_games.py`

Each fixture keeps only the events the analyser reads: the session,
safe-point, haunting and hound-step events, the whistle, fountain and
whistle-attention observations, and the last event. It also keeps the
schedule, envelope, receipts, director lines and whispers. The journal's
records are chained by hash, so a trimmed journal would not decode. The
fixture therefore keeps the private records decoded from every journal
record, together with the source journal's sha256.

The test asserts the whole per-game entry of the committed report, less the
sweep-added Dlvl. It also re-derives trigger, native effect and delivered
from the raw private rows, checks that the witnessed row falls on the
notice turn, and pins the outcome codes to the engine enum. Four deliberate
analyser bugs were each caught by at least one failing test:

- delivered code 3 changed to 4;
- first_felt off by one turn;
- trigger counted from effect rows;
- a witnessed row counted as a native effect.

## Limits

- Two games, both W. The F path is still checked only synthetically.
- The fixture replaces `read_journal` with its decoded records, so journal
  decoding is not exercised here. It has its own tests.
- Raw replay data: `~/.hermes/reports/nyarlathack-178/`, with the replay
  reports `replay-bard-40.json` and `replay-bard-default-path-21.json` and
  the replay script `replay.sh`.
