"""Does the host rehearsal reproduce the engine's shadow trial? (NGPL)

Runs HoundValidator.rehearse on footsteps.lua and the 18 retained #251
sources in the three bare rooms and compares moved, contacts, min_dist and
median_dist with the engine's own reports in baseline/trials.json (seed 1;
the engine's bare-room reports do not vary by seed). Prints one line per
mismatch and a summary; writes fidelity.json next to this file.

  fidelity.py <curio-validator.so>
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "docs/measurements/hound-free-pilot"))

from chaos import hound_author  # noqa: E402

import measure  # noqa: E402
import pilot  # noqa: E402

FIELDS = ("moved", "contacts", "min_dist", "median_dist", "escaped")


def main():
    v = hound_author.HoundValidator(Path(sys.argv[1]).absolute())
    engine = json.loads((HERE / "baseline/trials.json").read_text())
    sources = {"footsteps": pilot.FOOTSTEPS.read_bytes(), **measure.sources_of(measure.OLD)}
    rows, mismatches = [], 0
    for name, source in sources.items():
        for room in hound_author.REHEARSAL_ROOMS:
            host = v.rehearse(source, room)
            eng = next(
                t["report"]
                for t in engine[name]["trials"]
                if t["room"] == room[0] and t["seed"] == 1
            )
            diff = {f: (host[f], eng[f]) for f in FIELDS if host[f] != eng[f]}
            mismatches += bool(diff)
            if diff:
                print("MISMATCH", name, room[0], diff)
            rows.append(dict(source=name, room=room[0], host=host, engine={f: eng[f] for f in FIELDS}))
    (HERE / "fidelity.json").write_text(json.dumps(rows, indent=1) + "\n")
    print(f"{len(rows)} rehearsals, {mismatches} differ from the engine")


if __name__ == "__main__":
    main()
