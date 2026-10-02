"""V2-only, post-run metrics. Never used to steer the scripted player/director."""

from chaos.next_use_envelope import envelope_name


def program_metrics(run, events, receipts, timeline=(), statuses=()):
    from sweep_funnel import (
        dlvl_at,
        read_journal,
        JournalError,
        TERMINATION,
        _rows,
        W_ARMED,
        W_WITNESSED,
        F_REMAPPED,
    )

    programs, felt, effects_by_root, effect_keys = [], [], {}, {}
    # New runs project witnessed/remapped outcomes into a bounded public file.
    # Historical W journals carry the same public witness; historical F has no
    # such public attribution and is not guessed from private effect timing.
    for row in _rows(run / "next_use-felt.jsonl"):
        if (
            row.get("next_use_felt_v") == 1
            and type(row.get("program_ordinal")) is int
            and row["program_ordinal"] in (1, 2, 3)
            and row.get("family") in (1, 2)
            and type(row.get("root_seq")) is int
            and row["root_seq"] > 0
        ):
            effects_by_root[(row["family"], row["root_seq"])] = row["program_ordinal"]
    for ordinal in (1, 2, 3):
        name = (
            "next_use-journal.jsonl"
            if ordinal == 1
            else f"next_use-journal.{ordinal}.jsonl"
        )
        path = run / name
        private, public = [], []
        status = "missing"
        if path.exists():
            try:
                trace = read_journal(path)
                header = trace["records"][0]["data"]
                if header.get("program_ordinal", 1) != ordinal:
                    raise JournalError("journal ordinal mismatch")
                status = trace["status"]
                for row in trace["records"]:
                    private.extend(row["data"].get("private_records", ()))
                    public.extend(row["data"].get("public_records", ()))
            except JournalError as exc:
                status = "invalid: " + str(exc)[:80]
                private, public = [], []
        own = [r for r in receipts if r.get("program_ordinal", 1) == ordinal]
        admitted = int(any(r.get("kind") == 2 for r in own + private))
        effects = [r for r in private if r["kind"] == 4]
        delivered = [
            r for r in effects if r["data"]["outcome"] in (W_WITNESSED, F_REMAPPED)
        ]
        terminated = [r for r in private if r["kind"] == 5]
        rejected = [r for r in own if r.get("decision") == "rejected"]
        termination = (
            TERMINATION.get(terminated[-1]["data"]["reason"], "unknown")
            if terminated
            else None
        )
        if rejected and not admitted:
            termination = "rejected:" + "+".join(rejected[-1]["reasons"])
        published = (run / envelope_name(ordinal)).exists()
        programs.append(
            dict(
                program=ordinal,
                published=int(published),
                admitted=admitted,
                trigger=sum(r["kind"] == 3 for r in private),
                native_effect=sum(
                    r["data"]["outcome"] in (W_ARMED, F_REMAPPED) for r in effects
                ),
                delivered=len(delivered),
                felt=0,
                termination=termination,
                journal_status=status,
                delivery_known=not admitted
                or bool(delivered)
                or status == "structurally_complete",
            )
        )
        # Attribute by public action root, NOT envelope id (ids may repeat),
        # private replay sequence (not event seq), or monster move (not turn).
        for row in public:
            effects_by_root[(row["family"], row["root"])] = ordinal

    def add(turn, kind, program=None, dlvl=None, effect=None):
        row = dict(
            turn=turn,
            dlvl=dlvl if dlvl is not None else dlvl_at(timeline, turn),
            kind=kind,
            program=program,
        )
        felt.append(row)
        # Door/hunger: public turn of the accepted ack that opened the effect.
        # Kept beside, not inside, the row so felt_events keep their shape.
        effect_keys[id(row)] = effect
        if program is not None:
            programs[program - 1]["felt"] += 1

    door_until = door_start = None
    hunger_windows = []
    for e in events:
        if e["event"] == "ack" and e.get("status") == "accepted":
            if e.get("mutation") == "door_reluctance":
                door_until, door_start = e["expires"], e["turn"]
            elif e.get("mutation") == "hunger_rate":
                # A newer activation replaces the old one, even before expiry.
                if hunger_windows:
                    hunger_windows[-1][1] = min(hunger_windows[-1][1], e["turn"])
                hunger_windows.append([e["turn"], e["expires"]])
        elif e["event"] == "expiry":
            if e.get("detail") == "door_reluctance":
                door_until = None
            elif e.get("detail") == "hunger_rate" and hunger_windows:
                hunger_windows[-1][1] = min(hunger_windows[-1][1], e["turn"])
        o = e.get("observation", {})
        if e["event"] == "haunt_step":
            add(e["turn"], "hound")
        elif o.get("stage") == "notice":
            op, fact, root = o["operation"], o.get("fact"), o["root_seq"]
            if op == "whistle_attention" and fact == "attention":
                add(e["turn"], "next_use_W", effects_by_root.get((1, root)))
            elif (
                op == "door_open"
                and fact == "resisted"
                and door_until is not None
                and e["turn"] < door_until
            ):
                add(e["turn"], "door", effect=door_start)
            elif op == "fountain_drink" and (2, root) in effects_by_root:
                # Exactly one visible remap result per action, not every notice.
                ordinal = effects_by_root.pop((2, root))
                add(e["turn"], "next_use_F", ordinal)
    for start, end in hunger_windows:
        first = next(
            (
                s
                for s in statuses
                if start <= s["turn"] < end and s["hunger"] == "Hungry"
            ),
            None,
        )
        if first is not None:
            add(first["turn"], "hunger", dlvl=first.get("dlvl"), effect=start)
    felt.sort(key=lambda e: (e["turn"], e["kind"], e["program"] or 0))
    return {
        "programs": programs,
        "felt_events": felt,
        "distinct_felt": distinct_felt(felt, [effect_keys[id(e)] for e in felt]),
    }


# Arc metric (Sam, after #229): "distinct felt whispers" per game. Computed
# from public felt_events only; it never changes them or the raw 2+ figure.
DOOR_DURATION_CAP = 300  # contract door_reluctance duration bound
DISTINCT_KINDS = ("hound", "next_use", "door", "hunger")


def distinct_felt(felt_events, effects=None):
    """First felt event of each distinct source, in turn order.

    - hound: at most once per game (its first visible step);
    - next-use: at most once per program, W or F (first felt event); rows
      with no public program attribution (historical runs) are one source;
    - door: once per accepted effect (first visible resistance);
    - hunger: once per accepted effect (first Hungry in its window).

    ``effects`` (live analysis only) gives, per row, the public turn of the
    accepted ack that opened a door/hunger effect. Without it (post hoc on
    older reports), a hunger row is already one per window, and door rows are
    grouped by the contract's 300-turn duration cap from the group's first
    row; that can merge two short back-to-back door effects (a lower bound).
    """
    if effects is None:
        effects = [None] * len(felt_events)
    out, seen, door_group = [], set(), None
    rows = sorted(zip(felt_events, effects), key=lambda pair: pair[0]["turn"])
    for e, effect in rows:
        kind = e["kind"]
        if kind == "hound":
            key = ("hound",)
        elif kind in ("next_use_W", "next_use_F"):
            key = ("next_use", e.get("program"))
        elif kind == "door":
            if effect is not None:
                key = ("door", effect)
            else:
                if door_group is None or e["turn"] - door_group >= DOOR_DURATION_CAP:
                    door_group = e["turn"]
                key = ("door", "cap", door_group)
        elif kind == "hunger":
            key = ("hunger", effect if effect is not None else e["turn"])
        else:
            raise ValueError(f"unknown felt kind {kind!r}")
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(turn=e["turn"], kind=key[0]))
    return out
