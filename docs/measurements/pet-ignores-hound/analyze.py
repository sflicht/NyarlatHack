"""Pets never attack the echo hound: before/after summary.

usage: analyze.py RESULTS.jsonl  -> prints JSON {main: ..., head: ...}

Attribution is #201's (`before_after.py`): "You kill echo hound" is the
player; "<pet> kills echo hound", "Echo hound is killed!" and a pet eating a
corpse "named echo hound" are the pet; otherwise expired alive / alive at
end. A `haunting`/`killed` event with no attributable message counts as
"killed, unattributed". Life = turn of death minus admission turn (60 when it
expired alive or was alive at the end). Bootstrap 95% interval on the mean of
live steps, seed 1, 4000 resamples.
"""

import collections
import json
import random
import re
import statistics
import sys


def killer(x):
    for t in x["trace"]:
        m = t["msg"] or ""
        if re.search(r"You (?:kill|destroy) (?:the )?echo hound", m):
            return "player", t["turn"]
        if re.search(r"(?:kills|destroys) (?:the )?echo hound", m):
            return "pet", t["turn"]
        if re.search(r"[Ee]cho hound is (?:killed|destroyed)", m):
            return "pet", t["turn"]
        if re.search(r"eats? .*named echo hound", m):
            return "pet", t["turn"]
    if x.get("kill"):
        return ("player" if x["kill"].startswith("You") else "pet"), None
    if x.get("killed_event"):
        return "killed, unattributed", x["killed_event"][0]
    return ("expired alive" if x.get("expired") else "alive at end"), None


def summ(rows):
    adm = [x for x in rows if x.get("accepted_turn")]
    steps = [len(x["steps"]) for x in adm]
    who, life = collections.Counter(), []
    for x in adm:
        k, t = killer(x)
        who[k] += 1
        life.append((t - x["accepted_turn"]) if t is not None else 60)
    random.seed(1)
    bs = (
        sorted(
            statistics.mean(random.choices(steps, k=len(steps))) for _ in range(4000)
        )
        if steps
        else [0] * 4000
    )
    dist = collections.Counter(min(s, 10) for s in steps)
    return dict(
        games=len(rows),
        errors=sum(1 for x in rows if x.get("error")),
        hound_lane=sum(1 for x in rows if x.get("hound_lane")),
        admitted=len(adm),
        rejected=sum("rejected" in (x.get("haunting") or []) for x in rows),
        undecided=sum(1 for x in rows if not x.get("error") and not x.get("haunting")),
        steps_median=statistics.median(steps) if steps else None,
        steps_mean=round(statistics.mean(steps), 2) if steps else None,
        steps_mean_ci95=[round(bs[100], 2), round(bs[3899], 2)],
        steps_distribution={
            ("10+" if k == 10 else str(k)): v for k, v in sorted(dist.items())
        },
        lived_10_plus=sum(v >= 10 for v in life),
        life_median=statistics.median(life) if life else None,
        who=dict(who),
        pet_hits_hound=sum(x.get("pet_hits_hound", 0) for x in adm),
        hound_hits_pet=sum(x.get("hound_hits_pet", 0) for x in adm),
        hound_hits_you=sum(x.get("hound_hits_you", 0) for x in adm),
        accepted_turn_median=(
            statistics.median(x["accepted_turn"] for x in adm) if adm else None
        ),
    )


rows = [json.loads(line) for line in open(sys.argv[1]) if line.strip()]
print(
    json.dumps(
        {t: summ([x for x in rows if x["tree"] == t]) for t in ("main", "head")},
        indent=1,
    )
)
