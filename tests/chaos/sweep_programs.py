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

    programs, felt, effects_by_root = [], [], {}
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

    def add(turn, kind, program=None, dlvl=None):
        felt.append(
            dict(
                turn=turn,
                dlvl=dlvl if dlvl is not None else dlvl_at(timeline, turn),
                kind=kind,
                program=program,
            )
        )
        if program is not None:
            programs[program - 1]["felt"] += 1

    door_until = None
    hunger_windows = []
    for e in events:
        if e["event"] == "ack" and e.get("status") == "accepted":
            if e.get("mutation") == "door_reluctance":
                door_until = e["expires"]
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
                add(e["turn"], "door")
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
            add(first["turn"], "hunger", dlvl=first.get("dlvl"))
    felt.sort(key=lambda e: (e["turn"], e["kind"], e["program"] or 0))
    return {"programs": programs, "felt_events": felt}
