# Milestone 1 validation

Milestone 1 is a playable, bounded Tier 2 prototype. The checks below are
executed results, not inferred guarantees for arbitrary play or future scripts.

## Executed acceptance

The full command is:

```sh
make -j4 install CHAOS=1
NYARLATHACK_GAME_TESTS=1 python3 -m unittest discover -s tests/chaos -p 'test_*.py' -v
ruff check chaos tests/chaos
```

On the development host, the stock installation is preserved at
`/home/hermes/.local/share/nyarlathack/baselines/ff37b3a7a`. Elsewhere set
`NYARLATHACK_STOCK_DIR` to an unmodified, matching dNetHack installation.
The test count and raw final output are recorded in `evidence/` beside this file.

- **Protocol and mailbox:** actual C parser and transport reject malformed,
  duplicate, oversized and ineligible requests; tests cover budget, expiry,
  future scheduling, reentrancy, failed logging, failed presentation and consumed
  identifiers. The test fixture never reads device files as event logs.
- **Director:** bounded event-tail handling, strict request schema, private
  atomic mailbox publication, no overwrite before acknowledgement, restart
  handling, redacted summaries, random eligibility and accepted-schedule replay.
- **Model transport:** an explicitly fake local Hypertext Transfer Protocol
  (HTTP) server verifies request construction, validation, response limits,
  redirect rejection, no retries, call caps and request deadlines. A new
  regression caught the director not propagating its runtime deadline to an
  in-flight model request; that defect was fixed and retested. No live model
  was contacted or paid for.
- **Actual hunger and ward physics:** `game_rules.c` links the real game's
  compiled objects. It calls `gethungry`, observing ordinary consumption of one
  food unit, two under an admitted hunger effect, then one at expiry. It calls
  the actual `onscary` with a completed heptagram and a controlled monster:
  protection is present, absent under weakening, and present after expiry.
  The engraving itself remains unchanged. These are initialized linked-engine
  fixtures, not a bot's naturally occurring encounter.
- **Actual terminal save/restore:** a wizard-mode game admits a ward effect,
  queues a future hunger request, saves and exits. Restore retains spent and
  reserved budget, the consumed identifier and safe index. The pending request
  is admitted once at the next Sanity threshold. Both effects expire; lifetime
  spending is retained.
- **Incompatible saves:** real games save with director support on and off.
  Both opposite-layout restore attempts print the configuration incompatibility
  diagnostic rather than reading mismatched player state. Each binary must
  also be paired with its corresponding `nhdat` data file.
- **Stock equivalence:** three real terminal sessions—unmodified stock,
  director-compiled but inactive, and active observation with an empty mailbox—
  create the same character, wait twelve turns, and quit. Input bytes, complete
  terminal output and score logs are byte-identical under the controlled test
  environment. This is a short regression scenario, not exhaustive equivalence.
- **Accepted-schedule replay:** the real Python pack command submits hunger;
  a real wizard-mode game admits it. The real replay command requires matching
  accepted event evidence and submits that same request to a fresh real game.
  Identical actions produce identical terminal output, event records and score
  logs. This verifies one controlled accepted schedule, not unrestricted
  multi-session gameplay replay.

The four source-seam tests in the fast suite inspect code wiring; they are
not mislabeled as behavioral gameplay tests. Without `NYARLATHACK_GAME_TESTS=1`,
the five full-game tests are explicitly skipped and cannot establish acceptance.

## Why a seed is insufficient

The parent session's first stock comparison failed even with a fixed clock and
fixed `srand`/`srandom` seeds. Source inspection found `check_reseed` in `src/rnd.c`:
subsequent `/dev/urandom` reads determine both new seeds and reseeding intervals.
The test-only preload now controls those entropy reads as well as the clock.
It is applied equally to the unchanged stock binary and the new binary.
The resulting comparison passes without normalizing away gameplay differences.

The harness records input bytes, terminal output and a session manifest with
binary, game-data and preload hashes. Test clock, timezone, terminal dimensions
and character options are fixed by committed test source. The ordinary game
continues using its normal randomness. A general recorder for arbitrary live
entropy, human inputs and save rollback histories is not implemented.

## Review and scope

The parent reviewed specification coverage and code inline after the user
questioned repeated delegation. No final independent reviewer agent was used.
Review included strict parser probes, actual builds, the linked-engine tests,
the terminal tests, Python lint and a targeted added-code security scan.
There is no basis here to claim independent external certification.

The original list of possible mutations was illustrative. This implementation
ships ambient messages, ward efficacy and hunger rate, not spawn weighting,
shopkeeper disposition or every other proposed category. The entire director
allowance is presently at most twelve lifetime cruelty points: intentionally
conservative prototype policy, not a validated pacing design.

## Not established

- Live language-model gameplay quality or provider-specific compatibility.
- Long-run balance, fairness, endgame reachability under every combination, or
  replay of arbitrary ordinary games from only a starting seed.
- Atomic crash recovery spanning game saves, journals and the sidecar.
- A hardened adversarial multi-user hosting boundary.
- Runtime scripting, the Dreamlands validator, or Dreamland echoes. The echo
  requirement is preserved in `tier3-notes.md`; it is not implemented by the
  ordinary ambient-message mutation.
