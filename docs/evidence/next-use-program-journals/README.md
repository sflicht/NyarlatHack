# Per-program journals and replay (M2 PR 3)

Verification tier: **Tier A**. The temporary effective-cap-one guard is removed
only together with ordinal journal paths, closed-history save/restore, and resume
validation. The director still publishes **only program 1**. No scheduling,
pacing, new consequence, or RNG operation is introduced here.

## Contract

Program 1 retains `next_use-journal.jsonl`; programs 2 and 3 use
`next_use-journal.2.jsonl` and `next_use-journal.3.jsonl`. Each file has its own
header, source bytes, cursor, hash chain, bound, termination, and COMPLETE footer.
Headers and admission/rejection receipts carry the program ordinal; envelope IDs
may repeat. The live runtime rotates only after terminal mechanics **and** a
durably closed, acknowledged journal. Fresh origins and the cap remain mandatory.

The outer next-use native save carrier changes from NUS1 to NUS2. It stores the
current ordinal and at most two closed snapshot values before the current
program. This is history, not additional runnable slots. State v5 still owns the
attempt count and rejected attempts; the inner v6 snapshot codec is unchanged.
The old carrier is refused and the save is kept, never migrated. Restore stages
all values, then validates earlier closed chains before resuming the current
prefix. A prior-journal failure blocks admission even after a rejected latest
attempt with no runtime. Existing incomplete-capture behavior remains fail-closed.

## Executed oracles

- `test_next_use_safe.py`: three natural admissions, repeated envelope ID 1,
  active/same-origin NOT_OPEN, cap NOT_OPEN, independent chains and receipts.
  Native VM semantic replay of each program matches its own terminal codec.
  Restore occurs with an active program 2 and between programs / at the cap.
- `test_next_use_journal.py::test_linked_engine_admits_second_program_without_rng`:
  real linked fountain engine followed by a naturally admitted second program;
  no count injection, no additional native RNG draw on admission. Independent
  journal validation includes two different program IDs.
- `test_next_use_unix_save.py`: genuine save/exit/new-process restore between
  natural programs and at cap; rejected first **and middle** attempts;
  mid-program 2 restore; truncated current journal and damaged previous journal
  both fail closed. Explicit old-NUS1 and dropped-witness preservation probes.
  Wizard geometry and hand-placed ordinal envelopes are declared fixture controls.
- `read_journals`: bounded ordered list, repeated-ID separation, swapped-order
  and truncated-chain rejection, and historical single-journal compatibility.
- Regression control: the new series fixture linked against PR 2's safe layer
  admits program 1 then fails at program 2 (NOT_OPEN), as expected.

## Ordinary evidence and limitations

`result.json` is a separate, successful nonwizard `python3 -m chaos play
--ordinary` save/exit/restore/quit smoke capture. It does not claim program 2.
An additional bounded ordinary two-program attempt did **not** qualify: program
1 did not produce a complete journal in its allotted input sequence. It was not
retried or selected away; its raw evidence and failure log are retained locally.
Natural second/third admissions are established by the linked and real Unix-game
fixtures above, with hand-placed envelopes, not by director scheduling or a
claimed uncontrolled ordinary success.

Final warning-clean builds, full fast/native suites, required CI, and retained
artifact digests are reported on the PR after the final gates finish.
