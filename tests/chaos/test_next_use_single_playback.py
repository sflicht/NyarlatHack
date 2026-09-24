"""Single-capability controlled wizard pairs; not ordinary or saved-RNG replay.

Use the unchanged Unix fixture's declared clock/reset policy and normal commands.
Exact fixed-menu publication is admission input, not an authorship claim.
"""

import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from chaos.next_use_envelope import engine_run_hex, publish_envelope
from chaos.next_use_journal import read_journal
from gameplay_support import Game, ROOT
from next_use_semantic_preflight import validate_bundle
from test_episode_turnloop_oracle import compare_runs, read_native, validate_native
from test_next_use_native_playback import (
    InputTape,
    digest,
    load,
    preflight,
    retain_tree,
)
import test_next_use_native_playback as playback_support
import test_next_use_unix_save as unix_save


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class SingleFamilyPlaybackTests(unittest.TestCase):
    # Import modules, never another TestCase into discovery's namespace.
    setUpClass = classmethod(unix_save.NextUseUnixSaveTests.setUpClass.__func__)
    _build_two_family_game = classmethod(
        unix_save.NextUseUnixSaveTests._build_two_family_game.__func__
    )
    tearDownClass = classmethod(
        playback_support.NativePlaybackTests.tearDownClass.__func__
    )

    def test_w_only_recorded_input_native_playback(self):
        self.exercise("W")

    def test_f_only_recorded_input_native_playback(self):
        self.exercise("F")

    def exercise(self, family):
        self._build_two_family_game()
        directory = self.artifacts / family
        directory.mkdir()
        shutil.copy2(__file__, directory / Path(__file__).name)
        with patch.dict(
            os.environ,
            {"NYARLATHACK_NEXT_USE_ADMIT": "1", "NYARLATHACK_OBSERVATIONS": "1"},
        ):
            self.pair(family, directory)

    def pair(self, family, directory):
        def game(name):
            result = Game(
                ROOT / "dnethackdir",
                self.clock,
                wizard=True,
                asset_pool=self.asset_pool,
                executable=self.two_family_exe,
                root=directory / name,
            )
            self.addCleanup(result.close)
            (result.game / "detailed-native").touch()
            return result

        bootstrap = game("bootstrap")
        bootstrap.start()
        slot = load(bootstrap.game / "fixture.json")["letter"]
        action = ("a", slot) if family == "W" else ("q", "y")
        for value in action:
            bootstrap.more(bootstrap.send(value))
        operation = "whistling" if family == "W" else "fountain_drink"
        notices = [
            e
            for e in bootstrap.events()
            if e.get("observation", {}).get("operation") == operation
            and e["observation"]["stage"] == "notice"
        ]
        self.assertEqual(len(notices), 1)
        notice = notices[0]
        root = notice["observation"]["root_seq"]
        ends = [
            e
            for e in bootstrap.events()
            if e.get("observation", {}).get("root_seq") == root
            and e["observation"]["stage"] == "completed"
        ]
        self.assertEqual(len(ends), 1)
        self.assertEqual(
            notice["observation"]["fact"],
            "sound_high" if family == "W" else "water_refreshed",
        )
        state = load(bootstrap.game / "state.json")
        published = publish_envelope(
            bootstrap.run,
            dict(
                family=family,
                op="whistle_attention" if family == "W" else "fountain_refresh",
                origin=dict(
                    root_seq=root,
                    notice_seq=notice["seq"],
                    end_seq=ends[0]["seq"],
                    fact=notice["observation"]["fact"],
                ),
            ),
            dict(
                at=state["safe"] + 1,
                id=1,
                variant=0,
                level_dnum=state["dnum"],
                level_dlevel=state["dlevel"],
                move=notice["turn"],
                run=engine_run_hex(bootstrap.run),
            ),
        )
        self.assertEqual(published["status"], "envelope_published_not_admitted")
        envelope = bootstrap.run / "next_use-envelope.json"
        payload = load(envelope)
        self.assertEqual(payload["operations"], [family])
        self.assertEqual(payload["cost"], 1)
        source = payload["source"].encode("ascii")
        (bootstrap.root / "source.lua").write_bytes(source)
        (bootstrap.root / "envelope.json").write_bytes(envelope.read_bytes())
        bootstrap.sanity(60)
        envelope.unlink()
        self.assertFalse((bootstrap.run / "next_use.lua").exists())
        self.assertEqual(bootstrap.save(), 0)
        initial = load(bootstrap.game / "state.json")
        self.assertEqual(initial["spent"], 1)
        self.assertEqual(initial["attempted"], 1)
        self.assertEqual(
            (initial["slot_w"], initial["slot_f"]), (1, 0) if family == "W" else (0, 1)
        )
        self.assertEqual(initial["callback_ordinal"], 0)
        self.assertEqual(
            initial["source_sha256"], digest(bootstrap.root / "source.lua")
        )
        self.assertEqual(
            initial["run_token"], load(bootstrap.game / "identity.json")["game_token"]
        )
        self.assertEqual(
            (bootstrap.run / "next_use-owner").read_text(),
            f"NUO1:{initial['run_token']:016x}\n",
        )
        (bootstrap.root / "initial.json").write_text(json.dumps(initial, indent=2))
        saves = list((bootstrap.game / "save").iterdir())
        self.assertEqual(len(saves), 1)
        self.assertEqual(saves[0].read_bytes().count(source), 1)
        prefix = (bootstrap.run / "next_use-journal.jsonl").read_bytes()
        receipt = (bootstrap.run / "next_use-receipt.jsonl").read_bytes()
        self.assertEqual(len(receipt.splitlines()), 1)
        self.assertEqual(json.loads(receipt)["kind"], 2)

        def clone(name):
            g = game(name)
            retain_tree(bootstrap.game / "save", g.game / "save")
            retain_tree(bootstrap.run, g.run)
            for name in ("fixture.json", "identity.json"):
                shutil.copy2(bootstrap.game / name, g.game / name)
            self.assertEqual(
                (g.game / "save" / saves[0].name).read_bytes(), saves[0].read_bytes()
            )
            self.assertEqual((g.run / "next_use-journal.jsonl").read_bytes(), prefix)
            self.assertFalse((g.run / "next_use-envelope.json").exists())
            self.assertFalse((g.run / "next_use.lua").exists())
            return g

        def step(g, kind, value=None):
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
                raise AssertionError(kind)
            return load(g.game / "state.json")

        record = clone("record")
        InputTape(record)
        schedule, states = [], []

        def take(kind, value=None):
            begin = len(record.inputs)
            states.append(step(record, kind, value))
            schedule.append(dict(kind=kind, begin=begin, end=len(record.inputs)))
            return states[-1]

        restored = take("start")
        for key in initial:
            if key not in ("replay_cursor", "journal_bytes", "journal_sha256"):
                self.assertEqual(restored[key], initial[key], key)
        for value in action:
            take("send", value)
        if family == "W":
            # Same eligible A+5 decision and inside-A+10 checkpoint as Unix gate.
            while not states[-1]["witnessed"]:
                self.assertLess(
                    states[-1]["monstermoves"],
                    states[-1]["activation_monstermoves"] + 10,
                )
                take("send", ".")
        checkpoint = take("save")
        self.assertEqual(checkpoint["callback_ordinal"], 1)
        self.assertEqual(checkpoint["slot_" + family.lower()], 2)
        self.assertEqual(checkpoint["slot_" + ("f" if family == "W" else "w")], 0)
        restored = take("start")
        self.assertEqual(checkpoint["journal_state"], 1 if family == "W" else 2)
        for key in checkpoint:
            if family == "F" or key not in (
                "replay_cursor",
                "journal_bytes",
                "journal_sha256",
            ):
                self.assertEqual(restored[key], checkpoint[key], key)
        if family == "W":
            self.assertEqual(checkpoint["attention_claimed"], 1)
            self.assertEqual(checkpoint["witnessed"], 1)
            deadline = checkpoint["activation_monstermoves"] + 10
            self.assertLess(checkpoint["monstermoves"], deadline)
            while states[-1]["monstermoves"] <= deadline:
                self.assertEqual(states[-1]["w_runtime"], 1)
                take("send", ".")
            self.assertEqual(states[-1]["w_runtime"], 2)
            self.assertEqual(
                load(record.game / "window-ended.json"),
                dict(monstermoves=deadline, activation_monstermoves=deadline - 10),
            )
        # Reuse the same physical action after consumption/expiry; never reinstall.
        for value in action:
            take("send", value)
        if family == "W":
            retry_deadline = states[-1]["monstermoves"] + 10
            while states[-1]["monstermoves"] <= retry_deadline:
                take("send", ".")
        take("quit")
        for key in (
            "spent",
            "callback_ordinal",
            "callback_w",
            "callback_f",
            "slot_w",
            "slot_f",
            "attention_claimed",
            "witnessed",
            "activation_monstermoves",
            "source_sha256",
            "run_token",
            "armed_m_id",
            "attempted",
        ):
            self.assertEqual(states[-1][key], checkpoint[key], key)
        if family == "F":
            self.assertEqual(
                (record.run / "next_use-journal.jsonl").read_bytes(),
                (record.root / "middle-prefix/next_use-journal.jsonl").read_bytes(),
            )
        self.assertEqual(states[-1]["journal_state"], 2)
        self.assertEqual(states[-1]["termination_emitted"], 1)
        (record.root / "schedule.json").write_text(json.dumps(schedule, indent=2))
        (record.root / "states.json").write_text(json.dumps(states, indent=2))
        physical = [
            json.loads(s)
            for s in (record.game / "physical.jsonl").read_text().splitlines()
        ]
        witnesses = [r for r in physical if r["kind"] == "W"]
        drinks = [r for r in physical if r["kind"] == "F"]
        if family == "W":
            self.assertEqual(len(witnesses), 1)
            self.assertEqual(drinks, [])
            w = witnesses[0]
            self.assertNotEqual(w["before"], w["after"])
            self.assertEqual(w["after"], w["actual"])
            self.assertEqual(
                (w["delivered"], w["witnessed"], w["displaced"]), (1, 1, 1)
            )
            attention = [
                e["observation"]
                for e in record.events()
                if e.get("observation", {}).get("operation") == "whistle_attention"
            ]
            self.assertEqual(
                [e["stage"] for e in attention], ["started", "notice", "completed"]
            )
            self.assertEqual(attention[1]["fact"], "attention")
            published = next(e for e in record.events() if e["seq"] == w["notice"])
            self.assertEqual(published["observation"], attention[1])
            self.assertEqual(attention[1]["root_seq"], w["root"])
            self.assertEqual(
                w["pet_id"], load(bootstrap.game / "fixture.json")["pet_id"]
            )
            self.assertGreaterEqual(w["monstermoves"], deadline - 5)
            self.assertLess(w["monstermoves"], deadline)
        else:
            self.assertEqual(witnesses, [])
            self.assertEqual([r["outcome"] for r in drinks], [6, 4])
            self.assertEqual(
                [r["hunger_after"] - r["hunger_before"] for r in drinks], [4, 0]
            )

        files = dict(
            save=saves[0],
            initial=bootstrap.root / "initial.json",
            source=bootstrap.root / "source.lua",
            envelope=bootstrap.root / "envelope.json",
            binary=self.two_family_exe,
            clock=self.clock,
            native_data=record.game / "nhdat",
            fixture=bootstrap.game / "fixture.json",
            initial_identity=bootstrap.game / "identity.json",
            schema=ROOT / "chaos/next_use_journal.py",
            publisher=ROOT / "chaos/next_use_envelope.py",
            composition=ROOT / "chaos/next_use_compose.py",
            runtime_header=ROOT / "include/chaos_next_use_runtime.h",
        )
        for name in (
            "next_use_unix_game.c",
            "native_rng.h",
            "native_rng.py",
            "replay_clock.c",
            "gameplay_support.py",
            "test_next_use_single_playback.py",
            "test_next_use_native_playback.py",
            "next_use_semantic_preflight.py",
            "next_use_semantic_preflight.c",
        ):
            files[name] = ROOT / "tests/chaos" / name
        for name in (
            "chaos_next_use_runtime.c",
            "chaos_next_use.c",
            "chaos_lua.c",
            "chaos_next_use_admission.c",
            "chaos_protocol.c",
        ):
            files[name] = ROOT / "src" / name
        for name in ("build-commands.json", "compiled-inputs.json"):
            files[name] = self.artifacts / name
        for name in (
            "inputs.json",
            "schedule.json",
            "states.json",
            "terminal.raw",
            "manifest.json",
        ):
            files[name] = record.root / name
        for name in ("physical.jsonl", "native.jsonl", "identity.json", "capture.json"):
            files[name] = record.game / name
        for path, label in (
            (bootstrap.run, "prefix"),
            (record.run, "record"),
            (record.root / "middle-save", "middle-save"),
            (record.root / "middle-prefix", "middle-prefix"),
        ):
            files.update(
                {label + "/" + p.name: p for p in path.iterdir() if p.is_file()}
            )
        trusted = {k: digest(p) for k, p in files.items()}
        (directory / "bundle-digests.json").write_text(json.dumps(trusted, indent=2))
        decoded = preflight(
            files,
            trusted,
            record.run / "next_use-journal.jsonl",
            record.game / "capture.json",
            bootstrap.root / "initial.json",
            source,
        )
        semantic = validate_bundle(decoded, files, directory)
        self.assertEqual(
            semantic["accepted"],
            sum(r["kind"] == "transition" for r in decoded["records"]),
        )
        self.assertEqual((semantic["checkpoints"], semantic["terminal"]), (1, 1))
        playback = clone("playback")
        self.assertEqual(digest(playback.game / "dnethack"), trusted["binary"])
        self.assertEqual(digest(playback.game / "nhdat"), trusted["native_data"])
        tape = InputTape(playback, load(record.root / "inputs.json"))
        for expected, op in zip(states, schedule):
            self.assertEqual(tape.cursor, op["begin"])
            value = (
                bytes.fromhex(tape.expected[tape.cursor])
                if op["kind"] == "send"
                else None
            )
            self.assertEqual(step(playback, op["kind"], value), expected)
            self.assertEqual(tape.cursor, op["end"])
        self.assertEqual(tape.cursor, len(tape.expected))
        self.assertEqual(playback.sessions, record.sessions)
        for g in (record, playback):
            self.assertEqual((g.run / "next_use-receipt.jsonl").read_bytes(), receipt)
            self.assertFalse((g.run / "next_use-envelope.json").exists())
            self.assertFalse((g.run / "next_use.lua").exists())
            self.assertEqual(
                read_journal(
                    g.run / "next_use-journal.jsonl",
                    capture_status=load(g.game / "capture.json"),
                ),
                decoded,
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
        (directory / "playback-result.json").write_text(
            json.dumps(
                dict(
                    status="exact_native_pair",
                    family=family,
                    ordinary_play=False,
                    rng_saved=False,
                    typed_c_preflight=semantic,
                    input_chunks=len(tape.expected),
                ),
                indent=2,
            )
        )
