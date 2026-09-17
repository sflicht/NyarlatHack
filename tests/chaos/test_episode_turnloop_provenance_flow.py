"""SYNTHETIC UNIT ONLY seven-route driver orchestration; never native evidence.

Game, action delivery, compiler/history subprocesses and profile/history binding
are unit boundaries. Real tuple checks, strict/supplemental comparators, event
projection and publication run unchanged. Even the stock stand-in is generated
schema data, NOT a historical receipt or native-behavior test.
"""

from contextlib import ExitStack, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_episode_turnloop as driver
import test_episodes as event_fixtures
import test_turnloop_dump_provenance as dump_fixtures
import turnloop_dump_provenance as provenance
import turnloop_header_bindings as bindings


NAMES = [
    "reviewed-chaos0",
    "inactive",
    "legacy-empty",
    "legacy-repeat",
    "v2-empty",
    "v2-repeat",
    "upstream-stock",
]
COMMANDS = [
    "ordinary_whistle",
    "magic_whistle",
    "decline_then_potion",
    "confirmed_fountain",
]


class DriverFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-turnloop-unit-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "checkout"
        self.receipt = self.base / "receipts"
        self.receipt.mkdir()
        self.off = self.base / "off"
        self.current = self.root / "dnethackdir"
        self.stock = self.base / "synthetic-stock"
        self.out = self.base / "output"
        self.trace = []
        self.created = []
        self.samples = {}
        self.builds = {}
        self.fault = None
        self.handlers = {
            s: signal.getsignal(s)
            for s in (
                signal.SIGINT,
                signal.SIGTERM,
                signal.SIGALRM,
            )
        }
        # Safety backstop also covers the deliberately failing cleanup regression.
        self.addCleanup(self.restore_process_state, list(sys.path), os.umask(0o077))
        for directory, name, digit, mode in (
            (self.off, "reviewed-chaos0", "1", 0),
            (self.current, "reviewed-chaos1", "1", 1),
            (self.stock, "synthetic-stock", "2", 0),
        ):
            directory.mkdir(parents=True)
            fixture = dump_fixtures.ProvenanceDumpTests().fixture(name, digit, mode)
            # Current modes share revision but have independently captured headers.
            if mode:
                fixture["expected_header"] = fixture["expected_header"].replace(
                    b"18:51:31", b"18:51:39"
                )
                fixture["date_h"] = fixture["date_h"].replace(b"18:51:31", b"18:51:39")
                manifest = json.loads(fixture["manifest"])
                manifest["date_h_sha256"] = dump_fixtures.sha(fixture["date_h"])
                fixture["manifest"] = json.dumps(manifest, sort_keys=True).encode()
                fixture["trusted_manifest_sha256"] = dump_fixtures.sha(
                    fixture["manifest"]
                )
            for key, raw in fixture["artifacts"].items():
                (directory / key).write_bytes(raw)
            self.samples[directory] = dump_fixtures.ProvenanceDumpTests().dump(fixture)
            self.builds[directory] = bindings.Binding(
                provenance.validate_build(**fixture),
                tuple((key, len(raw)) for key, raw in fixture["artifacts"].items()),
                {"scope": "SYNTHETIC UNIT ONLY; generated schema, not native history"},
            )
            if directory != self.stock:
                commands = [
                    dict(
                        argv=[
                            "/usr/bin/make",
                            "-j2",
                            target,
                            f"CHAOS={mode}",
                            "CC=/usr/bin/cc",
                            "PKG_CONFIG=/usr/bin/pkg-config",
                        ],
                        exit_code=0,
                    )
                    for target in ("clean", "install")
                ]
                manifest = dict(
                    mode=mode,
                    revision="1" * 40,
                    commands=commands,
                    pairs={
                        key: dict(sha256=dump_fixtures.sha(raw), size=len(raw))
                        for key, raw in fixture["artifacts"].items()
                    },
                    generated_headers={
                        "include/date.h": dump_fixtures.sha(fixture["date_h"])
                    },
                )
                (self.receipt / f"{mode}-manifest.json").write_text(
                    json.dumps(manifest)
                )
                (self.receipt / f"{mode}-commands.json").write_text(
                    json.dumps(commands)
                )
                (self.receipt / f"{mode}-date.h").write_bytes(fixture["date_h"])
        stock_receipt = self.base / "stock-receipt"
        (stock_receipt / "game/dumplog").mkdir(parents=True)
        self.stock_receipt = stock_receipt / "manifest.json"
        self.stock_receipt.write_text(
            json.dumps(
                dict(
                    exit=0,
                    sessions=[
                        dict(sha256=dict(self.builds[self.stock].build.tuple_sha256))
                    ],
                )
            )
        )
        (stock_receipt / "game/dumplog/1700000000").write_bytes(
            self.samples[self.stock]
        )
        support = self.root / "tests/chaos"
        support.mkdir(parents=True)
        for name in ("gameplay_support.py", "replay_clock.c"):
            shutil.copy2(Path(driver.__file__).with_name(name), support / name)
        rows = [event_fixtures.enabled(), event_fixtures.session(2)]
        event_fixtures.action(rows, fact="sound_high")
        event_fixtures.action(rows, fact="sound_strange")
        event_fixtures.action(rows, operation="fountain_drink", fact=None)
        self.v2 = event_fixtures.wire(*rows)
        self.legacy = event_fixtures.wire(event_fixtures.session())

    def restore_process_state(self, path, mask):
        for sig, handler in self.handlers.items():
            signal.signal(sig, handler)
        sys.path[:] = path
        os.umask(mask)

    def execute(self, *, opt_in=True, fault=None):
        self.fault = fault
        owner = self

        class FakeGame:
            def __init__(self, source, clock, *, observe, wizard, root):
                self.root, self.source = root, source
                self.game, self.run = root / "game", root / "run"
                self.game.mkdir(parents=True)
                self.run.mkdir()
                for key in ("dnethack", "nhdat", "license"):
                    shutil.copy2(source / key, self.game / key)
                self.inputs = []
                self.raw = b"SYNTHETIC UNIT terminal"
                self.observe = observe
                owner.created.append(self)
                owner.trace.append(("create", root.name, source, observe, wizard))

            def start(self):
                owner.trace.append(
                    (
                        "start",
                        self.root.name,
                        os.environ.get("NYARLATHACK_OBSERVATIONS"),
                        os.environ["MAIL"],
                    )
                )
                if fault == ("early", self.root.name):
                    raise RuntimeError("synthetic start failure")
                if self.observe:
                    raw = (
                        owner.v2
                        if os.environ.get("NYARLATHACK_OBSERVATIONS")
                        else owner.legacy
                    )
                    if fault == ("events", self.root.name):
                        # Valid JSON/schema and semantics, but not an exact repeat.
                        raw = raw.replace(b'"seq":', b'"seq" :')
                    (self.run / "events.jsonl").write_bytes(raw)
                    (self.run / "whispers.jsonl").write_bytes(b"")

            def quit(self):
                owner.trace.append(("quit", self.root.name))
                return 0

            def save_artifacts(self):
                (self.game / "dumplog").mkdir(exist_ok=True)
                dump = owner.samples[self.source]
                xlog = b"SYNTHETIC UNIT score\n"
                if fault == ("dump", self.root.name):
                    dump += b"changed body\n"
                if fault == ("xlog", self.root.name):
                    xlog += b"changed\n"
                if fault == ("terminal", self.root.name):
                    self.raw += b"changed"
                if fault == ("native", self.root.name):
                    self.raw = b""
                (self.game / "dumplog/1700000000").write_bytes(dump)
                (self.game / "xlogfile").write_bytes(xlog)

            def events(self):
                return [
                    json.loads(line)
                    for line in (self.run / "events.jsonl").read_bytes().splitlines()
                ]

            def cleanup(self):
                owner.trace.append(("cleanup", self.root.name))
                if fault in (("cleanup", self.root.name), ("cleanup", "all")):
                    raise RuntimeError("synthetic cleanup failure: " + self.root.name)

        def synthetic_actions(game, matrix):
            self.assertTrue(matrix)
            game.inputs = [value.encode().hex() for value in driver.MATRIX_INPUTS]
            if fault == ("inputs", game.root.name):
                game.inputs[-1] = b"changed".hex()
            return {name: "SYNTHETIC UNIT witness" for name in COMMANDS}

        def bounded(command, work, env, prefix, **kwargs):
            self.trace.append(("bounded", str(command[0])))
            if str(command[0]) == "/usr/bin/cc":
                (self.out / "clock.so").write_bytes(b"SYNTHETIC UNIT, not a library")
            else:
                self.assertEqual(str(command[0]), "/usr/bin/git")
            return b"", b""

        original_save = driver.save

        def save(path, value):
            self.trace.append(("save", path.name))
            original_save(path, value)

        args = [
            "--root",
            str(self.root),
            "--receipt",
            str(self.receipt),
            "--revision",
            "1" * 40,
            "--off-tuple",
            str(self.off),
            "--artifacts",
            str(self.out),
            "--matrix",
            "--stock-tuple",
            str(self.stock),
            "--stock-receipt",
            str(self.stock_receipt),
            "--stock-revision",
            "2" * 40,
        ]
        if opt_in:
            args.append("--provenance-dumps")
        with ExitStack() as stack:
            stack.enter_context(patch.object(driver, "Game", FakeGame))
            # No child/PTY ownership in a no-process fixture; test driver cleanup calls.
            stack.enter_context(
                patch.object(
                    driver, "owned_game_type", side_effect=lambda base, cancel: base
                )
            )
            stack.enter_context(
                patch.object(driver, "actions", side_effect=synthetic_actions)
            )
            stack.enter_context(patch.object(driver, "bounded", side_effect=bounded))
            stack.enter_context(patch.object(driver, "save", side_effect=save))
            stack.enter_context(patch.object(driver.signal, "alarm"))
            stack.enter_context(
                patch.object(
                    bindings, "check_profile", return_value={"scope": "synthetic unit"}
                )
            )
            stack.enter_context(
                patch.object(
                    bindings, "historical_binding", return_value=self.builds[self.stock]
                )
            )
            # current_binding, verify_tuple, compare_runs, compare_run, validate_native,
            # legacy_projection and project_episodes are deliberately NOT mocked.
            stack.enter_context(redirect_stdout(io.StringIO()))
            return driver.main(args)

    def read(self, name):
        return json.loads((self.out / name).read_text())

    def assert_cleaned(self):
        self.assertEqual(
            [row[1] for row in self.trace if row[0] == "cleanup"],
            [game.root.name for game in self.created],
        )
        self.assertEqual(
            {sig: signal.getsignal(sig) for sig in self.handlers}, self.handlers
        )

    def assert_no_success(self):
        self.assertFalse((self.out / "provenance-result.json").exists())
        self.assertNotIn(("save", "provenance-result.json"), self.trace)

    def test_opt_in_seven_variants_strict_failure_supplemental_success_after_cleanup(
        self,
    ):
        self.execute()
        self.assertEqual([game.root.name for game in self.created], NAMES)
        self.assertEqual(
            [game.source for game in self.created],
            [
                self.off,
                self.current,
                self.current,
                self.current,
                self.current,
                self.current,
                self.stock,
            ],
        )
        starts = [row for row in self.trace if row[0] == "start"]
        self.assertEqual(
            [row[2] for row in starts], [None, None, None, None, "1", "1", None]
        )
        self.assertEqual({row[3] for row in starts}, {str(self.out / "private-mail")})
        self.assertEqual(
            [game.observe for game in self.created],
            [False, False, True, True, True, True, False],
        )
        strict, supplemental = (
            self.read("result.json"),
            self.read("provenance-result.json"),
        )
        self.assertFalse(strict["passed_selected_matrix"])
        self.assertEqual(strict["variants"], NAMES)
        self.assertEqual(strict["commands"], COMMANDS)
        self.assertEqual([row["variant"] for row in strict["mismatches"]], NAMES[1:])
        for row in strict["mismatches"]:
            self.assertEqual(row["failure"], "dumps parity")
            self.assertEqual(
                row["equal"], dict(inputs=True, terminal=True, xlog=True, dumps=False)
            )
        self.assertTrue(supplemental["passed_selected_matrix"])
        self.assertFalse(supplemental["strict_result_passed"])
        self.assertFalse(supplemental["task8_closed"])
        self.assertEqual(supplemental["strict_mismatches"], strict["mismatches"])
        self.assertEqual(len(supplemental["comparisons"]), 6)
        self.assertTrue(all(row["equal"] for row in supplemental["comparisons"]))
        self.assertTrue(supplemental["driver_cleanup_completed"])
        recorded = self.read("header-bindings.json")["bindings"]
        self.assertEqual(
            set(recorded), {str(self.off), str(self.current), str(self.stock)}
        )
        for source, binding in self.builds.items():
            self.assertEqual(recorded[str(source)]["build"], binding.build.record())
        compared_builds = {
            name for result in supplemental["comparisons"] for name in result["builds"]
        }
        self.assertEqual(
            compared_builds, {"reviewed-chaos0", "reviewed-chaos1", "synthetic-stock"}
        )
        self.assertEqual(
            self.read("provenance.json")["pinned_matrix_inputs"], driver.MATRIX_INPUTS
        )
        for key in (
            "exact_legacy_repeat",
            "exact_v2_repeat",
            "legacy_semantics_equal_after_v2_removal_and_seq_renumber",
        ):
            self.assertIs(strict[key], True)
        for first, second in (
            ("legacy-empty", "legacy-repeat"),
            ("v2-empty", "v2-repeat"),
        ):
            self.assertEqual(
                (self.out / first / "run/events.jsonl").read_bytes(),
                (self.out / second / "run/events.jsonl").read_bytes(),
            )
        self.assert_cleaned()
        publication = self.trace.index(("save", "provenance-result.json"))
        self.assertTrue(
            all(
                i < publication
                for i, row in enumerate(self.trace)
                if row[0] == "cleanup"
            )
        )

    def test_default_same_samples_save_strict_failure_and_raise_without_supplement(
        self,
    ):
        with self.assertRaisesRegex(AssertionError, "dumps parity"):
            self.execute(opt_in=False)
        self.assertEqual([game.root.name for game in self.created], NAMES)
        self.assertFalse(self.read("result.json")["passed_selected_matrix"])
        self.assertEqual(len(self.read("result.json")["mismatches"]), 6)
        self.assertFalse((self.out / "header-bindings.json").exists())
        self.assert_no_success()
        self.assert_cleaned()

    def test_nondump_and_body_changes_cannot_publish_success(self):
        for field in ("terminal", "xlog", "dump"):
            with self.subTest(field=field):
                with self.assertRaises(AssertionError):
                    self.execute(fault=(field, "upstream-stock"))
                self.assert_no_success()
                self.assert_cleaned()
                self.assertFalse(self.read("result.json")["passed_selected_matrix"])
                shutil.rmtree(self.out)
                self.created.clear()
                self.trace.clear()

    def test_changed_inputs_fail_pinned_route_and_cleanup(self):
        with self.assertRaisesRegex(AssertionError, "pinned input route"):
            self.execute(fault=("inputs", "inactive"))
        self.assertEqual(len(self.created), 2)
        self.assert_no_success()
        self.assert_cleaned()

    def test_native_gate_failure_prevents_publication(self):
        with self.assertRaisesRegex(AssertionError, "missing terminal"):
            self.execute(fault=("native", "upstream-stock"))
        self.assertEqual(len(self.created), 7)
        self.assert_no_success()
        self.assert_cleaned()

    def test_event_repeat_failure_prevents_publication(self):
        with self.assertRaises(AssertionError):
            self.execute(fault=("events", "v2-repeat"))
        self.assertEqual(len(self.created), 7)
        self.assert_no_success()
        self.assert_cleaned()

    def test_early_start_failure_cleans_every_acquired_game(self):
        with self.assertRaisesRegex(RuntimeError, "synthetic start failure"):
            self.execute(fault=("early", "inactive"))
        self.assertEqual(len(self.created), 2)
        self.assertFalse((self.out / "result.json").exists())
        self.assert_no_success()
        self.assert_cleaned()

    def test_cleanup_failure_attempts_all_games_restores_handlers_and_never_publishes(
        self,
    ):
        for name in (NAMES[0], NAMES[-1], "all"):
            with self.subTest(failing_cleanup=name):
                try:
                    with self.assertRaisesRegex(
                        RuntimeError, "synthetic cleanup failure"
                    ):
                        self.execute(fault=("cleanup", name))
                    self.assert_no_success()
                    self.assert_cleaned()
                finally:
                    # Isolate subtests even when the production cleanup contract fails.
                    for sig, handler in self.handlers.items():
                        signal.signal(sig, handler)
                    shutil.rmtree(self.out)
                    self.created.clear()
                    self.trace.clear()


if __name__ == "__main__":
    unittest.main()
