# The Crawling Chaos director

For the implemented constrained-runtime encounter, harmless history echoes, and
the user-selected GPT-5.6 Luna / ChatGPT OAuth route, see
[the First Haunting guide](../docs/milestone2.md). The generic HTTP model backend
described below is an optional alternative, not an automatic fallback.

Python 3.11+; standard library only. Run `python3 -m chaos --help` from the
repository root. No package installation or model key is needed for offline
play. An application programming interface (API) key is needed only for the
explicit `model` command.

## Opt-in history-conditioned pilot

Use the separate `python3 -m chaos history` command to consume mixed observation
history. A completed delivered fountain refresh can qualify an existing 10- or
20-turn hunger effect; a prior accepted hunger whisper suppresses repetition.
Empty eligibility means no model request. Legacy `play` and authoring do not
silently switch to this consumer.

The [pilot guide](../docs/history-conditioned-whispers.md) documents two-terminal
startup, ordinary-food affirmation, the existing-ledger-only Luna subscription
route, strict mixed replay, measured native effects and limits. Publication,
acceptance and a measured rule effect remain different claims.

## One-command offline play

### Current prototype and old-save migration

Ambient now costs **0 mechanical / 1 cosmetic**: at most three deliveries per
game, each fixed value 1/2/3 once, at least 50 native moves apart. This is a
prototype, not tuned pacing or continuous full-run presence. Mechanics retain
the 12-point lifetime ceiling and Sanity gates: curio1, haunt2, hunger3, ward4.
Expiry refunds no lifetime spending. Saved cosmetic mask/timestamp survive
restore; restarting/changing directors or waiting cannot refill them.

State/save version2 emits ordinary events3 and optional observations4; requests
remain v1, and journals use policy2 with separate `cosmetic_cost`. Historical
v1/v2 logs remain readable offline, **not current replay/publication inputs**.
Both ordinary and history replay require exact current accepted ACKs matching
the policy2 journal, including request, native turn/safe, both tariffs and expiry.
Neither a journal nor a telegraph replaces a missing final ACK.

**Answer NO to “Delete the old file?” on an incompatible old save.** Keep that
save with its matching old binary and `nhdat`; use a separate new game and run
directory for the new build. There is no automatic migration or fresh-credit
interpretation of an old save. The new CHAOS structural/clock guard preserves
the file, but stock short-read corruption handling still can delete damaged
saves; this is not blanket save protection. Back up saves independently.

Current full native save/replay gates remain pending reviewed fresh-build
acceptance. The [policy and bounded synthetic comparison](../docs/chaos-protocol.md#cosmetic-pacing-prototype-and-migration)
separate native-core accounting from actual gameplay/UI witnesses and retain
historical evidence unchanged.

After building, from the repository root:

```sh
python3 -m chaos play
python3 -m chaos play --backend random --seed 7
python3 -m chaos play --ordinary
```

`--ordinary` starts a human Bard with a dog, no wizard mode, and sets
`NETHACKOPTIONS` only if it is unset. It is a frozen test identity, not a
ban on other roles. Combine it with `--` game arguments only if they are not
wizard-mode tokens (`-D`, `-u wizard`).

The default publishes the ambient pack before starting the game. The supervisor
prints a fresh private run directory and keeps it for save/restore and evidence.
The game uses your terminal; the offline director is a separate child process.
No model call or credentials are involved. An actual `ack` with `accepted` in
`events.jsonl`, not launcher readiness, proves that the game admitted a request.

Use `--game-root /path/to/install` for another installation; keep its executable
and matching `nhdat` together. Put literal game arguments after `--`, for example:

```sh
python3 -m chaos play --pack hunger --at 2 -- -D -u wizard
```

That demonstration still needs an eligible ordinary-food character and Sanity 60
as described below; the launcher does not waive engine eligibility.

For restore, keep the matching save/game installation and explicitly reuse the
printed directory with the same pack/ID/index or random configuration:

```sh
python3 -m chaos play --reuse-run-dir /the/printed/path
```

`--run-dir /new/path` creates a new directory and rejects one that already exists.
Do not reuse a run directory for an unrelated new game. Existing ended, malformed
or conflicting state fails closed; incomplete pre-existing event records are
rejected without deleting or repairing the log. Partial records during active
game observation remain buffered until complete. An older-save rollback still needs manual
reconciliation. An already acknowledged matching pack is not applied again. A pending request
must still target a future index; for a fixed pack it must exactly match the
selected next request. Conflicts fail before startup without overwriting the
mailbox, deleting history or retiming. These checks also run before child
readiness, not only in parent preflight.

The supervisor holds the single-writer lock until the game exits, even when the
director finishes its pack or reaches its default 300-second runtime. A later
director failure does not stop gameplay. Normal game save/quit is the preferred
exit path. Interrupt, termination or hangup signals initiate bounded supervisor
shutdown; a child that will not exit is killed after the grace period. This is
not an automatic-save guarantee, and an uncatchable supervisor kill cannot run
cleanup. Director diagnostics go to the private `director.log`.

This is a POSIX (Portable Operating System Interface) launcher, tested on Linux. `play` currently supports only offline
pack/random modes; explicit model/OAuth commands below remain separate. Provider
configuration is not universally interchangeable and never silently falls back.

## Explicit saved-curio launch (offline)

A saved curio is a candidate Lua object program; installation does not mean the
engine admitted it. Select either a plain source file or an existing bundle:

```sh
python3 -m chaos play --run-dir /new/private/run \
  --curio-source /private/source.lua
# Alternative: ID is the bundle's exact 64 lowercase hexadecimal source identity.
python3 -m chaos play --run-dir /another/new/run \
  --curio-bundle-root /private/bundles --curio-candidate-id "$ID"
```

The bundle root and selected ID directory must already exist, be owned by you,
and have mode 0700. Bundle files must be owned regular mode-0600 single-link
files: `raw-response.json`, `source.lua`, `continuity-note.txt`, and
`manifest.json`. The launcher reparses the envelope and verifies the exact
source, note and manifest; it does not repair Lua or normalize the ID. A plain
source must be an owned mode-0600 single-link file in a private mode-0700 parent,
with 1–4096 non-NUL bytes. Unsafe paths, symlinks and conflicting evidence reject;
the launcher does not change supplied permissions to make them acceptable.

`--curio-source` and `--curio-bundle-root` are mutually exclusive. Bundle root
and candidate ID must be supplied together; an ID cannot accompany plain source.
Validation finishes before creating a run directory. Omit both run flags for a
fresh private directory, or supply `--run-dir` with a path that does not exist.
Unlike standalone `curio install`, fresh `play` never adopts a precreated run.
Installation and readback finish under the supervisor's held lock before either
child starts.

For a matching restore, keep the original private run path, matching save/game
installation and director configuration, and explicitly repeat the same selection:

```sh
python3 -m chaos play --reuse-run-dir /another/new/run \
  --curio-bundle-root /private/bundles --curio-candidate-id "$ID"
```

With either source form, reuse requires an existing safe `.director.lock`, exact
`curio.lua` and `curio-install.json`, and matching `curio-used.lua` if present.
This is verification only: no reinstall, repair, deletion of crash leftovers,
receipt promotion or schedule retiming. The verification seam is read-only;
subsequent ordinary director/game activity is not. A valid standalone bundle
installation can also be explicitly verified this way before startup.

The receipt retains status `candidate_installed_not_admitted`. Bundle selection
records `supplied_raw_envelope`; plain selection records `supplied_source_file`,
even when that file is a bundle's `source.lua`. These provenances are not
interchangeable on restore. Neither proves model authorship, native admission,
native save/source equality, historical raw-response/note identity or full
continuity-journal consistency. No-selector play retains its **legacy unverified
curio behavior**: it does not perform these curio checks, even with preexisting
curio files. An earlier standalone verify is not continuous-lock launcher
verification.

There are no automatic continuity-journal operations. Explicit offline
`bind_run`/`observe` operations remain separate and require stable evidence after
**both children have exited**; binding after an initial save/exit is supported.
The default ambient pack (including the pack named `silence`) is a real whisper,
not an empty stream. Saved-curio launcher process tests use a handwritten fake
executable fixture; native discovery, use and save/restore acceptance are separate.

## Manual alternative: fixed ambient whisper

```sh
RUN=$(mktemp -d)
python3 -m chaos pack ambient --run-dir "$RUN" --install-only
(cd dnethackdir && NYARLATHACK_RUN_DIR="$RUN" ./dnethack)
```

The directory must exist, belong to you, and be private (mode 0700).
`mktemp -d` supplies that. Use a fresh directory for each new game. Keep the
path when restoring that game; do not share one mailbox between games.
The engine logs newline-delimited JavaScript Object Notation (JSON) events
in `events.jsonl` and admissions in `whispers.jsonl`. The single mailbox is
`whisper.json`; never overwrite it before its exact acknowledgement arrives.
The sidecar enforces a single cooperating writer using a lock file.

An already-running director retains a copy of its exact outstanding request.
The engine consumes its identifier and emits a telegraph before presentation
finishes and the acknowledgement is written. During that narrow live interval,
the director waits only while the mailbox is unchanged and the observed
telegraph, mutation, safe index and last identifier match the known request.
This is **not acceptance**: the mailbox cannot be overwritten and no retry or
retiming is permitted. A matching acknowledgement is still required to proceed;
the existing runtime cap bounds a missing acknowledgement. Changed/deleted mail,
mismatched acknowledgements and incompatible progress fail closed. Startup has
no trusted live-request copy and retains strict reconciliation checks.


A request published before startup with `--at 1` targets initial level entry.
The output `installed_pending_ack` means only that the file was published.
An actual `ack` event with `status: accepted` confirms game acceptance.

## Demonstrate an actual rule change

The `ward` and `hunger` packs need lower Sanity than a fresh ordinary character
has. For a reproducible demonstration, use the game's built-in wizard mode:

```sh
RUN=$(mktemp -d)
python3 -m chaos pack hunger --run-dir "$RUN" --at 2 --install-only
(cd dnethackdir && NYARLATHACK_RUN_DIR="$RUN" ./dnethack -D -u wizard)
```

Choose a human Wizard, no inheritance. Type `#setsanity`, press Enter, then
enter `60`. The observed Sanity change creates safe point 2 and admits the
hunger request. Normal food consumption doubles for the pack's duration.
Use `pack ward` instead for weakened ward protection. The available pack names
are `ambient`, `silence`, `ward`, and `hunger`; `silence` is a different fixed
ambient message, not a command to mute the director.

## Random director

Use a second terminal, with the **same absolute run directory** as the game:

```sh
python3 -m chaos random --run-dir /absolute/private/run --seed 7 \
  --max-runtime 300 --max-submissions 12
```

Add `--ordinary-food` only when the player uses ordinary food metabolism; it
permits hunger proposals. The engine independently rejects ineligible forms.
The random director has its own seeded generator; it does not consume game
randomness. Requests target the next safe index. If the player outruns a
proposal, the engine rejects it rather than applying it at a different time.
Current random and generic model menus prefer eligible ward/hunger. Only when
neither is eligible do they offer unused, cooldown-eligible ambient values;
model response validation rejects a used value even if `ambient` is eligible.
Pack/replay may choose ambient despite eligible mechanics, but cannot bypass
the native cosmetic clock, repetition or lifetime gates. Curio/haunt are not
members of this menu, and mechanical starvation remains possible.

## Replay an accepted schedule

Stop the old director, use a fresh run directory, and retain both files from
the source run:

```sh
python3 -m chaos replay /source/run/whispers.jsonl \
  --accepted-events /source/run/events.jsonl \
  --run-dir /new/private/run --max-runtime 300
```

Start the new game using `/new/private/run`. The replay director requires
matching accepted acknowledgements: the admission journal is written before
presentation and is **not by itself proof that an effect happened**. Replayed
requests retain their original identifiers and safe indices; missed/rejected
schedules fail rather than silently retime.

This replays **requests, not player inputs or the whole game environment**.
For identical gameplay, the engine/data, initial options and state, player
inputs, terminal size, clock/timezone and **all entropy reads** must match.
dNetHack periodically reseeds from system randomness after startup, so a
starting seed alone cannot reproduce ordinary play. The acceptance harness
supplies a controlled environment and records inputs; it verified a real
accepted hunger run twice with identical output and score logs. Unrestricted
record/replay of arbitrary sessions and arbitrary save rollbacks is not shipped.

## Optional model backend

The generic connection is tested with a clearly identified local fake HTTP
(Hypertext Transfer Protocol) server, not every advertised compatible provider.
The separate pinned Luna OAuth route was live-tested for First Haunting; that
does not establish long-run balance or generic-provider interoperability.

Configure the full HTTPS (HTTP over Transport Layer Security) chat-completions
endpoint, model identifier, and **name** of the environment variable holding
your API key. Set the key privately, not in a command saved to shell history:

```sh
timeout 310s python3 -m chaos model \
  --run-dir /absolute/private/run \
  --endpoint https://YOUR_PROVIDER/v1/chat/completions \
  --model YOUR_MODEL --api-key-env YOUR_PRIVATE_KEY_VARIABLE \
  --max-calls 4 --timeout 10 --max-runtime 300
```

Replace uppercase placeholders with your chosen configuration. This example
is not an endorsement of, or a verified live integration with, a provider.
The outer `timeout` supplies a process wall-clock cap, including operating-system
name resolution; internal network timeouts alone are not a universal hard limit
on name resolution. Add `--ordinary-food` for a food-using character.

The model receives only a bounded whitelist of player-observable event fields
and the eligible registry. It cannot send prose to the terminal, execute code,
choose files, assign prices or change its assigned schedule. Responses must
match the engine's strict request schema. Whisper adapters may remove surrounding
whitespace and one complete enclosing bare or `json` Markdown fence; they do not
salvage prose, repair fields, change identifiers or retime requests. Local
cleanup adds no model call and never normalizes exact Lua-generation source.
Redirects and automatic retries are
not allowed. Failures count toward the configured call allowance. Keys and raw
response bodies are not printed. Provider-specific billing caps are not inferred
from the call cap. Use provider-side spending limits as well.

Default limits: 4 model calls; 10-second request timeout; 8,192-byte message
context; 16,384-byte response; 256 requested output tokens; 300-second director
runtime; 12 submissions; 50,000 events; 16 MiB of event input (MiB means
1,048,576 bytes). No new request is issued without a fresh eligible decision
point or while a previous request remains unacknowledged.

The legacy model summary retains the newest **12 events**, with only whitelisted
status fields, validated vitals and the exact confirmed/cancelled prayer enums;
arbitrary details and hidden facts are excluded. `--max-context` bounds serialized
messages (default 8192 bytes; allowed 2048–32768); overflow fails, it does not
silently truncate or make an extra call. `--max-calls` permits 1–100 (default 4),
`--timeout` greater than zero through 120 seconds (default 10), and
`--max-response` 512–65536 bytes (default 16384). These existing model limits
are separate from the offline episode window below, which is not fed to Luna.

## Offline selected-action observations

This observation foundation records selected whistle actions and confirmed
fountain drinks, not new whispers or effects. It does not change Luna, Lua,
cruelty budgets or recurring gameplay. Current default events are v3. To opt in to
mixed v3/v4 logs, start the already-built game directly, without a director:

```sh
RUN=$(mktemp -d)
(cd dnethackdir && NYARLATHACK_RUN_DIR="$RUN" NYARLATHACK_OBSERVATIONS=1 ./dnethack)
```

Keep `$RUN` for that game's restore and evidence; use a new private directory for
another game. Only the exact value `1`, read once at startup in a `CHAOS=1`
build with healthy run transport, enables observations. The enabled marker
precedes the v3 session record. **Do not enable this for ordinary `chaos play`,
directors or ordinary replay:** their ordinary-event parsers reject observation
rows (historical v2 and current v4). Use the explicit history pilot where needed.

After the game exits, from the repository root, replace the path in this Python
example with your retained private run directory. It reads only existing data:

```python
import json
from chaos.episodes import snapshot_episodes

public, proof = snapshot_episodes("/absolute/path/to/private/run")
print(json.dumps(public, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
# Recheck exactly the same prefix, even if valid later records were appended.
same_public, same_proof = snapshot_episodes(
    "/absolute/path/to/private/run", checkpoint=proof
)
assert same_public == public and same_proof == proof
```

`proof` is host-only device/inode, length and SHA-256 evidence; do not send it to
a model. The target must be an owned mode-0700 directory with an owned,
regular single-link mode-0600 `events.jsonl`, without symlink traversal. Replaced,
rewritten, truncated, malformed or over-cap history rejects; nothing is repaired.
The checkpoint verifies local prefix integrity, not source authenticity or
protection against a malicious process running as the same user.

For already-loaded bytes, import `parse_episode_event` and `project_episodes`
from `chaos.episodes`. The first validates a single row (not a safe public
projection); the second validates the full serial history before reducing it.
The [protocol](../docs/chaos-protocol.md#offline-episode-projection-and-limits)
defines every schema field and limit: 16 MiB/50,000 events of complete history,
newest 32 selected roots since the latest session, at most two operation groups,
three evidence entries per group, counts capped at three with saturation flags,
and at most 4096 bytes of canonical ASCII public JSON. Do not trim raw history to
32 roots: full history and a bounded summary are different things.

Started/notice/terminal records capture public context before the native call,
at actual supported delivery, and after return. A completed action need not be
beneficial; a missing terminal, including native death, remains incomplete.
Completed-without-notice is not “nothing happened.” Blocked is a native reach
guard, not cancellation. Cancel/decline/unsupported actions create no selected
root. Only completed roots with delivered allowed notices become positive
episodes. Whistle tone is not object identity or proof of companion obedience;
map presentation exports no monster locations. Other window ports or suppressed
output need not supply a notice. See the
[evidence ledger](../docs/haunting-observations-evidence.md) for accepted local
scope at `8f317763a`, including the approved provenance-validated turn-loop
acceptance and preserved **strict comparison failure**. Local acceptance is not
publication, whole-phase sign-off or consequential-vision (#26) completion.

## Safety and lifecycle limits

- The engine currently allows at most 12 lifetime mechanical cruelty points;
  ambient costs 0 mechanical / 1 cosmetic, hunger 3 and ward weakening 4.
  Mechanical capacity starts at 2 and gains one for each
  ten Sanity points lost. Expiry releases active reservation but **does not refund
  lifetime spending**. This is conservative prototype policy, not tuned balance.
- Effects last at most 50 game turns, do not stack by type, and cannot be refreshed
  while active. Ordinary food eligibility is checked again when hunger is used.
- Player state survives actual save/restore. If restoring an older save makes
  the event stream go backward relative to already-observed history, the sidecar
  stops for reconciliation; it does not guess which history to discard.
- An absent director or mailbox does not block play. Transport failures stop
  new admissions; previously admitted effects continue to expiry.
- A logged pre-admission and a saved game are not a cross-process atomic
  transaction. Unsaved crashes can leave admissions without applied effects.
- Private same-user files are the intended trust boundary. This is not a hardened
  multi-user game server. The narrow runtime and Dreamland history echoes are
  documented separately in [Milestone 2](../docs/milestone2.md); the generic
  Tier 2 transport described here does not accept executable scripts.

Details: [engine protocol](../docs/chaos-protocol.md) and
[validation](../docs/milestone1-validation.md).
