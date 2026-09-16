"""Actual retained native artifact mutations; no synthetic native pair claims."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import test_episode_fountain_matrix as matrix

BASELINE = (
    Path(os.environ["FOUNTAIN_MATRIX_EVIDENCE"])
    if os.environ.get("FOUNTAIN_MATRIX_EVIDENCE")
    else None
)


class MatrixOracleTests(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("FOUNTAIN_MATRIX_EVIDENCE"), "explicit native evidence required"
    )
    def test_pair_rejects_each_state_domain(self):
        work = BASELINE / "fate-01-on"
        base = dict(
            state=json.loads((work / "state.json").read_text()),
            terminal=(work / "terminal.stdout").read_bytes().hex(),
            inputs=json.loads((work / "inputs.json").read_text()),
        )
        matrix.validate_pair(base, copy.deepcopy(base))
        for key in matrix.DOMAINS:
            bad = copy.deepcopy(base)
            bad["state"]["after"][key] = None
            with self.subTest(domain=key), self.assertRaises(AssertionError):
                matrix.validate_pair(base, bad)
        for key in ("count", "next"):
            bad = copy.deepcopy(base)
            bad["state"][key] += 1
            with self.subTest(field=key), self.assertRaises(AssertionError):
                matrix.validate_pair(base, bad)

    @unittest.skipUnless(
        os.environ.get("FOUNTAIN_MATRIX_EVIDENCE"), "explicit native evidence required"
    )
    def test_actual_history_mutations(self):
        for fate in (1, 21, 23, 26, 30):
            work = BASELINE / f"fate-{fate:02}-on"
            raw = (work / "run/events.jsonl").read_bytes()
            rows = [json.loads(line) for line in raw.splitlines()]
            state = json.loads((work / "state.json").read_text())
            # Old retained native artifacts predate independent context capture.
            # These contexts only anchor mutation tests, never batch acceptance.
            keys = (
                "turn",
                "safe",
                "sanity",
                "insight",
                "budget",
                "spent",
                "reserved",
                "last_id",
                "vitals",
            )
            before = state.get("context_before", {k: rows[-2][k] for k in keys})
            after = state.get("context_after", {k: rows[-1][k] for k in keys})
            matrix.validate_history(raw, before, after, fate, True)
            mutations = []
            for name, change in (
                ("secret-envelope", lambda r: r[-1].update(secret=42)),
                ("secret-vitals", lambda r: r[-1]["vitals"].update(secret=42)),
                ("event", lambda r: r[-1].update(event="session")),
                ("version-type", lambda r: r[-1].update(v=2.0)),
                ("turn", lambda r: r[-1].update(turn=102)),
                ("root", lambda r: r[-1]["observation"].update(root_seq=2)),
                ("prefix-secret", lambda r: r[1].update(secret=42)),
                ("interleaving", lambda r: r.insert(-1, dict(r[2], seq=len(r)))),
                ("terminal", lambda r: r[-1]["observation"].update(stage="blocked")),
            ):
                bad = copy.deepcopy(rows)
                change(bad)
                mutations.append(
                    (name, b"".join(json.dumps(r).encode() + b"\n" for r in bad))
                )
            mutations.append(("duplicate", raw.replace(b'"v":2', b'"v":2,"v":2', 1)))
            for name, bad in mutations:
                with (
                    self.subTest(fate=fate, mutation=name),
                    self.assertRaises((ValueError, AssertionError)),
                ):
                    matrix.validate_history(bad, before, after, fate, True)

    def test_optimization_rejected_before_work(self):
        script = Path(matrix.__file__).resolve()
        for flags, optimize in ((["-O"], ""), (["-OO"], ""), ([], "1"), ([], "2")):
            for imported in (False, True):
                with (
                    self.subTest(flags=flags, env=optimize, imported=imported),
                    tempfile.TemporaryDirectory() as tmp,
                ):
                    out = Path(tmp) / "must-not-exist"
                    args = [
                        "--root",
                        tmp,
                        "--receipt",
                        tmp,
                        "--revision",
                        "invalid",
                        "--artifacts",
                        str(out),
                    ]
                    command = [sys.executable, *flags]
                    if imported:
                        command += [
                            "-c",
                            f"import sys; sys.path.insert(0, {str(script.parent)!r}); import test_episode_fountain_matrix as m; m.main()",
                        ]
                    else:
                        command += [str(script)]
                    result = subprocess.run(
                        command + args,
                        env=dict(os.environ, PYTHONOPTIMIZE=optimize),
                        capture_output=True,
                        timeout=10,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(b"optimized Python is forbidden", result.stderr)
                    self.assertFalse(out.exists())

    @unittest.skipUnless(
        os.environ.get("FOUNTAIN_MATRIX_CONTROL_EVIDENCE"),
        "explicit native evidence required",
    )
    def test_budget_control_rejects_unrelated_player_mutation(self):
        def pair(name):
            work = Path(os.environ["FOUNTAIN_MATRIX_CONTROL_EVIDENCE"]) / name
            return dict(
                state=json.loads((work / "state.json").read_text()),
                terminal=(work / "terminal.stdout").read_bytes().hex(),
                inputs=json.loads((work / "inputs.json").read_text()),
            )

        healthy = pair("fate-01-on")
        bad = pair("negative-budget")
        matrix.validate_negative(healthy, bad, "budget")
        player = bytearray.fromhex(bad["state"]["after"]["player"])
        player[0] ^= 1
        bad["state"]["after"]["player"] = player.hex()
        with self.assertRaises(AssertionError):
            matrix.validate_negative(healthy, bad, "budget")

    def test_manifest_requires_all_actual_fates(self):
        rows = [dict(fate=i, seed=i) for i in range(1, 31)]
        matrix.validate_manifest(rows)
        for bad in (
            rows[:-1],
            rows + [rows[0]],
            [dict(fate=i, seed=4097) for i in range(1, 31)],
        ):
            with self.assertRaises(AssertionError):
                matrix.validate_manifest(bad)


if __name__ == "__main__":
    unittest.main()
