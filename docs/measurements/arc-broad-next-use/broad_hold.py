"""Broad next-use (C): slot-hold and attribution analysis. Post-run only.

Reads a seed sweep's retained per-game work dirs (``--work``). For every
admitted broad (snapshot v7) program it decodes the journal and records:

* deliveries: private effect records W_WITNESSED (3) or F_REMAPPED (12), with
  move, family, level token and the triggering whistle's sound (magic whistle
  = ``sound_strange``);
* suppressed callbacks before the first delivery (W_CAPTURE_SUPPRESSED, 2);
* terminal reason (lifecycle row) and terminal move, or open at game end.

Then per start:
1. programs with a first delivery; of those, open afterwards; moves open after
   the first delivery (to terminal, or to the game's last turn if still open);
   second delivery vs expiry vs other ends vs open at game end.
2. director ``already_published`` polls while a program was published but not
   terminal (all programs; the director log has no timestamps); completed
   whistle/fountain origins that occurred while a FELT program still held the
   slot (the publish attempts the hold deferred); games where a felt program
   held the slot to game end and no later program was published.
3. attribution of each felt program's FIRST delivery (distinct metric counts
   a program once) to the first matching C change: after a suppressed callback
   in the same program; on a level other than its admission level; magic
   whistle or fountain drink; else "single-use path" (B could have felt it).
   This is journal attribution, not a counterfactual measurement.
4. a cap-1 ESTIMATE (see estimate()).

Usage: broad_hold.py WORK_DIR [START ...] > hold.json
"""

import json
from pathlib import Path
import statistics
import sys

R = Path("/home/hermes/worktrees/NyarlatHack/hermes-session-nyarlathack-queue-2")
sys.path[:0] = [str(R)]
from chaos.next_use_journal import read_journal  # noqa: E402

DELIVERED = {3: "W", 12: "F"}
SUPPRESSED = 2
EFFECT_KIND = 4


def rows(path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def journal_name(k):
    return "next_use-journal.jsonl" if k == 1 else f"next_use-journal.{k}.jsonl"


def envelope_name(k):
    return "next_use-envelope.json" if k == 1 else f"next_use-envelope.{k}.json"


def program(run, k, events_by_seq, last_turn, lifecycle):
    path = run / journal_name(k)
    if not path.exists():
        return None
    try:
        decoded = read_journal(path)
    except Exception as exc:  # report, never rescue
        return dict(ordinal=k, journal_error=repr(exc)[:200])
    head = decoded["records"][0]["data"]["snapshot"]
    if head["snapshot_v"] != 7:
        return dict(ordinal=k, broad=False)
    admit_level = head["level_token"]
    deliveries, suppressed_before_first, last_move = [], 0, head["admission_move"]
    callbacks_before_first = 0
    trigger = (0, head["admission_move"])
    for rec in decoded["records"][1:]:
        if rec["kind"] != "transition":
            continue
        d = rec["data"]
        last_move = max(last_move, d["at_move"])
        if d["operation"] == 1:
            # ACTION: a use reached the program's callback; root is the
            # completed whistling/fountain root that triggered it.
            trigger = (d["root"], d["at_move"])
            if not deliveries:
                callbacks_before_first += 1
        for q in d["private_records"]:
            if q["kind"] != EFFECT_KIND:
                continue
            outcome = q["data"].get("outcome")
            if outcome == SUPPRESSED and not deliveries:
                suppressed_before_first += 1
            if outcome in DELIVERED:
                root, trigger_move = trigger
                origin = events_by_seq.get(root, {})
                sound = None
                if DELIVERED[outcome] == "W":
                    # the triggering whistle's notice row follows its root
                    nxt = events_by_seq.get((root or 0) + 1, {})
                    sound = nxt.get("observation", {}).get("fact")
                deliveries.append(
                    dict(
                        move=d["at_move"],
                        family=DELIVERED[outcome],
                        level=d["post"]["current_level_token"],
                        other_level=d["post"]["current_level_token"] != admit_level,
                        sound=sound,
                        origin_op=origin.get("observation", {}).get("operation"),
                        root=root,
                        trigger_move=trigger_move,
                    )
                )
    # Earlier public uses of the delivering family since admission. Under the
    # single-use rules (B) the program's first such use consumed it.
    uses_before_first = None
    if deliveries:
        first = deliveries[0]
        op = "whistling" if first["family"] == "W" else "fountain_drink"
        root = first["root"] or 0
        # Uses strictly after the admission move (the origin use precedes
        # admission) and before the delivering use.
        uses_before_first = sum(
            1
            for seq, e in events_by_seq.items()
            if seq is not None
            and seq < root
            and e.get("turn", -1) > head["admission_move"]
            and e.get("observation", {}).get("operation") == op
            and e["observation"].get("stage") == "completed"
        )
    # The delivering use's own callback precedes its delivery; exclude it.
    if deliveries:
        callbacks_before_first = max(0, callbacks_before_first - 1)
    term = lifecycle.get(k)
    end_move = None
    if term is not None:
        ev = events_by_seq.get(term["terminal_seq"])
        end_move = ev.get("turn") if ev else last_move
    return dict(
        ordinal=k,
        broad=True,
        admission_move=head["admission_move"],
        expiry=head["program_expiry"],
        uses=head["broad_uses"],
        deliveries=deliveries,
        suppressed_before_first=suppressed_before_first,
        callbacks_before_first=callbacks_before_first,
        uses_before_first=uses_before_first,
        terminal=term["reason"] if term else None,
        end_move=end_move,
        last_turn=last_turn,
    )


def game(gdir):
    run = gdir / "run"
    events = rows(run / "events.jsonl")
    by_seq = {e.get("seq"): e for e in events}
    last_turn = events[-1].get("turn") if events else None
    lifecycle = {
        r["program_ordinal"]: r for r in rows(run / "next_use-lifecycle.jsonl")
    }
    schedule = rows(run / "next_use-schedule.jsonl")
    log = (
        (run / "director.log").read_text(errors="replace").splitlines()
        if (run / "director.log").exists()
        else []
    )
    progs = [program(run, k, by_seq, last_turn, lifecycle) for k in (1, 2, 3)]
    progs = [p for p in progs if p]
    published = [k for k in (1, 2, 3) if (run / envelope_name(k)).exists()]
    return dict(
        name=gdir.name,
        last_turn=last_turn,
        programs=progs,
        published=published,
        already_published_polls=sum(x.endswith("already_published") for x in log),
        schedule_moves=[r["move"] for r in schedule],
    )


def summarise(games):
    felt, open_after, hold_moves = 0, 0, []
    second, expired, other_end, open_at_end = 0, 0, 0, 0
    deferred_origins, games_deferred, games_blocked_to_end = 0, 0, 0
    attrib = dict(
        earlier_use_reached_callback=0,
        earlier_use_no_callback=0,
        other_level=0,
        magic_whistle=0,
        fountain=0,
        single_use_path=0,
    )
    polls = 0
    for g in games:
        polls += g["already_published_polls"]
        g_deferred = 0
        for p in g["programs"]:
            if not p.get("broad") or not p["deliveries"]:
                continue
            felt += 1
            first = p["deliveries"][0]
            # First matching C change, in this order. "earlier use" = the
            # program's first use of the family was not this one, so a
            # single-use program would already have been consumed: either an
            # earlier use reached the callback undelivered (repeat use), or it
            # never reached it (no companion in view: not consumed under C).
            if p["callbacks_before_first"]:
                attrib["earlier_use_reached_callback"] += 1
            elif p["uses_before_first"]:
                attrib["earlier_use_no_callback"] += 1
            elif first["other_level"]:
                attrib["other_level"] += 1
            elif first["sound"] == "sound_strange":
                attrib["magic_whistle"] += 1
            elif first["family"] == "F":
                attrib["fountain"] += 1
            else:
                attrib["single_use_path"] += 1
            # A program closes on its last allowed delivery; with uses > 1 it is
            # always still open right after its first.
            end = p["end_move"] if p["end_move"] is not None else g["last_turn"]
            if p["uses"] > 1:
                open_after += 1
                stop = p["deliveries"][1]["move"] if len(p["deliveries"]) > 1 else end
                hold_moves.append((stop or first["move"]) - first["move"])
            if len(p["deliveries"]) >= 2:
                second += 1
            elif p["terminal"] == "program_expired":
                expired += 1
            elif p["terminal"] is None:
                open_at_end += 1
            else:
                other_end += 1
            n = sum(first["move"] < m <= end for m in g["schedule_moves"]) if end else 0
            g_deferred += n
            if p["terminal"] is None and p["ordinal"] == max(g["published"]):
                games_blocked_to_end += 1
        deferred_origins += g_deferred
        games_deferred += g_deferred > 0
    return dict(
        games=len(games),
        programs_first_delivery=felt,
        open_after_first=open_after,
        moves_open_after_first=dict(
            n=len(hold_moves),
            median=statistics.median(hold_moves) if hold_moves else None,
            max=max(hold_moves) if hold_moves else None,
        ),
        reached_second_delivery=second,
        expired_after_first=expired,
        other_end_after_first=other_end,
        open_at_game_end_after_first=open_at_end,
        director_already_published_polls=polls,
        origins_during_felt_hold=deferred_origins,
        games_with_origins_during_felt_hold=games_deferred,
        games_felt_program_held_slot_to_end=games_blocked_to_end,
        first_delivery_attribution=attrib,
    )


def main(work, starts):
    work = Path(work)
    out = {}
    for start in starts:
        dirs = sorted(d for d in work.iterdir() if d.name.rsplit("-", 1)[0] == start)
        games = [game(d) for d in dirs]
        out[start] = summarise(games)
        out[start]["journal_errors"] = sum(
            "journal_error" in p for g in games for p in g["programs"]
        )
    return out


if __name__ == "__main__":
    starts = sys.argv[2:] or [
        "bard-default-path",
        "bard",
        "bard-inherited",
        "madman",
        "wizard-default-path",
    ]
    print(json.dumps(main(sys.argv[1], starts), indent=1, sort_keys=True))
