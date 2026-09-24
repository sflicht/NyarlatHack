"""Four-case controlled Unix playback, not ordinary play or saved-RNG replay.

Fake author bootstrap is a labelled fixture, not an intelligence claim. The
value-only typed C preflight is separate from physical execution. Three labelled
physical-loss controls exercise the same positive oracles; general replay remains
outside this bounded matrix.
"""

import difflib
import hashlib
import json
import os
import shutil
import subprocess
import unittest
from unittest.mock import Mock, patch

from chaos import next_use_author as author
from chaos.next_use_journal import read_journal
from gameplay_support import Game, ROOT
from test_episode_turnloop_oracle import compare_runs, read_native, validate_native
from test_next_use_offline_author import fixture_sources, response
import test_next_use_unix_save as unix_save


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def retain_tree(source, target):
    shutil.copytree(source, target, dirs_exist_ok=True)


class InputTape:
    """Validate ALL bytes, including Game's automatic answers, BEFORE send."""

    def __init__(self, game, expected=None):
        self.game = game
        self.expected = expected
        self.cursor = 0
        self.original = game.send
        game.send = self.send

    def send(self, value, **kwargs):
        raw = value.encode() if isinstance(value, str) else value
        if self.expected is not None:
            assert self.cursor < len(self.expected), "unexpected input"
            assert raw.hex() == self.expected[self.cursor], "input differs before send"
        self.cursor += 1
        return self.original(raw, **kwargs)


def preflight(files, trusted, journal, capture, initial, source):
    # trusted is retained independently in the recording process, not loaded
    # from the mutable bundle manifest. No semantic-C-validator claim here.
    assert set(files) == set(trusted), "bundle identity"
    for name, path in files.items():
        assert digest(path) == trusted[name], "bundle digest: " + name
    decoded = read_journal(journal, capture_status=load(capture))
    assert decoded["status"] == "acknowledged_complete"
    header = decoded["records"][0]["data"]["snapshot"]
    saved = load(initial)
    assert bytes.fromhex(header["source_hex"]) == source
    for key in header:
        if key in saved and key not in (
            "replay_cursor",
            "journal_state",
            "journal_bytes",
            "journal_sha256",
        ):
            assert header[key] == saved[key], "initial snapshot binding: " + key
    return decoded


class InputTapeTests(unittest.TestCase):
    """Fast byte-guard probes: no native game or author transport."""

    def test_mismatch_at_each_position_rejected_before_send(self):
        # Explicit commands and the automatic save/quit responses share one tape.
        expected = [b"a", b"b", b" ", b"S", b"y", b"\n"]
        for index, value in enumerate(expected):
            with self.subTest(index=index):
                sink = Mock()
                tape = InputTape(sink, [v.hex() for v in expected])
                for prefix in expected[:index]:
                    tape.send(prefix)
                tape.original.reset_mock()
                with self.assertRaisesRegex(
                    AssertionError, "input differs before send"
                ):
                    tape.send(value + b"x")
                tape.original.assert_not_called()
                self.assertEqual(tape.cursor, index)

    def test_exhaustion_rejected_before_send(self):
        sink = Mock()
        tape = InputTape(sink, [])
        with self.assertRaisesRegex(AssertionError, "unexpected input"):
            tape.send(b"x")
        tape.original.assert_not_called()
        self.assertEqual(tape.cursor, 0)


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class NativePlaybackTests(unittest.TestCase):
    # Reuse build implementation, NOT the original TestCase or its test methods.
    setUpClass = classmethod(unix_save.NextUseUnixSaveTests.setUpClass.__func__)
    _build_two_family_game = classmethod(
        unix_save.NextUseUnixSaveTests._build_two_family_game.__func__
    )

    @classmethod
    def tearDownClass(cls):
        # Compare only successful cases actually selected, never rely on test
        # order or require unselected cases in a focused control invocation.
        cases = {}
        for name in ("WF-witness", "WF-state", "FW-state", "WF-witness-unpublished"):
            directory = cls.artifacts / name
            if (directory / "playback-result.json").exists():
                cases[name] = load(directory / "bundle-digests.json")
        if cases:
            assert len({v["binary"] for v in cases.values()}) == 1, (
                "matrix shared binary"
            )
            wf = [v for k, v in cases.items() if k.startswith("WF-")]
            for key in ("inputs.json", "schedule.json"):
                assert len({v[key] for v in wf}) <= 1, "matrix matched WF " + key
            for program in ("state", "witness"):
                group = [v["source"] for k, v in cases.items() if program in k]
                assert len(set(group)) <= 1, "matrix source identity " + program
        (cls.artifacts / "matrix-cross-case.json").write_text(
            json.dumps(
                dict(
                    cases=list(cases),
                    checked="shared binary, matched WF inputs/schedule, source identity",
                ),
                indent=2,
            )
        )
        # Only this suite's completed compiled copies; retain saves and evidence.
        for pattern in (
            "*.o",
            "*.so",
            "dnethack",
            "semantic-preflight",
            "*/game/dnethack",
            "*/game/nhdat",
            "*/*/game/dnethack",
            "*/*/game/nhdat",
            "*/semantic-preflight",
            "*/fault-dnethack",
            "*/fountain-effect-loss.o",
        ):
            for path in cls.artifacts.glob(pattern):
                path.unlink()
        shutil.rmtree(cls.asset_pool, ignore_errors=True)

    def test_same_admitted_save_w_checkpoint_f_exact_input_playback(self):
        self.run_case("WF", "witness")

    def test_w_native_effect_bypass(self):
        self.physical_control("w-bypass", "native W witnessed at middle Save")

    def test_witness_loss_at_save(self):
        self.physical_control("witness-save", "preserved-witness oracle")

    def test_remaining_f_hunger_effect_loss(self):
        self.physical_control("f-effect", "native F hunger oracle")

    def physical_control(self, control, oracle):
        with self.assertRaisesRegex(AssertionError, oracle) as caught:
            self.run_case("WF", "witness", control=control)
        directory = self.artifacts / ("WF-witness-control-" + control)
        (directory / "oracle-failure.txt").write_text(str(caught.exception))
        if self.control_record.pid is not None:
            self.assertEqual(self.control_record.quit(), 0)
        self.check_physical_control(directory, control)

    def build_f_effect_loss(self, directory):
        # Only a temporary native source copy: keep rnd(10), result reporting,
        # callback and consumption untouched. Origin bootstrap uses the base exe.
        original_path = ROOT / "src/fountain.c"
        original = original_path.read_text()
        target = "\t\tu.uhunger += rnd(10); /* don't choke on water */"
        self.assertEqual(original.count(target), 1)
        replacement = """\t{ /* TEST ONLY physical-loss fault: retain the real native draw. */
\t\tint gain = rnd(10);
\t\tif (access("lose-f-effect", F_OK) != 0) u.uhunger += gain;
\t}"""
        mutated = original.replace(target, replacement).replace(
            '#include "hack.h"', '#include "hack.h"\n#include <unistd.h>', 1
        )
        source = directory / "fountain-effect-loss.c"
        obj = directory / "fountain-effect-loss.o"
        exe = directory / "fault-dnethack"
        source.write_text(mutated)
        (directory / "fountain-original.c").write_text(original)
        (directory / "fault.diff").write_text(
            "".join(
                difflib.unified_diff(
                    original.splitlines(True),
                    mutated.splitlines(True),
                    fromfile="src/fountain.c",
                    tofile=source.name,
                )
            )
        )
        compile_command = [
            "/usr/bin/cc",
            "-g",
            "-DCHAOS",
            "-DDLB",
            "-std=gnu17",
            "-I" + str(ROOT / "include"),
            "-c",
            str(source),
            "-o",
            str(obj),
        ]
        link = load(self.artifacts / "build-commands.json")[1]
        self.assertEqual(link.count(str(ROOT / "src/fountain.o")), 1)
        link = [
            str(obj)
            if s == str(ROOT / "src/fountain.o")
            else str(exe)
            if s == str(self.two_family_exe)
            else s
            for s in link
        ]
        commands = [compile_command, link]
        for index, command in enumerate(commands):
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            (directory / f"fault-build-{index}.log").write_text(
                result.stdout + result.stderr
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(original_path.read_text(), original)
        (directory / "fault-build.json").write_text(
            json.dumps(
                dict(
                    commands=commands,
                    returncode=0,
                    binary_sha256=digest(exe),
                    original_sha256=digest(original_path),
                    mutant_sha256=digest(source),
                    base_binary_sha256=digest(self.two_family_exe),
                ),
                indent=2,
            )
        )
        return exe

    def check_physical_control(self, directory, control):
        record = directory / "record"
        initial = load(directory / "bootstrap/initial.json")
        source = (directory / "bootstrap/fixture-source.lua").read_bytes()
        states = load(record / "states.json")
        schedule = load(record / "schedule.json")
        physical = [
            json.loads(s)
            for s in (record / "game/physical.jsonl").read_text().splitlines()
        ]
        native_path = record / "game/native.jsonl"
        if control == "w-bypass":
            self.assertFalse(native_path.exists(), "bypassed W must not emit a witness")
            native = []
        else:
            native = [json.loads(s) for s in native_path.read_text().splitlines()]
        middle_index = next(i for i, s in enumerate(schedule) if s["kind"] == "save")
        middle = states[middle_index]
        self.assertEqual(initial["source_sha256"], hashlib.sha256(source).hexdigest())
        for state in states:
            self.assertEqual(state["valid"], 1)
            self.assertEqual(state["source_sha256"], initial["source_sha256"])
            self.assertEqual(state["run_token"], initial["run_token"])
            self.assertEqual(state["spent"], 2)
        save = list((record / "middle-save").iterdir())
        self.assertEqual(len(save), 1)
        self.assertEqual(save[0].read_bytes().count(source), 1)
        self.assertEqual(
            (record / "run/next_use-receipt.jsonl").read_bytes(),
            (directory / "bootstrap/run/next_use-receipt.jsonl").read_bytes(),
        )
        witnesses = [r for r in physical if r["kind"] == "W"]
        drinks = [r for r in physical if r["kind"] == "F"]
        self.assertEqual(middle["callback_w"], 1)
        self.assertEqual(middle["callback_f"], 0)
        self.assertEqual(middle["slot_f"], 1)
        events = [
            json.loads(s)
            for s in (record / "run/events.jsonl").read_text().splitlines()
        ]
        restores = sum(
            e.get("event") == "session" and e.get("detail") == "restore" for e in events
        )
        self.assertEqual(restores, 1 if control == "w-bypass" else 2)
        if control == "w-bypass":
            bypass = [r for r in physical if r["kind"] == "W-bypass"]
            self.assertTrue(bypass)
            for row in bypass:
                self.assertEqual(row["before"], row["after"])
                self.assertEqual(row["witnessed"], 0)
                self.assertEqual(row["spent"], 2)
                self.assertGreaterEqual(
                    row["monstermoves"], middle["activation_monstermoves"] + 5
                )
                self.assertLess(
                    row["monstermoves"], middle["activation_monstermoves"] + 10
                )
            self.assertEqual(witnesses, [])
            self.assertEqual(drinks, [])  # Stop at decisive W oracle; no F claim.
            self.assertEqual(middle["witnessed"], 0)
        else:
            self.assertEqual(len(witnesses), 1)
            w = witnesses[0]
            for key in ("displaced", "delivered", "witnessed"):
                self.assertEqual(w[key], 1)
            self.assertNotEqual(w["before"], w["after"])
            self.assertEqual(w["after"], w["actual"])
            self.assertEqual(middle["witnessed"], 1)
            restored = states[middle_index + 1]
            if control == "witness-save":
                lost = [r for r in native if r["kind"] == "witness-loss-save"]
                self.assertEqual(len(lost), 1)
                self.assertEqual(lost[0]["serializer_result"], 1)
                self.assertEqual(lost[0]["runtime_witnessed"], 1)
                self.assertEqual(lost[0]["saved_witnessed"], 0)
                self.assertEqual(lost[0]["source_sha256"], initial["source_sha256"])
                self.assertEqual(restored["witnessed"], 0)
                self.assertFalse((record / "game/lose-witness-on-save").exists())
                # Recorder bookkeeping is inspected separately from this check
                # that isolates the lost gameplay value. Positive comparisons
                # above remain unchanged; this is only the negative diagnostic.
                diagnostic = {
                    "replay_cursor",
                    "journal_bytes",
                    "journal_sha256",
                    "journal_state",
                    "capture_incomplete",
                    "witnessed",
                }
                for key in middle.keys() - diagnostic:
                    self.assertEqual(restored[key], middle[key], key)
                self.assertEqual(drinks, [])
            else:
                self.assertEqual(restored["witnessed"], 1)
                self.assertEqual(len(drinks), 1)
                f = drinks[0]
                self.assertEqual(f["outcome"], 6)  # Actual callback, not a surrogate.
                # Same reset/fate/refresh/dry-up draws as the positive fixture;
                # the removed hunger addition must not remove rnd(10).
                self.assertEqual(f["rng_count"], 3)
                self.assertEqual(f["hunger_after"] - f["hunger_before"], 0)
                self.assertEqual(states[-1]["callback_f"], 1)
                self.assertEqual(states[-1]["callback_ordinal"], 2)
                self.assertEqual(states[-1]["slot_f"], 2)
                self.assertEqual(load(directory / "fault-build.json")["returncode"], 0)
        retained = {
            str(p.relative_to(directory)): digest(p)
            for p in directory.rglob("*")
            if p.is_file() and p.name not in ("dnethack", "nhdat")
        }
        (directory / "control-result.json").write_text(
            json.dumps(
                dict(
                    control=control,
                    oracle_failure=(directory / "oracle-failure.txt").read_text(),
                    native_restores=restores,
                    middle_save_exit=0,
                    physical=physical,
                    digests=retained,
                    ordinary_play=False,
                    rng_saved=False,
                ),
                indent=2,
            )
        )

    def run_case(self, order, program, unpublished=False, control=None):
        self._build_two_family_game()
        shutil.copy2(__file__, self.artifacts / "test_next_use_native_playback.py")
        with patch.dict(
            os.environ,
            {"NYARLATHACK_NEXT_USE_ADMIT": "1", "NYARLATHACK_OBSERVATIONS": "1"},
        ):
            self.exercise(order, program, unpublished, control)

    def test_state_wf_quiet_exact_input_playback(self):
        self.run_case("WF", "state")

    def test_state_fw_refresh_exact_input_playback(self):
        self.run_case("FW", "state")

    def test_witness_wf_unsupported_message_exact_input_playback(self):
        self.run_case("WF", "witness", unpublished=True)

    def exercise(self, order="WF", program="witness", unpublished=False, control=None):
        case = order + "-" + program + ("-unpublished" if unpublished else "")
        if control:
            case += "-control-" + control
        directory = self.artifacts / case
        directory.mkdir()
        refresh = order == "FW" or (program == "witness" and not unpublished)
        original_case = case == "WF-witness"
        fault_exe = (
            self.build_f_effect_loss(directory) if control == "f-effect" else None
        )

        def game(name):
            result = Game(
                ROOT / "dnethackdir",
                self.clock,
                wizard=True,
                asset_pool=self.asset_pool,
                executable=fault_exe
                if name == "record" and fault_exe
                else self.two_family_exe,
                root=directory / name,
            )
            self.addCleanup(result.close)
            (result.game / "detailed-native").touch()
            return result

        bootstrap = game("bootstrap")
        bootstrap.start()
        slot = load(bootstrap.game / "fixture.json")["letter"]
        bootstrap.more(bootstrap.send("a"))
        bootstrap.more(bootstrap.send(slot))
        bootstrap.more(bootstrap.send("q"))
        bootstrap.more(bootstrap.send("y"))
        source = fixture_sources()[0 if program == "state" else 1]
        transport = author.FakeAuthorTransport(response(source))
        authored = author.author_offline(
            bootstrap.run, transport=transport, validator=self.validator
        )
        self.assertEqual(authored["status"], "envelope_published_not_admitted")
        self.assertEqual(authored["validation"], "native_parser_and_load")
        self.assertEqual(authored["source_sha256"], hashlib.sha256(source).hexdigest())
        self.assertEqual(len(transport.calls), 1)
        envelope = bootstrap.run / "next_use-envelope.json"
        (bootstrap.root / "fixture-envelope.json").write_bytes(envelope.read_bytes())
        (bootstrap.root / "fixture-source.lua").write_bytes(source)
        bootstrap.sanity(60)
        envelope.unlink()
        self.assertFalse((bootstrap.run / "next_use.lua").exists())
        self.assertEqual(bootstrap.save(), 0)
        initial = load(bootstrap.game / "state.json")
        self.assertEqual((initial["callback_w"], initial["callback_f"]), (0, 0))
        self.assertEqual((initial["slot_w"], initial["slot_f"]), (1, 1))
        self.assertEqual(initial["spent"], 2)
        self.assertEqual(initial["source_sha256"], hashlib.sha256(source).hexdigest())
        identity = load(bootstrap.game / "identity.json")
        self.assertEqual(initial["run_token"], identity["game_token"])
        self.assertEqual(
            (bootstrap.run / "next_use-owner").read_text(),
            f"NUO1:{identity['game_token']:016x}\n",
        )
        prefix = (bootstrap.run / "next_use-journal.jsonl").read_bytes()
        prefix_result = read_journal(bootstrap.run / "next_use-journal.jsonl")
        self.assertEqual(prefix_result["status"], "incomplete")
        self.assertEqual(len(prefix_result["records"]), initial["replay_cursor"] + 1)
        self.assertEqual(initial["journal_bytes"], len(prefix))
        self.assertEqual(
            initial["journal_sha256"], json.loads(prefix.splitlines()[-1])["sha256"]
        )
        (bootstrap.root / "initial.json").write_text(json.dumps(initial, indent=2))
        (bootstrap.root / "prefix-status.json").write_text(
            json.dumps(
                {
                    "header_only": len(prefix_result["records"]) == 1,
                    "cursor": initial["replay_cursor"],
                    "fake_author_fixture": True,
                    "ordinary_play": False,
                    "rng_saved": False,
                },
                indent=2,
            )
        )
        saves = list((bootstrap.game / "save").iterdir())
        self.assertEqual(len(saves), 1)
        self.assertEqual(saves[0].read_bytes().count(source), 1)
        receipt = (bootstrap.run / "next_use-receipt.jsonl").read_bytes()
        self.assertEqual(len(receipt.splitlines()), 1)

        def clone(name):
            result = game(name)
            retain_tree(bootstrap.game / "save", result.game / "save")
            retain_tree(bootstrap.run, result.run)
            for filename in ("fixture.json", "identity.json"):
                shutil.copy2(bootstrap.game / filename, result.game / filename)
            self.assertEqual(
                (result.game / "save" / saves[0].name).read_bytes(),
                saves[0].read_bytes(),
            )
            self.assertEqual(
                (result.run / "next_use-journal.jsonl").read_bytes(), prefix
            )
            self.assertFalse((result.run / "next_use-envelope.json").exists())
            self.assertFalse((result.run / "next_use.lua").exists())
            if unpublished:
                # Real unsupported presentation route, never a witness setter.
                (result.game / "deny-w-message").touch()
            return result

        record = clone("record")
        if control:
            self.control_record = record
            if control in ("w-bypass", "f-effect"):
                marker = "bypass-w-native" if control == "w-bypass" else "lose-f-effect"
                (record.game / marker).touch()
        InputTape(record)
        schedule = []
        states = []

        def step(g, kind, value=None, expected_end=None):
            if kind == "start":
                g.start()
            elif kind == "send":
                g.more(g.send(value))
            elif kind == "save":
                marker = g.game / "lose-witness-on-save"
                if control == "witness-save":
                    marker.touch()
                try:
                    self.assertEqual(g.save(), 0)
                finally:
                    if control == "witness-save":
                        marker.unlink()
                retain_tree(g.game / "save", g.root / "middle-save")
                retain_tree(g.run, g.root / "middle-prefix")
            elif kind == "quit":
                self.assertEqual(g.quit(), 0)
            else:
                raise AssertionError("unknown tape operation")
            if expected_end is not None:
                self.assertEqual(len(g.inputs), expected_end)
            return load(g.game / "state.json")

        whistle = [("send", "a"), ("send", slot)] + [("send", ".")] * 7
        fountain = [("send", "q"), ("send", "y")]
        operations = {"W": whistle, "F": fountain}
        for kind, value in (
            [("start", None)]
            + operations[order[0]]
            + [("save", None), ("start", None)]
            + operations[order[1]]
            + [("send", ".")] * 4
            + [("quit", None)]
        ):
            begin = len(record.inputs)
            states.append(step(record, kind, value))
            # Persist before any oracle: early physical failures must retain
            # genuine native state/inputs rather than reconstructed JSON.
            schedule.append(dict(kind=kind, begin=begin, end=len(record.inputs)))
            (record.root / "schedule.json").write_text(json.dumps(schedule, indent=2))
            (record.root / "states.json").write_text(json.dumps(states, indent=2))
            record.save_artifacts()
            if len(states) == 1:
                # Native restore legitimately appends a zero-output boundary.
                # Check all saved gameplay fields without changing either state.
                for key in initial:
                    if key not in ("replay_cursor", "journal_bytes", "journal_sha256"):
                        self.assertEqual(states[0][key], initial[key], key)
            if kind == "start" and len(states) > 1:
                # Preserve the original W attention anchor or still-pending W,
                # not a newly armed window after the new-process restore.
                for key in (
                    "state",
                    "callback_ordinal",
                    "callback_w",
                    "callback_f",
                    "slot_w",
                    "slot_f",
                    "w_runtime",
                    "witnessed",
                    "attention_claimed",
                    "activation_monstermoves",
                    "armed_m_id",
                    "armed_root",
                    "source_sha256",
                ):
                    self.assertEqual(
                        states[-1][key],
                        states[-2][key],
                        "preserved-witness oracle" if key == "witnessed" else key,
                    )
            if kind == "save":
                middle = states[-1]
                self.assertEqual(middle["callback_ordinal"], 1)
                self.assertEqual(middle["callback_w"], int(order == "WF"))
                self.assertEqual(middle["callback_f"], int(order == "FW"))
                self.assertEqual(
                    middle["state"], int(program == "state" and order == "WF")
                )
                self.assertEqual(
                    middle["witnessed"],
                    int(order == "WF" and not unpublished),
                    "native W witnessed at middle Save",
                )
                if order == "WF":
                    self.assertEqual(middle["slot_f"], 1)
                    self.assertEqual(middle["attention_claimed"], 1)
                    self.assertEqual(middle["w_runtime"], 1)
                    self.assertGreaterEqual(
                        middle["monstermoves"], middle["activation_monstermoves"] + 5
                    )
                    self.assertLess(
                        middle["monstermoves"], middle["activation_monstermoves"] + 10
                    )
                else:
                    self.assertEqual(middle["slot_w"], 1)
                    self.assertEqual(middle["slot_f"], 2)
                    self.assertEqual(middle["attention_claimed"], 0)
        self.assertTrue(
            (record.game / "physical.jsonl").exists(), "missing physical evidence"
        )
        physical = [
            json.loads(line)
            for line in (record.game / "physical.jsonl").read_text().splitlines()
        ]
        witnesses = [r for r in physical if r["kind"] == "W"]
        drinks = [r for r in physical if r["kind"] == "F"]
        self.assertEqual(len(witnesses), 1)
        self.assertEqual(len(drinks), 1)
        w, f = witnesses[0], drinks[0]
        self.assertEqual(w["delivered"], int(not unpublished))
        self.assertEqual(w["witnessed"], int(not unpublished))
        self.assertEqual(w["displaced"], 1)
        self.assertEqual(w["notice"] > 0, not unpublished)
        self.assertEqual(
            [r["kind"] for r in physical if r["kind"] in ("W", "F")], list(order)
        )
        self.assertNotEqual(w["before"], w["after"])
        self.assertEqual(w["after"], w["actual"])
        self.assertEqual(
            f["hunger_after"] - f["hunger_before"],
            4 if refresh else 0,
            "native F hunger oracle",
        )
        # Existing Unix calibration: native fate 11 emits DEFAULT outcome 4.
        self.assertEqual(f["outcome"], 6 if refresh else 4)
        self.assertEqual(states[-1]["callback_ordinal"], 2)
        self.assertEqual(states[-1]["spent"], 2)

        files = {
            "save": saves[0],
            "initial": bootstrap.root / "initial.json",
            "source": bootstrap.root / "fixture-source.lua",
            "envelope": bootstrap.root / "fixture-envelope.json",
            "helper": ROOT / "tests/chaos/next_use_unix_game.c",
            "rng_policy": ROOT / "tests/chaos/native_rng.h",
            "clock_policy": ROOT / "tests/chaos/replay_clock.c",
            "schema": ROOT / "chaos/next_use_journal.py",
            "driver": ROOT / "tests/chaos/test_next_use_native_playback.py",
            "semantic_bridge": ROOT / "tests/chaos/next_use_semantic_preflight.py",
            "semantic_c": ROOT / "tests/chaos/next_use_semantic_preflight.c",
            "semantic_runtime": ROOT / "src/chaos_next_use_runtime.c",
            "semantic_runtime_header": ROOT / "include/chaos_next_use_runtime.h",
            "semantic_vm": ROOT / "src/chaos_next_use.c",
            "semantic_lua": ROOT / "src/chaos_lua.c",
            "semantic_admission": ROOT / "src/chaos_next_use_admission.c",
            "semantic_protocol": ROOT / "src/chaos_protocol.c",
            "game_driver": ROOT / "tests/chaos/gameplay_support.py",
            "build_commands": self.artifacts / "build-commands.json",
            "compiled_inputs": self.artifacts / "compiled-inputs.json",
            "rng_objects": ROOT / "tests/chaos/native_rng.py",
            "initial_identity": bootstrap.game / "identity.json",
            "fixture": bootstrap.game / "fixture.json",
            "binary": self.two_family_exe,
            "clock": self.clock,
            "native_data": record.game / "nhdat",
        }
        for capture_directory, label in (
            (bootstrap.run, "prefix"),
            (record.run, "record"),
        ):
            files.update(
                {
                    label + "/" + p.name: p
                    for p in capture_directory.iterdir()
                    if p.is_file()
                }
            )
        for name in (
            "inputs.json",
            "schedule.json",
            "states.json",
            "terminal.raw",
            "manifest.json",
        ):
            files[name] = record.root / name
        for name in ("physical.jsonl", "native.jsonl", "capture.json", "identity.json"):
            files[name] = record.game / name
        for dirname in ("middle-save", "middle-prefix"):
            files.update(
                {
                    dirname + "/" + p.name: p
                    for p in (record.root / dirname).iterdir()
                    if p.is_file()
                }
            )
        trusted = {name: digest(p) for name, p in files.items()}
        (directory / "bundle-digests.json").write_text(json.dumps(trusted, indent=2))
        args = (
            files,
            trusted,
            record.run / "next_use-journal.jsonl",
            record.game / "capture.json",
            bootstrap.root / "initial.json",
            source,
        )
        original_inputs = (record.root / "inputs.json").read_bytes()
        tampered_inputs = directory / "tampered-inputs.json"
        tampered_inputs.write_bytes(b'["2e"]')
        altered_files = dict(files, **{"inputs.json": tampered_inputs})
        with self.assertRaisesRegex(AssertionError, "bundle digest: inputs.json"):
            preflight(altered_files, *args[1:])
        self.assertEqual((record.root / "inputs.json").read_bytes(), original_inputs)
        decoded = preflight(
            *args
        )  # Before playback Game.start (including all auto bytes).
        from next_use_semantic_preflight import validate_bundle, exercise_negatives

        semantic = validate_bundle(decoded, files, directory)
        transitions = [r for r in decoded["records"] if r["kind"] == "transition"]
        self.assertEqual(semantic["accepted"], len(transitions))
        actions = [r["data"] for r in transitions if r["data"]["operation"] == 1]
        self.assertEqual(
            [t["family"] for t in actions], [{"W": 1, "F": 2}[f] for f in order]
        )
        f_action = next(t for t in actions if t["family"] == 2)
        intents = [
            r["data"]["intent"]["op"]
            for r in f_action["private_records"]
            if r["kind"] == 3
        ]
        self.assertEqual(intents, [3 if refresh else 0])
        # Quiet may terminate in ACTION without an active F-result transition.
        # Judge its native effect separately above, not by inventing a result.
        public_w = [
            p
            for t in transitions
            for p in t["data"]["public_records"]
            if p["family"] == 1
        ]
        self.assertEqual(len(public_w), int(not unpublished))
        if public_w:
            self.assertEqual(public_w[0]["root"], w["root"])
            self.assertEqual(public_w[0]["notice_seq"], w["notice"])
        self.assertEqual(semantic["checkpoints"], 1)
        self.assertEqual(semantic["terminal"], 1)
        if original_case:
            with patch.object(
                Game,
                "start",
                side_effect=AssertionError("negative launched native playback"),
            ) as start:
                exercise_negatives(self, decoded, files, directory)
                start.assert_not_called()
        playback = clone("playback")
        for original in bootstrap.run.iterdir():
            if original.is_file():
                self.assertEqual(
                    digest(playback.run / original.name),
                    trusted["prefix/" + original.name],
                )
        self.assertEqual(digest(playback.game / "dnethack"), trusted["binary"])
        self.assertEqual(digest(playback.game / "nhdat"), trusted["native_data"])
        self.assertEqual(
            digest(playback.game / "save" / saves[0].name), trusted["save"]
        )
        tape = InputTape(playback, load(record.root / "inputs.json"))
        for expected_state, operation in zip(
            states, load(record.root / "schedule.json")
        ):
            self.assertEqual(tape.cursor, operation["begin"])
            value = (
                bytes.fromhex(tape.expected[tape.cursor])
                if operation["kind"] == "send"
                else None
            )
            actual = step(playback, operation["kind"], value, operation["end"])
            self.assertEqual(actual, expected_state)
        self.assertEqual(tape.cursor, len(tape.expected))
        self.assertEqual(playback.sessions, record.sessions)
        self.assertEqual(len(transport.calls), 1)
        for g in (record, playback):
            self.assertEqual((g.run / "next_use-receipt.jsonl").read_bytes(), receipt)
            self.assertFalse((g.run / "next_use-envelope.json").exists())
            self.assertFalse((g.run / "next_use.lua").exists())
            actual = read_journal(
                g.run / "next_use-journal.jsonl",
                capture_status=load(g.game / "capture.json"),
            )
            self.assertEqual(actual, decoded)
            self.assertTrue(
                (g.run / "next_use-journal.jsonl")
                .read_bytes()
                .startswith(
                    (g.root / "middle-prefix/next_use-journal.jsonl").read_bytes()
                )
            )
        for name in (
            "native.jsonl",
            "physical.jsonl",
            "state.json",
            "identity.json",
            "capture.json",
        ):
            self.assertEqual(
                (record.game / name).read_bytes(),
                (playback.game / name).read_bytes(),
                name,
            )
        for name in (
            "events.jsonl",
            "next_use-journal.jsonl",
            "next_use-schedule.jsonl",
            "whispers.jsonl",
        ):
            a, b = record.run / name, playback.run / name
            self.assertEqual(a.exists(), b.exists())
            if a.exists():
                self.assertEqual(a.read_bytes(), b.read_bytes(), name)
        reference, candidate = read_native(record.root), read_native(playback.root)
        validate_native(reference)
        validate_native(candidate)
        compare_runs(reference, candidate)
        (directory / "playback-result.json").write_text(
            json.dumps(
                {
                    "status": "exact_native_pair",
                    "transitions": len(decoded["records"]) - 2,
                    "input_chunks": len(tape.expected),
                    "initial_cursor": initial["replay_cursor"],
                    "typed_c_preflight": semantic,
                    "validator_negative_count": 4 if original_case else 0,
                    "case": case,
                    "source_sha256": hashlib.sha256(source).hexdigest(),
                    "fountain_hunger_delta": f["hunger_after"] - f["hunger_before"],
                    "fountain_outcome": f["outcome"],
                    "w_delivered": w["delivered"],
                    "rng_saved": False,
                    "ordinary_play": False,
                },
                indent=2,
            )
        )
