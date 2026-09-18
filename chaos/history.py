"""Checked mixed history for the bounded fountain pilot; NGPL, see dat/license.

Admissions are native ACK evidence, not proof of witnessed rule application.
Source checks establish a local prefix at a read instant, not authenticity.
"""

from collections import deque
import json

from .director import DEFAULT_BYTES, DEFAULT_EVENTS, State, eligible
from .episodes import _snapshot_projection, parse_episode_event, project_episodes
from .protocol import MAX_INT, REGISTRY, LEGACY_REGISTRY, VITALS, encode_request

PUBLIC_CONTEXT_BYTES = 6144  # Leave room in the 8192-byte model input for its menu.
PRIOR_LIMIT = 3


class IncompleteHistory(ValueError):
    """Bounded empty or unfinished bytes; never usable partial evidence."""


def _complete(raw):
    if not isinstance(raw, bytes):
        raise ValueError("native bytes required")
    if len(raw) > DEFAULT_BYTES or raw.count(b"\n") > DEFAULT_EVENTS:
        raise ValueError("native history cap exceeded")
    tail = raw.rsplit(b"\n", 1)[-1]
    if len(tail) > 4096:
        raise ValueError("event line exceeds byte cap")
    if not raw or tail:
        prefix = raw[: len(raw) - len(tail)]
        if prefix:
            # Invalid complete evidence must not be hidden by a partial suffix.
            HistoryState(prefix)
        if tail:
            try:
                json.loads(tail)
            except (UnicodeError, RecursionError) as exc:
                raise ValueError("invalid unfinished encoding") from exc
            except json.JSONDecodeError:
                pass
            else:
                parse_episode_event(tail)
        raise IncompleteHistory("complete nonempty native bytes required")


class HistoryState:
    """A single fully validated prefix, with a contained unmodified v1 consumer."""

    def __init__(self, raw: bytes):
        _complete(raw)
        self.episodes = project_episodes(raw)
        self._legacy = State()
        self.enabled = False
        marker = False
        roots = deque(maxlen=32)
        admissions = {}
        pending_expiry = {}
        for line in raw.split(b"\n")[:-1]:
            row = parse_episode_event(line)
            self.latest = row
            if row["v"] in (2, 4):
                payload = row["observation"]
                stage = payload["stage"]
                if stage == "enabled":
                    marker = True
                elif stage == "started":
                    roots.append(
                        dict(operation=payload["operation"], fact=None, completed=False)
                    )
                elif stage == "notice":
                    roots[-1]["fact"] = payload["fact"]
                elif stage == "completed":
                    roots[-1]["completed"] = True
                continue
            if row["event"] == "session":
                self.enabled, marker = marker, False
                roots.clear()
            if row["event"] == "ack" and row["status"] == "accepted":
                name = row["mutation"]
                expires = row["turn"] + row["duration"] if row["duration"] else 0
                if (
                    row["phase"] != "result"
                    or row["last_id"] != row["id"]
                    or row["at"] != row["safe"]
                    or row["cost"]
                    != (LEGACY_REGISTRY if row["v"] == 1 else REGISTRY)[name][0]
                    or row["expires"] != expires
                ):
                    raise ValueError("inconsistent accepted acknowledgement")
                if row["id"] in admissions:
                    raise ValueError("repeated accepted acknowledgement")
                if name in pending_expiry:
                    raise ValueError("acceptance without previous native expiry")
                admission = dict(
                    id=row["id"],
                    mutation=name,
                    duration=row["duration"],
                    accepted_seq=row["seq"],
                    accepted_turn=row["turn"],
                    expires_turn=expires,
                    active_at_snapshot=False,
                    expiry_observed=False,
                )
                admissions[row["id"]] = admission
                if row["duration"]:
                    pending_expiry[name] = admission
            elif row["event"] == "expiry":
                admission = pending_expiry.get(row["detail"])
                if (
                    row["phase"] != "result"
                    or admission is None
                    or row["turn"] < admission["expires_turn"]
                ):
                    raise ValueError("invalid native expiry linkage")
                admission["expiry_observed"] = True
                del pending_expiry[row["detail"]]
            self._legacy.ingest(row)
        self._qualifying = any(
            root["operation"] == "fountain_drink"
            and root["fact"] == "water_refreshed"
            and root["completed"]
            for root in roots
        )
        for admission in admissions.values():
            admission["active_at_snapshot"] = (
                admission["expires_turn"] > self.latest["turn"]
                and not admission["expiry_observed"]
            )
        self.prior_whispers = list(admissions.values())[-PRIOR_LIMIT:]
        self.prior_coverage = dict(
            shown=len(self.prior_whispers),
            omitted=len(admissions) - len(self.prior_whispers),
        )

    @property
    def safe(self):
        return self.latest["safe"]

    @property
    def last_id(self):
        return self.latest["last_id"]

    @property
    def ended(self):
        return self._legacy.ended

    @property
    def acks(self):
        return self._legacy.acks

    @property
    def accepted(self):
        return self._legacy.accepted

    @property
    def accepted_receipts(self):
        return self._legacy.accepted_receipts

    @property
    def active(self):
        return {
            name: expiry
            for name, expiry in self._legacy.active.items()
            if expiry > self.latest["turn"]
        }

    def summary(self):
        summary = json.loads(self._legacy.summary())
        observed = {
            key: self.latest[key]
            for key in (
                "turn",
                "safe",
                "sanity",
                "insight",
                "budget",
                "spent",
                "reserved",
            )
        }
        if "vitals" in self.latest:
            observed["vitals"] = {key: self.latest["vitals"][key] for key in VITALS}
        summary["observed"] = observed
        return json.dumps(summary, ensure_ascii=True, separators=(",", ":"))


def snapshot_history(path, *, checkpoint=None):
    """Return (HistoryState, host proof) from the same checked native bytes."""
    return _snapshot_projection(path, HistoryState, checkpoint=checkpoint)


def candidate_requests(state, ordinary_food=False):
    """Exact host-owned menu; one completed refresh suffices in 32 roots."""
    if type(state) is not HistoryState or type(ordinary_food) is not bool:
        raise ValueError(
            "checked history and boolean ordinary-food affirmation required"
        )
    if (
        not state.enabled
        or not state._qualifying
        or any(
            request["mutation"] == "hunger_rate" for request in state.accepted.values()
        )
        or "hunger_rate" not in eligible(state, ordinary_food)
        or state.last_id == MAX_INT
        or state.safe == MAX_INT
    ):
        return []
    requests = [
        dict(
            v=1,
            id=state.last_id + 1,
            at=state.safe + 1,
            mutation="hunger_rate",
            value=2,
            duration=duration,
            telegraph=3,
        )
        for duration in (10, 20)
    ]
    for request in requests:
        encode_request(request)
    return requests


def public_context(state):
    """Allowlisted model context only; no checkpoint or arbitrary native extras."""
    if type(state) is not HistoryState:
        raise ValueError("checked history required")
    from .next_use_history import eligible_families, next_use_menu

    public = dict(
        history_context_v=1,
        summary=json.loads(state.summary()),
        episodes=state.episodes,
        prior_whispers=state.prior_whispers,
        prior_coverage=state.prior_coverage,
        next_use=dict(
            families=list(eligible_families(state)),
            menu=next_use_menu(state),
        ),
    )
    encoded = json.dumps(public, ensure_ascii=True, separators=(",", ":"))
    if len(encoded.encode("ascii")) > PUBLIC_CONTEXT_BYTES:
        raise ValueError("history context byte cap exceeded")
    return json.loads(encoded)
