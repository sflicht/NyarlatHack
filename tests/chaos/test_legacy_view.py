"""#1: legacy readers see exactly what they saw before door_reluctance.

door_reluctance lives in additive contract sections (telegraph_extensions,
mutation_limits). The frozen v1 view and the frozen shared block must be
unchanged, and every committed historical log must still validate.
"""

import json
from pathlib import Path
import subprocess
import unittest

from chaos import protocol
from chaos._protocol_contract import DURATION_CAP, LEGACY, TELEGRAPHS
from test_director import ack, event

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = "c00029de0ef54bf89dc0d283b8e4f0fc365beb11:chaos/protocol_contract.json"
DOOR = dict(
    v=1,
    id=1,
    mutation="door_reluctance",
    value=50,
    duration=300,
    telegraph=4,
    at=1,
)


def baseline():
    return json.loads(subprocess.check_output(["git", "show", ORIGINAL], cwd=ROOT))


class LegacyView(unittest.TestCase):
    def test_frozen_v1_view_is_unchanged(self):
        base = baseline()
        data = json.loads((ROOT / "chaos/protocol_contract.json").read_text())
        # The generated legacy view equals the original contract's subtree.
        self.assertEqual(LEGACY, {k: base[k] for k in LEGACY})
        self.assertEqual(
            protocol.LEGACY_REGISTRY,
            {
                "ambient": (1, 100, 1),
                "ward_efficacy": (4, 80, 2),
                "hunger_rate": (3, 90, 3),
            },
        )
        self.assertNotIn("door_reluctance", protocol.LEGACY_REGISTRY)
        # Shared telegraphs and the 50-turn headroom are byte-identical.
        self.assertEqual(data["telegraphs"], base["telegraphs"])
        self.assertEqual(data["limits"], base["limits"])
        self.assertEqual(data["limits"]["admission_turn_headroom"], 50)
        # The additions are visible only through the new sections.
        self.assertEqual(
            data["telegraph_extensions"],
            [dict(id=4, text="The doors of this place seem to lean against you.")],
        )
        self.assertEqual(data["mutation_limits"], dict(duration_cap=300))
        self.assertEqual(DURATION_CAP, 300)
        self.assertEqual(sorted(TELEGRAPHS), [1, 2, 3, 4])
        for row in base["telegraphs"]:
            self.assertEqual(TELEGRAPHS[row["id"]], row["text"])

    def test_committed_historical_logs_still_validate(self):
        paths = sorted((ROOT / "docs/evidence").rglob("events.jsonl"))
        self.assertGreaterEqual(len(paths), 10)
        rows = 0
        for path in paths:
            for line in path.read_bytes().splitlines():
                with self.subTest(path=str(path.relative_to(ROOT))):
                    protocol.parse_event(line)
                rows += 1
        self.assertGreater(rows, 100)
        for path in sorted((ROOT / "docs/evidence").rglob("whispers.jsonl")):
            for line in path.read_bytes().splitlines():
                row = json.loads(line)
                if row.get("id"):
                    protocol.parse_request(
                        protocol.encode_request(protocol.event_request(row))
                    )

    def test_frozen_random_choices_still_parse(self):
        expected = json.loads(
            (ROOT / "tests/chaos/protocol_legacy_baseline.json").read_text()
        )
        for encoded in expected["random"]:
            self.assertEqual(
                protocol.encode_request(protocol.parse_request(encoded)),
                encoded.encode(),
            )

    def test_legacy_rows_cannot_name_the_new_kind(self):
        # A v1 ack naming a v1 kind still validates as before ...
        self.assertEqual(protocol.parse_event(json.dumps(ack())), ack())
        # ... but a v1 row can never carry door_reluctance: it did not exist.
        row = ack(request=DOOR, expires=301)
        with self.assertRaises(ValueError):
            protocol.parse_event(json.dumps(row))
        # A v1 event envelope is otherwise unchanged.
        self.assertEqual(protocol.parse_event(json.dumps(event())), event())

    def test_current_reader_accepts_the_new_kind_within_its_own_bounds(self):
        self.assertEqual(protocol.parse_request(json.dumps(DOOR).encode()), DOOR)
        for bad in (
            dict(DOOR, duration=301),
            dict(DOOR, duration=0),
            dict(DOOR, telegraph=1),
            dict(DOOR, value=49),
            dict(DOOR, mutation="hunger_rate", value=2, telegraph=3, duration=51),
            dict(DOOR, mutation="ward_efficacy", telegraph=2, duration=51),
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                protocol.parse_request(json.dumps(bad).encode())


if __name__ == "__main__":
    unittest.main()
