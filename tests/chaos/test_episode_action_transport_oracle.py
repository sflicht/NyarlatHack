"""Sensitivity of the new selected-action comparator, not older fixtures."""

import copy
import unittest
from test_episode_action_transport import compare_native, validate_transport


class ActionTransportOracleTests(unittest.TestCase):
    def test_native_comparator_rejects_each_channel(self):
        baseline = dict(
            terminal=b"native",
            inputs=["79", "61"],
            snapshot=b"full",
            state=dict(count=3, next=42, spent=0),
        )
        compare_native(baseline, copy.deepcopy(baseline))
        for key, value in (
            ("terminal", b"changed"),
            ("inputs", []),
            ("snapshot", b"changed"),
            ("state", dict(count=4, next=42, spent=0)),
        ):
            with self.subTest(key=key):
                changed = copy.deepcopy(baseline)
                changed[key] = value
                with self.assertRaises(AssertionError):
                    compare_native(baseline, changed)

    def test_transport_requires_trigger_and_no_rewrite(self):
        healthy = b"a\nb\nc\n"
        meta = dict(
            triggered=1,
            committed=1,
            seq_final=1,
            seq_action=1,
            writes_after=0,
            syncs_after=0,
        )
        validate_transport(healthy, b"a\nb\n", meta, 1, "fsync")
        for key in ("triggered", "seq_final", "writes_after", "syncs_after"):
            changed = dict(meta, **{key: 9})
            with self.assertRaises(AssertionError):
                validate_transport(healthy, b"a\nb\n", changed, 1, "fsync")
        with self.assertRaises(AssertionError):
            validate_transport(healthy, b"a\nx\n", meta, 1, "fsync")


if __name__ == "__main__":
    unittest.main()
