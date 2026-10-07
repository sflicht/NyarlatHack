"""The director's hound lane: one model-designed pursuit per game (NGPL).

Slice 5a (docs/proposals/model-authored-play.md section 4 "Hound"). With a
model configured, footsteps.lua is NOT installed at start. The engine's haunt
tick (src/chaos_haunt.c) looks for haunting.lua at each qualifying tick after
the first backtrack and, finding none, tries again later. This lane:

- requests once per game, when the first public "backtrack" event appears
  (the engine's own qualifying condition; nothing earlier is known to the
  host), while the lane is idle;
- publishes haunting.lua by rename(2) when a ready answer arrives; the engine
  admits it, or refuses it in its shadow trial, at its next qualifying tick;
- on any lane failure (deadline, transport, envelope, host pre-check, a
  restore that abandoned the request) publishes the hand-authored
  footsteps.lua instead, so the hound still happens.

The lane rules are the curio lane's (chaos/lane.py): the backend is built
before any run state; the lane record is durable before any send, so a
restore never asks again; the deadline is the lane's own clock and late
results are void; at most one regeneration, only for an envelope rejection;
ledger surface "haunt" (3 per game, 200 per day).

Replay: the engine's first haunting event about the candidate (budget,
pre_admitted, rejected, shadow_failed or source_rejected) names the window
(turn, sequence number) of its first look that found the file.
record_admission binds that window and the source's SHA-256 after the game.
stage_replay writes the source and haunting-due ("<turn> <seq>") into a fresh
run directory before the game starts; the engine treats the file as absent
before that window, so it admits at exactly the recorded point and not
earlier because the file is already there.
"""

import json
import time
from pathlib import Path

from . import curio_store as store, hound_author, lane as shared
from .haunt import DEFAULT_PACK, read_source

LANE = "haunt-lane.json"
DUE = "haunting-due"
CANDIDATE = "haunting.lua"
ADMISSION = "haunt-admission.json"
EVIDENCE = ("haunt-evidence", "haunt-evidence-2")
_STEPS = ("idle", "requested", "ready", "failed", "published", "fallback", "no_model")
# Engine haunting details that end the lane's interest: the candidate was
# looked at (budget is logged once, before any read, and still counts).
_DECIDED = ("pre_admitted", "rejected", "shadow_failed", "source_rejected")
_FIRST = _DECIDED + ("budget",)


def read_lane(directory):
    return shared.read_record(
        directory, LANE, steps=_STEPS, evidence=EVIDENCE, label="hound"
    )


def new_lane(directory, *, game=None, seed=None):
    """Fresh game with a model hound: the ledger game id and layer seed."""
    return shared.new_record(directory, LANE, game=game, seed=seed)


def _scan(directory):
    """(backtracked, decided) from the engine's own event log."""
    backtracked = decided = False
    path = Path(directory) / "events.jsonl"
    if path.exists():
        with open(path, "rb") as f:
            for line in f:
                if not line.endswith(b"\n"):
                    continue
                if b'"event":"backtrack"' in line:
                    backtracked = True
                elif b'"event":"haunting"' in line:
                    decided |= json.loads(line)["detail"] in _DECIDED
    return backtracked, decided


class HoundLane(shared.AuthoringLane):
    """One background hound request per game; poll() never blocks."""

    LANE = LANE
    EVIDENCE = EVIDENCE
    STEPS = _STEPS
    LABEL = "hound"

    def __init__(
        self,
        directory,
        backend,
        *,
        validator,
        fallback=DEFAULT_PACK,
        deadline_s=hound_author.DEADLINE_S,
        clock=time.monotonic,
    ):
        self._backtracked, self._decided = _scan(directory)
        self.fallback = read_source(fallback)
        super().__init__(
            directory, backend, validator=validator, deadline_s=deadline_s, clock=clock
        )
        if self.state == "no_model":
            # Configured but unusable (or a restored no-model record): the
            # hound is the hand-authored one, published at once.
            self._publish_fallback(None)

    def _read_evidence(self, evidence_dir):
        return hound_author.read_evidence(evidence_dir)

    def _author_once(self, evidence_dir, remaining):
        return hound_author.author_hound(
            self.backend,
            events_dir=self.directory,
            evidence_dir=evidence_dir,
            game_seed=self.game_seed,
            validator=self.validator,
            deadline_s=remaining,
            gate=self._gate,
        )

    def mark_no_model(self, reason):
        if self.state == "idle":
            super().mark_no_model(reason)
            self._publish_fallback(None)

    def note(self, event):
        """Feed one ingested event."""
        if event.get("event") == "backtrack":
            self._backtracked = True
        elif event.get("event") == "haunting" and event.get("detail") in _DECIDED:
            self._decided = True

    @property
    def active(self):
        """Whether the director loop must keep polling for this lane."""
        if self.state in ("requested", "ready", "failed"):
            return True
        return self.state == "idle" and not self._decided

    def poll(self, *, safe=None, **_):
        """Called from the director's mailbox loop; returns the lane state."""
        if self.state == "idle" and self._backtracked and not self._decided:
            self._start(safe)
        elif self.state == "requested":
            self._advance(safe)
        if self.state == "ready":
            self._publish(safe)
        if self.state == "failed":
            self._publish_fallback(safe)
        return self.state

    def _publish(self, safe):
        evidence = self.directory / self.record["evidence"]
        hound_author.read_evidence(evidence)  # re-verify the chain before use
        source = shared.read_path(evidence / "source.lua")
        shared.publish_source(self.directory, source, name=CANDIDATE)
        self._write("published", safe, "ready", self.record["evidence"])

    def _publish_fallback(self, safe):
        """The hound still happens: footsteps.lua, by rename(2), once."""
        shared.publish_source(self.directory, self.fallback, name=CANDIDATE)
        if self.state != "no_model":
            self._write(
                "fallback",
                safe,
                self.record["outcome"],
                None,
                error_type=self.record.get("error_type"),
            )


# ---------------------------------------------------------------- replay
def engine_window(directory):
    """The engine's first haunting event about the candidate: its window
    {"turn", "seq", "detail"}, or None when the engine never saw one."""
    with open(Path(directory) / "events.jsonl", "rb") as f:
        for line in f:
            e = json.loads(line)
            if e["event"] == "haunting" and e["detail"] in _FIRST:
                return dict(turn=e["turn"], seq=e["seq"], detail=e["detail"])
    return None


def _sha(raw):
    return hound_author._sha(raw)


def record_admission(directory):
    """After the recorded game: bind the engine's window and the exact bytes
    it looked at (model evidence or the fallback) into the run directory."""
    window = engine_window(directory)
    if window is None:
        raise ValueError("the engine never looked at a hound candidate")
    record = read_lane(directory)
    source = shared.read_path(Path(directory) / CANDIDATE)
    evidence = None
    if record is not None and record["step"] == "published":
        evidence = record["evidence"]
        receipt = hound_author.read_evidence(Path(directory) / evidence)
        if receipt["lua_source_sha256"] != _sha(source):
            raise ValueError("published bytes differ from the evidence")
    admission = dict(
        v=1,
        turn=window["turn"],
        seq=window["seq"],
        detail=window["detail"],
        source_sha256=_sha(source),
        evidence=evidence,
    )
    with store._directory(directory) as d:
        store._publish(d, ADMISSION, shared.encode(admission))
    return admission


def read_admission(directory):
    record = json.loads(shared.read_path(Path(directory) / ADMISSION, 4096))
    if (
        type(record) is not dict
        or set(record) != {"v", "turn", "seq", "detail", "source_sha256", "evidence"}
        or record["v"] != 1
        or type(record["turn"]) is not int
        or type(record["seq"]) is not int
        or not 1 <= record["turn"] < 2**31
        or not 1 <= record["seq"] < 2**31
        or record["detail"] not in _FIRST
        or record["evidence"] not in (None, *EVIDENCE)
    ):
        raise ValueError("invalid recorded hound admission")
    return record


def stage_replay(directory, recorded):
    """Before the replay game starts: the recorded game's exact source and
    the engine's window. Never a transport."""
    admission = read_admission(recorded)
    if admission["evidence"] is not None:
        evidence = Path(recorded) / admission["evidence"]
        receipt = hound_author.read_evidence(evidence)
        source = shared.read_path(evidence / "source.lua")
        if receipt["lua_source_sha256"] != _sha(source):
            raise ValueError("recorded evidence does not verify")
    else:
        source = shared.read_path(Path(recorded) / CANDIDATE)
    if _sha(source) != admission["source_sha256"]:
        raise ValueError("recorded admission does not match the source")
    due = b"%d %d\n" % (admission["turn"], admission["seq"])
    shared.publish_source(directory, due, name=DUE)
    shared.publish_source(directory, source, name=CANDIDATE)
    return admission


def verify_replay(directory, recorded):
    """After replay: the engine looked at the same bytes in the same window."""
    expected = read_admission(recorded)
    window = engine_window(directory)
    source = shared.read_path(Path(directory) / CANDIDATE)
    got = None if window is None else dict(window, source_sha256=_sha(source))
    want = {k: expected[k] for k in ("turn", "seq", "detail", "source_sha256")}
    if got != want:
        raise ValueError("replay hound window differs from the record")
    return got
