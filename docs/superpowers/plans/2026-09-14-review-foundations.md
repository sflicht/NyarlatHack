# Review Foundations Implementation Plan

> **For Hermes:** Use subagent-driven-development for isolated implementation and spec/quality review.

**Goal:** Implement the review's first usable, testable foundations and revise the entire open backlog without pretending the ambitious proposals are finished.

**Architecture:** Keep the two-process mailbox, engine-owned eligibility/prices, exact safe-index targeting, and admitted-effect lifecycle. No live model calls, budget increase, provider fallback, or security-setting change is authorized by this batch. Preserve previous review provenance when revising issues.

**Tech Stack:** Existing Python 3.11 standard-library director, C engine, Lua 5.4, unittest and linked/terminal harnesses.

## Task 1 — public backlog decisions (parent)
Read all thirteen current issue bodies and comments; snapshot before edits. Update #5 to choose exact-index/no-retime scheduling and coalesced Sanity observations; #6 to require measurements and retain prefix-rewrite detection (incremental hashing is not equivalent); #7 to allow only a single enclosing fence/whitespace removal. Update stale milestone claims and sequence #1/#9–#13 without closing unfinished proposals. Read every edited issue back and compare exact title/body payload.

## Task 2 — launcher (#3; isolated worker)
Create `chaos/launcher.py` and `tests/chaos/test_launcher.py`; modify `chaos/__main__.py` only for CLI wiring. Start with offline pack/random backends, explicitly no automatic paid model invocation. A parent supervisor keeps the game attached to the terminal, runs the director as a distinct child with input disconnected, stops/reaps the director after game exit or signal, and preserves the game's exit status. Validate a private owned run directory, no concurrent writer, game executable, arguments, and backend before starting the game. Preserve the directory for restore, print its path without credentials, and never delete save/evidence on exit. Write failing tests first for invalid/private directories, lock contention, exit propagation, startup failure, cleanup and argument forwarding; exercise real subprocesses where possible. Run `PYTHONPATH=tests/chaos:. python3 -m unittest -v test_launcher`. No changes to C, director.py, other test files or docs; no commit/push by worker.

## Task 3 — bounded response normalization (#7; isolated worker)
Own `chaos/model.py`, `chaos/oauth.py`, optional `chaos/response.py`, and a new `tests/chaos/test_response_cleanup.py`. Use a shared normalizer only at model response boundaries: unchanged strict JSON or one complete enclosing Markdown fence with empty/json language plus surrounding whitespace. Reject prose prefixes/suffixes, nested/multiple fences, extra schema keys, duplicate keys, changed identifiers/index, and ineligible mutation. Never repair semantics or repeat inference. A failed normalization spends exactly the existing request attempt; no extra network call for local parsing. Do not normalize Lua source generation: exact-source preservation remains mandatory. Write and run failing fake-client/server tests before implementation; use existing OAuth/model regressions and directory-sync tests. No live requests, credentials, CLI edits, C edits, commit or push.

## Task 4 — observations and scheduling (#4/#5/#8; parent)
Inspect `src/chaos_engine.c`, hooks and director State; select only already public bounded scalar context for the first observation expansion. Selected after code inspection: use status-line health/power values (including polymorph health selection and displayed negative-health clamp), and exact prayer confirmation/cancellation enums. Do not use depth or identity strings in this first slice. Extend the whitelist and real C/terminal evidence; demonstrate that unknown/hidden fields remain absent. Add exact-count coalescence test in an actual linked engine harness, preserving future/past index behavior. Run tests red before fixes, then focused gates.

## Task 5 — review and release
Run Ruff, changed-file checks, the game-enabled unittest suite, and targeted real terminal launcher validation. Keep source-seam tests but distinguish them from behavioral proof. Spec review first; independent correctness/security review after spec passes. Address blocking findings before publishing. Link verified commits/tests to issues; close only acceptance criteria actually met. Leave budget retuning, new mechanical mutations, masks, deceptive scripture, bones, altar and broader Dreamlands explicitly pending where not implemented in this batch. Produce a concise human-facing report and preserve reproducible evidence.
