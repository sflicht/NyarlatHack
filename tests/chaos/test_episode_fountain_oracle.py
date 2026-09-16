"""Build-free SYNTHETIC contract tests; never native acceptance evidence."""

import copy
import json
from pathlib import Path
import subprocess
import unittest

import test_episode_fountain as driver
from chaos.episodes import parse_episode_event, project_episodes


CONTEXT = dict(
    turn=101,
    safe=1,
    sanity=73,
    insight=19,
    budget=4,
    spent=0,
    reserved=0,
    last_id=0,
    vitals=dict(hp=20, hp_max=20, power=20, power_max=23),
)


def synthetic(enabled, future):
    """Independent, contract-derived records, NOT a captured native journal."""
    records = []

    def add(event, detail="", safe=0, observation=None, phase="result"):
        record = dict(
            CONTEXT, v=1, seq=len(records) + 1, event=event, detail=detail, phase=phase
        )
        record["safe"] = safe
        if observation is not None:
            record.update(v=2, observation=observation)
        records.append(copy.deepcopy(record))

    if enabled:
        add(
            "observation",
            observation=dict(
                operation="none", stage="enabled", root_seq=0, fact="none"
            ),
        )
    add("session", "new")
    add("level_enter")
    add("safe_point", "level_enter", safe=1)
    if enabled and future:
        for stage, fact, root, phase in (
            ("started", "none", 0, "attempt"),
            ("notice", "water_refreshed", 5, "result"),
            ("completed", "none", 5, "result"),
        ):
            add(
                "observation",
                safe=1,
                phase=phase,
                observation=dict(
                    operation="fountain_drink", stage=stage, root_seq=root, fact=fact
                ),
            )
    return records


class FountainOracleTests(unittest.TestCase):
    def validate(self, records, enabled=True, future=True):
        driver.validate_history(records, CONTEXT, enabled=enabled, future=future)

    def test_legitimate_synthetic_contract(self):
        for enabled in (False, True):
            for future in (False, True):
                self.validate(synthetic(enabled, future), enabled, future)

    def test_reject_extra_valid_legacy_event(self):
        for enabled in (False, True):
            for future in (False, True):
                records = synthetic(enabled, future)
                records.append(
                    dict(records[-1], v=1, event="level_enter", seq=len(records) + 1)
                )
                records[-1].pop("observation", None)
                parse_episode_event(json.dumps(records[-1]))
                with self.assertRaises(AssertionError):
                    self.validate(records, enabled, future)

    def test_synthetic_future_projector_shape_is_legal(self):
        raw = b"".join(json.dumps(r).encode() + b"\n" for r in synthetic(True, True))
        self.assertEqual(
            project_episodes(raw)["episodes"],
            [
                dict(
                    operation="fountain_drink",
                    count=1,
                    saturated=False,
                    evidence=[
                        dict(
                            root_seq=5, notice_seq=6, end_seq=7, fact="water_refreshed"
                        )
                    ],
                )
            ],
        )

    def test_reject_falsified_envelopes(self):
        for enabled in (False, True):
            for future in (False, True):
                original = synthetic(enabled, future)
                for index in range(len(original)):
                    for key in (
                        "turn",
                        "safe",
                        "sanity",
                        "insight",
                        "budget",
                        "spent",
                        "reserved",
                        "last_id",
                        "seq",
                    ):
                        with self.subTest(
                            enabled=enabled, future=future, index=index, key=key
                        ):
                            records = copy.deepcopy(original)
                            records[index][key] += 1
                            with self.assertRaises(AssertionError):
                                self.validate(records, enabled, future)
                    for key in CONTEXT["vitals"]:
                        records = copy.deepcopy(original)
                        records[index]["vitals"][key] += 1
                        with self.assertRaises(AssertionError):
                            self.validate(records, enabled, future)
                    for key, value in (("detail", "falsified"), ("unexpected", 1)):
                        records = copy.deepcopy(original)
                        records[index][key] = value
                        with self.assertRaises(AssertionError):
                            self.validate(records, enabled, future)

    def test_reject_action_on_decline_or_prehook(self):
        with self.assertRaises(AssertionError):
            self.validate(synthetic(True, True), future=False)

    def test_complete_legacy_pair_only_seq_offset(self):
        off, on = synthetic(False, False), synthetic(True, True)
        driver.validate_legacy_pair(off, on)
        on[2]["vitals"]["hp_max"] += 1
        with self.assertRaises(AssertionError):
            driver.validate_legacy_pair(off, on)

    def test_optimized_cli_rejected_before_arguments_or_setup(self):
        result = subprocess.run(
            ["/usr/bin/python3", "-O", str(Path(driver.__file__))],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RuntimeError: optimized Python is not supported", result.stderr)
        self.assertNotIn("required", result.stderr)


if __name__ == "__main__":
    unittest.main()
