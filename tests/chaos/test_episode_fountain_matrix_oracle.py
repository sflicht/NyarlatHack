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


def evidence_policy():
    # Caller-owned mode, never inferred from versions or missing context.
    mode = os.environ.get("FOUNTAIN_MATRIX_POLICY")
    assert mode in ("current", "historical"), "explicit evidence policy"
    return matrix.CURRENT if mode == "current" else matrix.HISTORICAL


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
            if evidence_policy() == matrix.CURRENT:
                before, after = state["context_before"], state["context_after"]
            else:
                before = state.get("context_before", {k: rows[-2][k] for k in keys})
                after = state.get("context_after", {k: rows[-1][k] for k in keys})
            matrix.validate_history(
                raw, before, after, fate, True, policy=evidence_policy()
            )
            mutations = []
            for name, change in (
                ("secret-envelope", lambda r: r[-1].update(secret=42)),
                ("secret-vitals", lambda r: r[-1]["vitals"].update(secret=42)),
                ("event", lambda r: r[-1].update(event="session")),
                ("version-type", lambda r: r[-1].update(v=2.0)),
                ("turn", lambda r: r[-1].update(turn=102)),
                ("phase", lambda r: r[-1].update(phase="attempt")),
                ("deleted-root", lambda r: r.pop(-2)),
                ("ordinary-value", lambda r: r[1].update(spent=1)),
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
            if evidence_policy() == matrix.CURRENT:
                for value in (
                    None,
                    {},
                    dict(seen=False, last_turn=0),
                    dict(seen=1, last_turn=0),
                ):
                    bad = copy.deepcopy(rows)
                    bad[1]["cosmetic"] = value
                    mutations.append(
                        (
                            "cosmetic",
                            b"".join(json.dumps(r).encode() + b"\n" for r in bad),
                        )
                    )
            # Duplicate a real key independently of wire version/JSON spacing.
            first = raw.index(b'"v"')
            duplicate = raw[:first] + b'"v":0,' + raw[first:]
            mutations.append(("duplicate", duplicate))
            for name, bad in mutations:
                with (
                    self.subTest(fate=fate, mutation=name),
                    self.assertRaises((ValueError, AssertionError)),
                ):
                    matrix.validate_history(
                        bad, before, after, fate, True, policy=evidence_policy()
                    )

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

    def test_special_manifest_is_finite_and_explicit(self):
        self.assertEqual(
            [row["case"] for row in matrix.SPECIAL_CASES],
            [
                "magic-refresh",
                "magic-low-luck",
                "magic-high-luck",
                "magic-negative-luck",
                "depletion",
                "hallucination-map",
                "no-mouth",
            ],
        )
        for row in matrix.SPECIAL_CASES:
            self.assertEqual(
                set(row),
                {
                    "case",
                    "fate",
                    "blessed",
                    "luck",
                    "hallucination",
                    "no_mouth",
                    "restore",
                },
            )

    @unittest.skipUnless(
        os.environ.get("FOUNTAIN_MATRIX_EVIDENCE"), "explicit native evidence required"
    )
    def test_actual_special_pairs_and_history_mutations(self):
        for case in matrix.SPECIAL_CASES:
            pairs = []
            for enabled in (False, True):
                work = BASELINE / (case["case"] + ("-on" if enabled else "-off"))
                state = json.loads((work / "state.json").read_text())
                raw = (work / "run/events.jsonl").read_bytes()
                matrix.validate_history(
                    raw,
                    state["context_before"],
                    state["context_after"],
                    case["fate"],
                    enabled,
                    case["case"],
                    policy=evidence_policy(),
                )
                pairs.append(
                    dict(
                        state=state,
                        terminal=(work / "terminal.stdout").read_bytes().hex(),
                        inputs=json.loads((work / "inputs.json").read_text()),
                    )
                )
                if enabled:
                    rows = [json.loads(line) for line in raw.splitlines()]
                    for field in ("secret", "vitals", "observation"):
                        bad = copy.deepcopy(rows)
                        if field == "secret":
                            bad[-1][field] = "private-native-identity"
                        elif field == "vitals":
                            bad[-1][field]["hp"] += 1
                        else:
                            bad[-1][field] = dict(
                                operation="fountain_drink",
                                stage="notice",
                                root_seq=5,
                                fact="water_refreshed",
                            )
                        with (
                            self.subTest(case=case["case"], field=field),
                            self.assertRaises((ValueError, AssertionError)),
                        ):
                            matrix.validate_history(
                                b"\n".join(json.dumps(r).encode() for r in bad) + b"\n",
                                state["context_before"],
                                state["context_after"],
                                case["fate"],
                                True,
                                case["case"],
                                policy=evidence_policy(),
                            )
            matrix.validate_pair(*pairs)
            for field in ("vision", "player"):
                bad = copy.deepcopy(pairs[1])
                bad["state"]["after"][field] = None
                with (
                    self.subTest(case=case["case"], domain=field),
                    self.assertRaises(AssertionError),
                ):
                    matrix.validate_pair(pairs[0], bad)
            state = pairs[1]["state"]
            if case["restore"]:
                self.assertEqual(
                    sum(a - 12 for a, _ in state["special"]["attributes"]),
                    6 if case["luck"] == 4 else 1,
                )
            if case["no_mouth"]:
                self.assertEqual(pairs[1]["inputs"], [])
                self.assertEqual(state["count"], 0)

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
