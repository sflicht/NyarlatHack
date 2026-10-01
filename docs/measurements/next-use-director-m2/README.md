# M2 director scheduler: ordinary smoke and v2 metrics

Verification tier B: director selection, launcher choice and post-run reporting.
Native additions only project public diagnostic receipts after existing journal
acknowledgement; no admission, budget, RNG, save layout, effect or replay rule
changes. No Arc 1 wording changes. All gates remain required.

## Ordinary default-path smoke

`ordinary/` is a real nonwizard `python3 -m chaos play --ordinary` capture on
implementation revision `cb99b7e293bedbddc0e44ef535f779123cfc0be5`.
Default haunt, M1 and next-use are enabled. No model, wizard, seed/clock override,
hand-placed envelope, patched game state, hidden-map steering, or policy retry.
A no-op shared library satisfies the existing Game harness's preload interface;
it exports no clock/RNG overrides. Binary/data hashes are in `manifest.json`.

The fixed bound was two prayers and at most 120 search commands waiting for
program 1's terminal receipt. Inputs: inspect inventory, apply the visible tin
whistle, pray, apply again; wait if needed; apply once after terminal, pray,
apply again; save, restore, search, quit. `inputs.json` is the actual byte trace.
The director got up to three wall-clock seconds after each origin to publish;
no game turn, safe index or envelope deadline was retimed.

Both programs published naturally, were admitted and completed. Program 1
produced one witnessed W event at public turn 9; program 2's quiet callback
completed without a delivered/felt effect. Both journals are independently
readable. Terminal event sequences are 20 and 31; program 2's published/bound
origin root is 22, completed at event 24, strictly newer than 20. Both reused program id 2, demonstrating why
ordinal identity matters. Save and quit returned 0; the event stream contains
one restore and the recorded v3 M2 choice remained enabled/cap 3.

This is a bounded smoke, not a survival/balance estimate. No program-3 claim.
The harness did not collect a Dlvl timeline, so this capture's felt Dlvl is null;
the sweep player does collect its public status timeline. The default hound was
enabled but had no accepted encounter in this short run.

## Disclosed earlier attempts

`harness-error/` retains the first failed attempt: a greedy inventory regex chose
armor rather than the whistle, producing no qualifying action and no envelope.
After fixing item-boundary parsing, one replacement development run naturally
admitted/completed programs 1 and 2 and saved/restored. The final run above was
then repeated once on the committed implementation, not selected by seed/outcome.
No failed attempt is presented as successful. The development capture identified
its base revision but had a dirty implementation tree; it is not the final
revision witness. All three raw PTY traces, receipts and the exact final driver
are retained under `~/.hermes/reports/nyarlathack-m2/pr4/`.

## V2 report semantics

The action policy/parameters remain baseline-v2. Report schema `report_v` is now
4 for v2; v1 remains 1 with unchanged row/aggregate shapes. V2 adds `programs`
(three ordinal rows) and `felt_events` (`turn`, `dlvl`, `kind`, `program`). `program`
is null for hound/door/hunger or unattributed historical W events, not a fictitious
program zero. Counts for delivery may exceed one (W and F); publication/admission
are 0/1. `termination` is null while unknown/open, a runtime termination reason,
or `rejected:<reasons>`. Missing/invalid/open admitted journals remain unknown,
not silently zero-delivery evidence. Original single-journal runs still read.

New public felt receipts attribute W/F by public action root; an actual public
notice supplies the turn. A native delivered effect alone is not felt. Historical
W public witness records remain usable; historical F traces without the new public
attribution cannot be assigned a felt event from private replay clocks. Every
visible hound step and door resistance under an active door effect is retained.
Hunger records the first observed Hungry status in each accepted hunger effect's
[start, expiry) window; Weak/Fainting, pre-activation or expired samples do not
count. Dlvl comes from public status, or null when absent. V2 aggregates sum each
program's funnel and termination reasons; `first_felt` is the first public entry.

`test_sweep_programs.py` also reads PR 3's retained three-program real-game
fixture. It confirms three admissions/terminations but does not invent felt
events where those old artifacts lack public notices. Full paired sweeps and the
rest of the proposal's broader measurement plan are not claimed here.
