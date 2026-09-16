"""Strict fatal-fountain artifact oracle; native execution is never synthesized."""

import copy
import unittest


def validate_fatal(records, native, terminal, xlog, public, *, enabled):
    assert native["gameover"] == 1 and native["hp"] <= 0
    assert native["rng_count"] == 3
    assert native["entered"] == 1 and native["returned"] == 0
    assert b"The water is contaminated!" in terminal
    assert b"contaminated water" in xlog
    assert b"OK, so you don" not in terminal
    assert records[-1]["event"] == "death" and records[-1]["detail"] == "died"
    observations = [r for r in records if r["event"] == "observation"]
    assert [r["observation"]["stage"] for r in observations] == (
        ["enabled", "started"] if enabled else []
    ), "fatal selected root must remain incomplete"
    if enabled:
        root = observations[-1]
        assert root["observation"] == dict(
            operation="fountain_drink", stage="started", root_seq=0, fact="none"
        )
        assert root["phase"] == "attempt" and root["vitals"]["hp"] == 1
        assert records[-1]["vitals"]["hp"] == 0  # public clamp, native HP is negative
        assert records[-1]["turn"] == root["turn"] == 1
        assert records[-1]["vitals"]["hp_max"] == root["vitals"]["hp_max"]
        assert public["episodes"] == []
        assert public["coverage"]["incomplete"] == dict(count=1, saturated=False)
        assert all(
            v == dict(count=0, saturated=False)
            for k, v in public["coverage"].items()
            if k != "incomplete"
        )


def reject_mutated_death_evidence(records, native, terminal, xlog, public):
    """Sensitivity only: mutate copies of actual native outputs, never journals."""
    completed = copy.deepcopy(records[-2])
    completed["observation"].update(stage="completed", root_seq=completed["seq"])
    completed.update(phase="result", seq=records[-1]["seq"] + 1)
    variants = {
        "invented_terminal": (records + [completed], native, terminal, xlog, public),
        "returned_action": (records, dict(native, returned=1), terminal, xlog, public),
        "no_native_gameover": (
            records,
            dict(native, gameover=0),
            terminal,
            xlog,
            public,
        ),
        "missing_death_cause": (records, native, terminal, b"", public),
    }
    rejected = []
    for name, values in variants.items():
        try:
            validate_fatal(*values, enabled=True)
        except AssertionError:
            rejected.append(name)
        else:
            raise AssertionError("oracle accepted mutation: " + name)
    return rejected


def compare_pair(off, on):
    for key in ("terminal", "inputs", "xlog", "dump", "native", "before"):
        assert off[key] == on[key], key + " OFF/ON mismatch"
    legacy = [r for r in on["records"] if r["v"] == 1]
    assert len(legacy) == len(off["records"])
    assert [dict(r, seq=i + 1) for i, r in enumerate(legacy)] == off["records"]


class FatalOracleTests(unittest.TestCase):
    def test_missing_native_death_rejected_before_journal(self):
        with self.assertRaises(AssertionError):
            validate_fatal(
                [],
                dict(gameover=0, hp=1, entered=1, returned=0),
                b"",
                b"",
                {},
                enabled=True,
            )

    def test_pair_rejects_each_artifact_change(self):
        row = dict(
            terminal=b"a",
            inputs=["79"],
            xlog=b"b",
            dump=b"c",
            native={"hp": -1},
            before={"hp": 1},
            records=[],
        )
        compare_pair(row, copy.deepcopy(row))
        for key in ("terminal", "inputs", "xlog", "dump", "native", "before"):
            altered = copy.deepcopy(row)
            altered[key] = None
            with self.subTest(key=key), self.assertRaises(AssertionError):
                compare_pair(row, altered)


if __name__ == "__main__":
    unittest.main()
