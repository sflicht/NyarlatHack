"""#1 door_open: excluded from the next-use lookback and episode summary.

A door attempt is a v4 observation root like any other (strictly checked
chronology), but it must never occupy or evict one of the 32 bounded roots
that next-use origins and the public episode summary are drawn from.
"""

import json
import unittest

from chaos.episodes import project_episodes
from chaos.history import HistoryState
from chaos.next_use_history import eligible_families, next_use_menu
from current_history_fixtures import current_action, current_history_rows


def wire(rows):
    return "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows).encode()


def with_doors(n, fact="resisted"):
    rows = current_history_rows()
    for i in range(n):
        current_action(rows, "door_open", "opened" if i % 2 else fact)
    return rows


class DoorLookbackTests(unittest.TestCase):
    def test_door_roots_parse_and_are_strict(self):
        project_episodes(wire(with_doors(2)))
        for bad in ("water_refreshed", "none"):
            with self.subTest(fact=bad), self.assertRaises(ValueError):
                project_episodes(wire(with_doors(1, bad)))
        rows = current_history_rows()
        current_action(rows, "door_open", "resisted", terminal="blocked")
        with self.assertRaises(ValueError):  # door_open never blocks
            project_episodes(wire(rows))

    def test_many_doors_never_evict_the_fountain_origin(self):
        base = HistoryState(wire(current_history_rows()))
        for n in (0, 1, 40):
            with self.subTest(doors=n):
                state = HistoryState(wire(with_doors(n)))
                self.assertEqual(eligible_families(state), eligible_families(base))
                self.assertEqual(eligible_families(state), ("F",))
                self.assertEqual(next_use_menu(state), next_use_menu(base))
                self.assertEqual(state.episodes, base.episodes)
                self.assertEqual(state._next_use_roots, base._next_use_roots)

    def test_door_roots_are_not_in_the_public_summary(self):
        summary = project_episodes(wire(with_doors(5)))
        self.assertEqual(
            [g["operation"] for g in summary["episodes"]], ["fountain_drink"]
        )
        self.assertEqual(summary["coverage"]["omitted_roots"]["count"], 0)


if __name__ == "__main__":
    unittest.main()
