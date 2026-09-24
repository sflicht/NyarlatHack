"""R1: controlled Unix-fixture playback, not ordinary play or saved-RNG replay.

Fake author bootstrap is a labelled fixture, not an intelligence claim. Typed C
semantic preflight and rehashed tamper/matrix coverage remain a later stage.
"""

import hashlib
import json
import os
import shutil
import unittest
from unittest.mock import patch

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
        # Only this suite's completed compiled copies; retain saves and evidence.
        for pattern in ("*.o", "*.so", "dnethack", "*/game/dnethack", "*/game/nhdat"):
            for path in cls.artifacts.glob(pattern):
                path.unlink()
        shutil.rmtree(cls.asset_pool, ignore_errors=True)

    def test_same_admitted_save_w_checkpoint_f_exact_input_playback(self):
        self._build_two_family_game()
        shutil.copy2(__file__, self.artifacts / "test_next_use_native_playback.py")
        with patch.dict(
            os.environ,
            {"NYARLATHACK_NEXT_USE_ADMIT": "1", "NYARLATHACK_OBSERVATIONS": "1"},
        ):
            self.exercise()

    def exercise(self):
        def game(name):
            result = Game(
                ROOT / "dnethackdir",
                self.clock,
                wizard=True,
                asset_pool=self.asset_pool,
                executable=self.two_family_exe,
                root=self.artifacts / name,
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
        source = fixture_sources()[1]
        transport = author.FakeAuthorTransport(response(source))
        authored = author.author_offline(
            bootstrap.run, transport=transport, validator=self.validator
        )
        self.assertEqual(authored["status"], "envelope_published_not_admitted")
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
            return result

        record = clone("record")
        InputTape(record)
        schedule = []
        states = []

        def step(g, kind, value=None, expected_end=None):
            if kind == "start":
                g.start()
            elif kind == "send":
                g.more(g.send(value))
            elif kind == "save":
                self.assertEqual(g.save(), 0)
                retain_tree(g.game / "save", g.root / "middle-save")
                retain_tree(g.run, g.root / "middle-prefix")
            elif kind == "quit":
                self.assertEqual(g.quit(), 0)
            else:
                raise AssertionError("unknown tape operation")
            if expected_end is not None:
                self.assertEqual(len(g.inputs), expected_end)
            return load(g.game / "state.json")

        for kind, value in (
            [("start", None), ("send", "a"), ("send", slot)]
            + [("send", ".")] * 7
            + [("save", None), ("start", None), ("send", "q"), ("send", "y")]
            + [("send", ".")] * 4
            + [("quit", None)]
        ):
            begin = len(record.inputs)
            states.append(step(record, kind, value))
            if len(states) == 1:
                # Native restore legitimately appends a zero-output boundary.
                # Check all saved gameplay fields without changing either state.
                for key in initial:
                    if key not in ("replay_cursor", "journal_bytes", "journal_sha256"):
                        self.assertEqual(states[0][key], initial[key], key)
            if kind == "save":
                self.assertEqual(states[-1]["witnessed"], 1)
                self.assertEqual(states[-1]["callback_w"], 1)
                self.assertEqual(states[-1]["callback_f"], 0)
                self.assertEqual(states[-1]["slot_f"], 1)
            schedule.append(dict(kind=kind, begin=begin, end=len(record.inputs)))
        (record.root / "schedule.json").write_text(json.dumps(schedule, indent=2))
        (record.root / "states.json").write_text(json.dumps(states, indent=2))
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
        self.assertEqual(w["delivered"], 1)
        self.assertEqual(w["witnessed"], 1)
        self.assertNotEqual(w["before"], w["after"])
        self.assertEqual(w["after"], w["actual"])
        self.assertEqual(f["hunger_after"] - f["hunger_before"], 4)
        self.assertEqual(f["outcome"], 6)
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
        for directory, label in ((bootstrap.run, "prefix"), (record.run, "record")):
            files.update(
                {label + "/" + p.name: p for p in directory.iterdir() if p.is_file()}
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
        (self.artifacts / "bundle-digests.json").write_text(
            json.dumps(trusted, indent=2)
        )
        args = (
            files,
            trusted,
            record.run / "next_use-journal.jsonl",
            record.game / "capture.json",
            bootstrap.root / "initial.json",
            source,
        )
        original_inputs = (record.root / "inputs.json").read_bytes()
        tampered_inputs = self.artifacts / "tampered-inputs.json"
        tampered_inputs.write_bytes(b'["2e"]')
        altered_files = dict(files, **{"inputs.json": tampered_inputs})
        with self.assertRaisesRegex(AssertionError, "bundle digest: inputs.json"):
            preflight(altered_files, *args[1:])
        self.assertEqual((record.root / "inputs.json").read_bytes(), original_inputs)
        decoded = preflight(
            *args
        )  # Before playback Game.start (including all auto bytes).
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
        for name in ("native.jsonl", "physical.jsonl", "identity.json", "capture.json"):
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
        (self.artifacts / "playback-result.json").write_text(
            json.dumps(
                {
                    "status": "exact_native_pair",
                    "transitions": len(decoded["records"]) - 2,
                    "input_chunks": len(tape.expected),
                    "initial_cursor": initial["replay_cursor"],
                    "typed_c_preflight": False,
                    "ordinary_play": False,
                },
                indent=2,
            )
        )
