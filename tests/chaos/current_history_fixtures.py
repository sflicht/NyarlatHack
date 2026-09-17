"""Independent synthetic current-policy history, never native evidence."""

from test_director import current_event


def current_action(
    rows, operation="fountain_drink", fact="water_refreshed", terminal="completed"
):
    root = len(rows) + 1
    for stage, notice in (("started", "none"), ("notice", fact), (terminal, "none")):
        rows.append(
            current_event(
                len(rows) + 1,
                v=4,
                sanity=70,
                budget=6,
                event="observation",
                detail="",
                phase="attempt" if stage == "started" else "result",
                vitals=dict(hp=7, hp_max=20, power=2, power_max=10),
                observation=dict(
                    operation=operation,
                    stage=stage,
                    root_seq=0 if stage == "started" else root,
                    fact=notice,
                ),
            )
        )


def current_history_rows(fact="water_refreshed"):
    rows = [
        current_event(
            1,
            v=4,
            safe=0,
            sanity=70,
            budget=6,
            event="observation",
            detail="",
            vitals=dict(hp=7, hp_max=20, power=2, power_max=10),
            observation=dict(
                operation="none", stage="enabled", root_seq=0, fact="none"
            ),
        ),
        current_event(
            2,
            safe=0,
            sanity=70,
            budget=6,
            event="session",
            detail="new",
            private="SECRET",
        ),
    ]
    current_action(rows, fact=fact)
    return rows
