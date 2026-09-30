"""#180: alert rules for the scheduled seed sweep (scripts/sweep_alert.py)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import sweep_alert  # noqa: E402

V2 = ROOT / "docs/measurements/seed-sweep-v2-179/baseline-v2-seeds-1-100.json"


def game(start="bard", seed=1, **kw):
    g = {
        "start": start,
        "seed": seed,
        "outcome": "died",
        "error": None,
        "exit_code": 0,
        "sync_timeouts": 0,
        "save_restore": {"attempted": True, "session_detail": "restore"},
    }
    g.update(kw)
    return g


FOLLOW = 'AssertionError: b\'"I don\\\'t know you.""Please follow me."\''


class Check(unittest.TestCase):
    def test_committed_v2_report_is_clean(self):
        games = json.loads(V2.read_text())["games"]
        self.assertEqual(sweep_alert.problems(games), [])
        self.assertEqual(sum(1 for g in games if sweep_alert.known(g)), 2)

    def test_known_errors_need_start_seed_and_text(self):
        ok = game(seed=48, outcome="harness_error", error=FOLLOW, exit_code=None)
        self.assertEqual(sweep_alert.problems([ok]), [])
        for other in (
            game(seed=49, outcome="harness_error", error=FOLLOW),
            game(start="madman", seed=48, outcome="harness_error", error=FOLLOW),
            game(seed=48, outcome="harness_error", error="AssertionError: other"),
        ):
            with self.subTest(other=other):
                (line,) = sweep_alert.problems([other])
                self.assertIn("new harness error", line)

    def test_each_alert_kind(self):
        cases = {
            "nonzero exit 139": game(exit_code=139),
            "director sync timeout": game(sync_timeouts=1),
            "restore failed": game(
                save_restore={"attempted": True, "session_detail": None}
            ),
        }
        for text, g in cases.items():
            with self.subTest(text=text):
                (line,) = sweep_alert.problems([g])
                self.assertIn(text, line)

    def test_measurements_do_not_alert(self):
        quiet = [
            game(outcome="turn_limit"),
            game(outcome="died"),
            game(save_restore={"attempted": False, "session_detail": None}),
        ]
        self.assertEqual(sweep_alert.problems(quiet), [])


class Compare(unittest.TestCase):
    def test_identical_and_subset(self):
        first = [game(seed=1), game(seed=2)]
        self.assertEqual(sweep_alert.differences(first, [game(seed=2)]), [])

    def test_difference_and_missing(self):
        first = [game(seed=1)]
        second = [game(seed=1, outcome="turn_limit"), game(seed=3)]
        lines = sweep_alert.differences(first, second)
        self.assertEqual(len(lines), 2)
        self.assertIn("differs in outcome", lines[0])
        self.assertIn("missing", lines[1])

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.json", Path(tmp) / "b.json"
            a.write_text(json.dumps({"games": [game()]}))
            b.write_text(json.dumps({"games": [game(exit_code=1)]}))
            self.assertEqual(sweep_alert.main(["check", str(a)]), 0)
            self.assertEqual(sweep_alert.main(["check", str(b)]), 1)
            self.assertEqual(sweep_alert.main(["compare", str(a), str(a)]), 0)
            self.assertEqual(sweep_alert.main(["compare", str(a), str(b)]), 1)


if __name__ == "__main__":
    unittest.main()
