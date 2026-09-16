# Supplemental turn-loop dump comparison contract

## Narrow approval and status

sflicht approved the separately labelled provenance/header comparison in Discord
message **1549898563021054044**, thread **1548884673344577627**, as relayed in the
parent's explicit implementation authorization: validate the build header against
independent build evidence; require **every other byte** exact; preserve the
original failed result. This record does not claim an independent Discord fetch.
It implements the proposal in `/tmp/nyarl-turnloop-dump-contract-review.md:70–77`.

Status: **proposed implementation with synthetic unit validation only; native
acceptance and independent review pending**. Existing strict `compare_runs` and
its cross-build mismatch negative remain unchanged. The original strict failed
native execution at revision `170c68e502a91662df832ec6029603915f0a1666` remains
FAILED forever at `/tmp/nyarl-episode-turnloop-work/final`; never overwrite or
relabel it. The separate core evidence at `49d4e166d001d27072ba9b50f5854a70a8e70cb7`
is also untouched. This does not close Task 8, exact-current-HEAD acceptance,
the remaining matrix, or the whole phase. No gameplay rerun is authorized here.

## API and independent-evidence trust boundary

`tests/chaos/turnloop_dump_provenance.py` is a test-only, no-I/O helper:

1. `validate_build(build_name=..., expected_header=..., date_h=..., manifest=...,
   trusted_manifest_sha256=..., artifacts=...) -> VerifiedBuild`.
2. `compare_provenance_dumps(reference, candidate, reference_build=...,
   candidate_build=...) -> dict` labelled `provenance-validated-dump-v1`.
   Any invalid binding or mismatch raises `ValueError`, including under `-O/-OO`.

`expected_header` is independent bytes without a line terminator, never extracted
from the dump being compared. `date_h` contains exact generated source bytes.
`artifacts` maps exactly `dnethack`, `nhdat`, `license` to the actual run's file
bytes, not paths or caller-declared digests. All three hashes are checked.

The **supplemental** manifest is UTF-8 JSON bytes with exactly these fields:

- `build_name`: nonempty named build, matching the explicit API input;
- `revision`: full lowercase 40-hex source revision;
- `mode`: integer 0 or 1 (not Boolean);
- `date_h_sha256`: lowercase SHA-256 of the exact per-mode generated source;
- `tuple_sha256`: exact mapping of `dnethack`, `nhdat`, `license` to SHA-256.

`trusted_manifest_sha256` must be pinned independently by the reviewed producer
or evidence reviewer, **not calculated ad hoc from untrusted evidence to bless
it**. The producer must verify original per-mode receipt/source/tuple provenance
before issuing this supplemental manifest. Its schema is not a claim that old
native manifests already contain these fields. A self-consistent arbitrary JSON
object is not independent evidence. Hashes authenticate bytes against a trusted
pin; they do not prove historical truth or reveal a date. The helper verifies
source and actual tuple bytes against the pinned binding, the exact generated
`VERSION_ID` definition, native header grammar, and header revision prefix.
Only this validating factory produces `VerifiedBuild`; arbitrary dictionaries
and direct construction are rejected. Python object internals are not a sandbox
against hostile code in the same process.

Each result records named builds, exact expected header hex, full revision/mode,
manifest/source hashes, and complete binary/data/license tuple hashes. Integration
must also bind those actual file bytes and the complete dump mapping to the
specific run. It must not silently filter unknown filesystem entries.
`validate_historical_build` is a separate fixed-pin factory: historical stock
`ff37b3a7a5381ea9b5d5960dda7bd756c6c8dbd8` is bound to the reviewed original
receipt and independent old dump, not a compared route. Its receipt binds only
binary/data; its license pin is separately reviewed. `date_h_sha256` is `None`
and `source_kind` is `historical-recorded-dump`; no generated source is invented.
The old current-build OFF date.h remains unavailable; it is not inferred.

## Opt-in driver integration (test-validated, not native acceptance)

`--provenance-dumps` requires `--matrix` and all historical-stock arguments.
The unittest adapter adds it only with `NYARLATHACK_TURNLOOP_PROVENANCE_DUMPS=1`.
Default strict comparison and `result.json` remain unchanged, including failed
cross-build dump comparisons. A separate `provenance-result.json` uses label
`provenance-validated-dump-v1` and retains strict status/mismatches; Task 8 remains
open. Driver-local cleanup must finish before publishing supplemental success;
outer family cleanup remains the existing supervisor's independent gate.

`turnloop_header_bindings.py` checks full root HEAD, pinned reviewed Linux
producer sources/configuration and absence of local.mk overrides. It validates
both successful clean/install command records, full revision/mode, every actual
tuple hash and size, and each captured `<mode>-date.h` against the original
manifest before deriving/pinning any supplemental manifest. Only the exact
plain ASCII generated literal is supported, without C escapes, concatenation,
macros, or runtime suffixes. Original receipt/capture bytes, hashes and sizes
are retained in pre-route `header-bindings.json`. This is the cooperative
same-UID receipt trust model, not cryptographic build attestation.

Each copied run tuple is verified before launch and after play. Complete dump
directory enumeration requires the frozen route's sole `1700000000` regular
file; symlinks, directories, extra/missing filenames fail. Inputs, terminal and
xlog stay exact. Same-build full dumps and event repeats remain exact. Sources
and source tuples are checked again at completion. Native execution and
independent specification/quality review remain pending.

## Exact comparison boundary

Both mappings must be nonempty and have exactly the same filenames/counts; values
are raw bytes, not decoded text or hexadecimal strings. Exactly one native build
header must occur, at line 2, and match its independently validated expectation.
Missing, duplicate, misplaced, foreign or malformed headers fail closed. Only
that validated line's content is excluded. Line 1, all newline delimiters
(including LF versus CRLF), all body bytes, whitespace and trailing data remain
byte-exact. No generic regex stripping, whitespace normalization or fallback.
The regex validates the explicitly supported native structure; it removes nothing.

Same-build comparisons additionally require entire dump bytes exact; existing
same-build repeat gates remain intact. Inputs, terminal, xlog, legacy/v2 events,
seed/clock, native aftermath and all other requirements stay with the existing
strict oracles and driver. This new dump-only helper does not certify those gates
or establish whole-run equivalence. No model/provider/budget changes, native
builds, baseline replacement or old-artifact edits are part of this increment.

## Unit verification

`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:tests/chaos python3 -m unittest
 test_turnloop_dump_provenance -v` (one shell line) runs explicitly synthetic unit
fixtures, not native or model-generated receipts. Mutation cases cover dates,
revision, tuple binary/data/license, source/manifest bindings, missing/duplicate/
misplaced/extra headers, line-one/body bytes, whitespace, LF/CRLF, trailing bytes,
file sets and empty evidence. The suite runs again in `-O` and `-OO` subprocesses.
Existing native oracle mutation negatives may be read-only checked against the
preserved artifacts; neither that check nor unit success changes strict exit 1.
