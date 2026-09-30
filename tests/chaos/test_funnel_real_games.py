"""#178: sweep_funnel's later stages checked against two real delivering games.

The fixtures under funnel_fixtures/ are trimmed from two games of the
committed v2 report (docs/measurements/seed-sweep-v2-179/), replayed at the
report's revision with the exact v2 command and found identical to it:

- bard seed 40: a next-use W program delivered (whistle attention seen);
- bard-default-path seed 21: an early echo hound, then a delivered W program.

No F (fountain) program delivered anywhere in the v2 report, so there is no
real F fixture. The hash-chained journal cannot be trimmed without breaking
its chain, so each fixture keeps the private records decoded from every
journal record (header and transitions, as sweep_funnel reads them) and the
source journal's sha256; read_journal is replaced by those records.
"""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sweep_funnel  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "funnel_fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def _analyse(fx):
    with tempfile.TemporaryDirectory() as tmp:
        run = Path(tmp) / "run"
        run.mkdir()

        def lines(rows):
            return "".join(json.dumps(r) + "\n" for r in rows)

        (run / "events.jsonl").write_text(lines(fx["events"]))
        (run / "next_use-schedule.jsonl").write_text(lines(fx["schedule"]))
        (run / "next_use-envelope.json").write_text(json.dumps(fx["envelope"]))
        (run / "next_use-receipt.jsonl").write_text(lines(fx["receipts"]))
        (run / "director.log").write_text("".join(d + "\n" for d in fx["director"]))
        (run / "whispers.jsonl").write_text(lines(fx["whispers"]))
        (run / "next_use-journal.jsonl").write_text("")
        decoded = {
            "status": fx["source"]["journal_status"],
            "records": [
                {
                    "kind": "transition",
                    "data": {"private_records": fx["private_records"]},
                }
            ],
        }
        with mock.patch.object(sweep_funnel, "read_journal", return_value=decoded):
            return sweep_funnel.analyse(tmp, felt=True)


RUNTIME_H = Path(__file__).resolve().parents[2] / "include" / "chaos_next_use_runtime.h"


def _engine_outcomes():
    """enum chaos_next_use_effect_outcome from the engine header, by name."""
    text = RUNTIME_H.read_text()
    body = re.search(r"enum chaos_next_use_effect_outcome \{(.*?)\};", text, re.S)
    names = [n.split("=")[0].strip() for n in body.group(1).split(",") if n.strip()]
    first = int(re.search(r"=\s*(\d+)", body.group(1)).group(1))
    return {n: first + i for i, n in enumerate(names)}


class RealDeliveringGames(unittest.TestCase):
    def test_outcome_codes_match_engine(self):
        # Both real games end [1, 3, 4] (armed, witnessed, ended after
        # witness), so a delivered code of 4 would count the same; pin the
        # analyser's codes to the engine enum instead.
        engine = _engine_outcomes()
        self.assertEqual(sweep_funnel.W_ARMED, engine["CHAOS_EFFECT_W_ARMED"])
        self.assertEqual(
            sweep_funnel.W_CAPTURE_SUPPRESSED,
            engine["CHAOS_EFFECT_W_CAPTURE_SUPPRESSED"],
        )
        self.assertEqual(sweep_funnel.W_WITNESSED, engine["CHAOS_EFFECT_W_WITNESSED"])
        self.assertEqual(sweep_funnel.F_REMAPPED, engine["CHAOS_EFFECT_F_REMAPPED"])

    def delivered_at_notice(self, fx):
        """The witnessed effect row falls on the turn of the public notice."""
        rows = [
            p["at_move"]
            for p in fx["private_records"]
            if p["kind"] == 4 and p["data"]["outcome"] == sweep_funnel.W_WITNESSED
        ]
        notices = [
            e["turn"]
            for e in fx["events"]
            if e.get("observation", {}).get("operation") == "whistle_attention"
            and e["observation"]["stage"] == "notice"
        ]
        self.assertEqual(rows, notices)

    def check(self, name):
        fx = _load(name)
        a = _analyse(fx)
        # The whole per-game entry the committed report holds (minus the
        # sweep-added Dlvl, which needs the status-line timeline).
        self.assertEqual(a, fx["expected"])
        # Hand-checked stages, from the raw rows rather than the analyser.
        private = fx["private_records"]
        effects = [p["data"]["outcome"] for p in private if p["kind"] == 4]
        self.assertEqual(sum(p["kind"] == 3 for p in private), a["counts"]["trigger"])
        self.assertEqual(effects.count(1), a["counts"]["native_effect"])  # W armed
        self.assertEqual(effects.count(3), a["counts"]["delivered"])  # W witnessed
        return fx, a

    def test_bard_40_next_use_w_delivered(self):
        fx, a = self.check("v2-bard-40.json")
        self.delivered_at_notice(fx)
        c = a["counts"]
        self.assertEqual((c["trigger"], c["native_effect"], c["delivered"]), (1, 1, 1))
        self.assertIsNone(a["loss"])
        # First felt = the attention notice the player sees (turn 200), not
        # the whistle that armed it (turn 195).
        self.assertEqual(a["first_felt"], {"turn": 200, "kind": "next_use_W"})
        notice = [
            e["turn"]
            for e in fx["events"]
            if e.get("observation", {}).get("operation") == "whistle_attention"
            and e["observation"]["stage"] == "notice"
        ]
        self.assertEqual(notice, [200])

    def test_default_path_21_hound_then_w_delivered(self):
        fx, a = self.check("v2-bard-default-path-21.json")
        self.delivered_at_notice(fx)
        c = a["counts"]
        self.assertEqual((c["trigger"], c["native_effect"], c["delivered"]), (1, 1, 1))
        # The hound's first visible step (turn 7) precedes the W notice (344).
        self.assertEqual(a["first_felt"], {"turn": 7, "kind": "hound"})
        self.assertEqual(a["haunt_steps"], 2)
        self.assertEqual(a["haunt"], {"accepted": 1, "expired": 1, "pre_admitted": 1})


if __name__ == "__main__":
    unittest.main()
