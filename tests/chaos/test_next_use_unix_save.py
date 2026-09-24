"""Controlled real Unix next-use save/restore boundaries. Not ordinary play."""

import hashlib
import json
import os
import re
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest

from chaos.next_use_envelope import engine_run_hex, publish_envelope
from gameplay_support import Game, ROOT
from native_rng import controlled_rng_objects


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class NextUseUnixSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert (ROOT / ".chaos-build").read_text().strip() == "1"
        cls.artifacts = Path(tempfile.mkdtemp(prefix="nyarl-next-use-unix-save-"))
        print("NEXT_USE_UNIX_SAVE_ARTIFACTS=" + str(cls.artifacts), flush=True)
        cls.clock = cls.artifacts / "clock.so"
        subprocess.run(
            [
                "cc",
                "-shared",
                "-fPIC",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(ROOT / "tests/chaos/replay_clock.c"),
                "-ldl",
                "-o",
                str(cls.clock),
            ],
            check=True,
            timeout=30,
        )

    @classmethod
    def _build_two_family_game(cls):
        if hasattr(cls, "two_family_exe"):
            return
        commands = [
            [
                "objcopy",
                "--redefine-sym",
                "main=original_game_main",
                str(ROOT / "sys/unix/unixmain.o"),
                str(cls.artifacts / "unixmain.o"),
            ]
        ]
        subprocess.run(commands[0], check=True, timeout=30)
        objects = (
            sorted((ROOT / "src").glob("*.o"))
            + [
                ROOT / "sys/unix/unixres.o",
                ROOT / "sys/unix/unixunix.o",
                cls.artifacts / "unixmain.o",
                ROOT / "sys/share/ioctl.o",
                ROOT / "sys/share/unixtty.o",
            ]
            + sorted((ROOT / "win/tty").glob("*.o"))
            + sorted((ROOT / "win/curses").glob("*.o"))
        )
        protected = [
            *objects,
            ROOT / "sys/unix/unixmain.o",
            ROOT / "tests/chaos/native_rng.h",
            ROOT / "tests/chaos/native_rng.py",
            ROOT / "tests/chaos/gameplay_support.py",
        ]
        hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
        objects = controlled_rng_objects(objects, cls.artifacts)
        exe = cls.artifacts / "dnethack"
        wraps = (
            "chaos_start",
            "chaos_observe",
            "rhack",
            "dog_move",
            "chaos_whistle_witness_finalize",
            "drinkfountain",
            "chaos_next_use_fountain_result",
        )
        command = [
            "/usr/bin/cc",
            "-g",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-DCHAOS",
            "-isystem" + str(ROOT / "include"),
            str(ROOT / "tests/chaos/next_use_unix_game.c"),
            *map(str, objects),
            *["-Wl,--wrap=" + name for name in wraps],
            "-lncursesw",
            "-ltinfo",
            "-lm",
            *subprocess.check_output(
                ["/usr/bin/pkg-config", "--libs", "lua5.4"], text=True
            ).split(),
            "-o",
            str(exe),
        ]
        commands.append(command)
        (cls.artifacts / "build-commands.json").write_text(
            json.dumps(commands, indent=2)
        )
        (cls.artifacts / "compiled-inputs.json").write_text(
            json.dumps(hashes, indent=2)
        )
        for name in (
            "next_use_unix_game.c",
            "test_next_use_unix_save.py",
            "replay_clock.c",
            "native_rng.h",
        ):
            shutil.copy2(ROOT / "tests/chaos" / name, cls.artifacts / name)
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (cls.artifacts / "build.log").write_text(result.stdout + result.stderr)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        assert hashes == {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected
        }
        cls.two_family_exe = exe

    def test_save_exit_restore_does_not_readmit(self):
        self._exercise_save_exit_restore(save_before_origin=False)

    def test_empty_save_does_not_spend_the_unused_admission_opportunity(self):
        self._exercise_save_exit_restore(save_before_origin=True)

    def test_pending_departure_save_exit_restore(self):
        self._exercise_save_exit_restore(save_before_origin=False, departure="pending")

    def test_completed_departure_save_exit_restore(self):
        self._exercise_save_exit_restore(
            save_before_origin=False, departure="completed"
        )

    def test_w_save_exit_restore_f_matches_uninterrupted(self):
        self._two_family_order("WF")

    def test_f_save_exit_restore_w_matches_uninterrupted(self):
        self._two_family_order("FW")

    def test_deleted_candidate_after_save_preserves_admitted_continuation(self):
        self._two_family_order("WF", boundary="deleted-candidate")

    def test_replaced_candidate_after_save_preserves_admitted_continuation(self):
        self._two_family_order("WF", boundary="replaced-candidate")

    def test_relocated_transport_preserves_admitted_continuation(self):
        self._two_family_order("WF", boundary="relocated-transport")

    def test_armed_whistle_save_restores_target_before_attention(self):
        self._two_family_order("WF", boundary="armed-whistle")

    def _two_family_order(self, order, *, boundary="unchanged"):
        """Controlled wizard geometry/RNG; NOT ordinary play or #66 evidence."""
        self.assertIn(
            boundary,
            (
                "unchanged",
                "deleted-candidate",
                "replaced-candidate",
                "relocated-transport",
                "armed-whistle",
            ),
        )
        armed_checkpoint = boundary == "armed-whistle"
        if armed_checkpoint:
            self.assertEqual(order, "WF")
        saved = {
            key: os.environ.get(key)
            for key in ("NYARLATHACK_NEXT_USE_ADMIT", "NYARLATHACK_OBSERVATIONS")
        }

        def restore_env():
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.addCleanup(restore_env)
        os.environ.update({key: "1" for key in saved})
        # Exact pre-existing handwritten wf-families source, not #67 authorship.
        old = (ROOT / "tests/chaos/next_use_admit.c").read_text()
        block = old.split('!strcmp(argv[1], "wf-families")', 1)[1]
        block = block.split("static const char src[] =", 1)[1].split(";", 1)[0]
        source = "".join(json.loads(s) for s in re.findall(r'"(?:[^"\\]|\\.)*"', block))
        sha = hashlib.sha256(source.encode("ascii")).hexdigest()
        results = []
        for interrupted in (False, True):
            game = Game(
                ROOT / "dnethackdir",
                self.clock,
                wizard=True,
                root=self.artifacts
                / (
                    order
                    + "-"
                    + boundary
                    + ("-restore" if interrupted else "-continuous")
                ),
            )
            self.addCleanup(game.close)
            self._build_two_family_game()
            shutil.copy2(self.two_family_exe, game.game / "dnethack")
            game.start()
            self.assertTrue(
                (game.game / "fixture.json").exists(),
                "real Unix game lacks controlled two-family setup",
            )
            fixture = json.loads((game.game / "fixture.json").read_text())
            slot = fixture["letter"].encode()

            def state():
                return json.loads((game.game / "state.json").read_text())

            def native_trace():
                return [
                    json.loads(line)
                    for line in (game.game / "native.jsonl").read_text().splitlines()
                ]

            def whistle():
                self.assertIn(b"apply", game.send("a").lower())
                game.more(game.send(slot))

            def fountain():
                self.assertIn(b"fountain", game.send("q").lower())
                game.more(game.send("y"))

            whistle()
            fountain()
            origins = []
            for family, operation, fact in (
                ("W", "whistling", "ordinary_whistle"),
                ("F", "fountain_drink", "water_refreshed"),
            ):
                notices = [
                    e
                    for e in game.events()
                    if e.get("observation", {}).get("operation") == operation
                    and e["observation"].get("stage") == "notice"
                ]
                self.assertEqual(len(notices), 1, game.events())
                notice = notices[0]
                root = notice["observation"]["root_seq"]
                ends = [
                    e
                    for e in game.events()
                    if e.get("observation", {}).get("root_seq") == root
                    and e["observation"].get("stage") == "completed"
                ]
                self.assertEqual(len(ends), 1)
                self.assertEqual(
                    notice["observation"]["fact"],
                    "sound_high" if family == "W" else "water_refreshed",
                )
                starts = [e for e in game.events() if e["seq"] == root]
                self.assertEqual(len(starts), 1)
                self.assertEqual(
                    starts[0]["observation"],
                    dict(operation=operation, stage="started", root_seq=0, fact="none"),
                )
                self.assertEqual(ends[0]["observation"]["operation"], operation)
                self.assertLess(root, notice["seq"])
                self.assertLess(notice["seq"], ends[0]["seq"])
                origins.append(
                    dict(
                        family=family,
                        fact=fact,
                        root=root,
                        notice_seq=notice["seq"],
                        end_seq=ends[0]["seq"],
                        move=notice["turn"],
                        level_dnum=state()["dnum"],
                        level_dlevel=state()["dlevel"],
                        run=engine_run_hex(game.run),
                    )
                )
            payload = dict(
                at=state()["safe"] + 1,
                cost=2,
                id=1,
                next_use_program_v=2,
                operations=["W", "F"],
                origin_refs=origins,
                source=source,
                source_sha256=sha,
                telegraph="next-use-v2-WF",
                ttl=100,
                variant=0,
            )
            encoded = json.dumps(
                payload, separators=(",", ":"), sort_keys=True
            ).encode()
            envelope = game.run / "next_use-envelope.json"
            envelope.write_bytes(encoded)
            envelope.chmod(0o600)
            # Immutable admission evidence is outside the candidate transport;
            # later deliberate candidate tampering never rewrites this history.
            evidence = game.root / "published-envelope.json"
            evidence.write_bytes(encoded)
            evidence.chmod(0o400)
            expected_envelope = encoded
            original_run = game.run
            original_run_hex = engine_run_hex(original_run)
            original_transport = None
            (game.root / "candidate.lua").write_text(source)
            spent_before = state()["spent"]
            game.sanity(60)
            admitted = state()
            self.assertEqual(admitted["spent"], spent_before + 2, admitted)
            self.assertEqual((admitted["slot_w"], admitted["slot_f"]), (1, 1))
            self.assertEqual(admitted["source_sha256"], sha)
            receipt = (game.run / "next_use-receipt.jsonl").read_bytes()
            admissions = [json.loads(line) for line in receipt.splitlines()]
            self.assertEqual(len(admissions), 1)
            self.assertEqual(admissions[0]["kind"], 2)  # native admission receipt

            def await_attention():
                # Fixed bound: witness at A+5, finish inside (not exactly
                # on) A+10. Never re-whistle to resume an armed saved target.
                game.wait_turns(7)
                self.assertEqual(state()["witnessed"], 1, state())
                self.assertEqual(state()["attention_claimed"], 1)

            def effect(family):
                if family == "W":
                    whistle()
                    await_attention()
                else:
                    fountain()
                    self.assertEqual(state()["slot_f"], 2, state())

            if armed_checkpoint:
                whistle()
            else:
                effect(order[0])
            checkpoint = state()
            self.assertEqual(checkpoint["valid"], 1)
            if armed_checkpoint:
                self.assertEqual(checkpoint["slot_w"], 2)  # consumed, armed
                self.assertEqual(checkpoint["slot_f"], 1)  # still pending
                self.assertEqual(checkpoint["w_runtime"], 1)  # ARMED
                self.assertEqual(checkpoint["witnessed"], 0)
                self.assertEqual(checkpoint["attention_claimed"], 0)
                self.assertEqual(checkpoint["callback_ordinal"], 1)
                self.assertEqual(checkpoint["armed_m_id"], fixture["pet_id"])
                self.assertGreater(checkpoint["armed_root"], origins[0]["root"])
                self.assertGreaterEqual(
                    checkpoint["monstermoves"], checkpoint["activation_monstermoves"]
                )
                self.assertLess(
                    checkpoint["monstermoves"],
                    checkpoint["activation_monstermoves"] + 5,
                )
                self.assertFalse([r for r in native_trace() if r["kind"] == "witness"])
            (game.root / "checkpoint.json").write_text(json.dumps(checkpoint, indent=2))
            if interrupted:
                self.assertEqual(game.save(), 0)
                saves = list((game.game / "save").iterdir())
                self.assertTrue(saves)
                for save in saves:
                    retained = game.root / ("saved-" + save.name)
                    shutil.copy2(save, retained)
                    retained.chmod(0o400)
                if boundary == "deleted-candidate":
                    envelope.unlink()
                    expected_envelope = None
                elif boundary == "replaced-candidate":
                    # Deliberately invalid candidate, not a new authored program.
                    # Only the transport input changes, after the real save/exit.
                    expected_envelope = b'{"test_only_invalid_replacement":true}\n'
                    replacement = game.run / "replacement.tmp"
                    replacement.write_bytes(expected_envelope)
                    replacement.chmod(0o600)
                    replacement.replace(envelope)
                elif boundary == "relocated-transport":
                    original_transport = {
                        str(p.relative_to(original_run)): p.read_bytes()
                        for p in original_run.rglob("*")
                        if p.is_file()
                    }
                    relocated = game.root / "relocated-run"
                    shutil.copytree(original_run, relocated)
                    self.assertNotEqual(
                        original_run.stat().st_ino, relocated.stat().st_ino
                    )
                    # start() and events() both use this exact new transport.
                    # Do not rebind origins, retime or republish the envelope.
                    game.run = relocated
                    envelope = game.run / "next_use-envelope.json"
                    self.assertNotEqual(engine_run_hex(game.run), original_run_hex)
                    self.assertEqual(envelope.read_bytes(), encoded)
                game.start()
                restored = state()
                self.assertEqual(restored["valid"], 1)
                (game.root / "restored.json").write_text(json.dumps(restored, indent=2))
                # Read-only exported fields, never imported/assigned by the test.
                for key in (
                    "moves",
                    "monstermoves",
                    "safe",
                    "state",
                    "slot_w",
                    "slot_f",
                    "w_runtime",
                    "witnessed",
                    "attention_claimed",
                    "callback_ordinal",
                    "source_sha256",
                    "spent",
                    "armed_m_id",
                    "activation_monstermoves",
                    "armed_root",
                    "run_token",
                    "level_token",
                    "origin_w",
                    "origin_f",
                    "origin_w_deadline",
                    "origin_f_deadline",
                    "program_expiry",
                ):
                    self.assertEqual(restored[key], checkpoint[key], key)
                if armed_checkpoint:
                    self.assertLess(
                        restored["monstermoves"],
                        restored["activation_monstermoves"] + 5,
                    )
                    self.assertFalse(
                        [r for r in native_trace() if r["kind"] == "witness"]
                    )
                self.assertEqual(
                    sum(
                        e.get("event") == "session" and e.get("detail") == "restore"
                        for e in game.events()
                    ),
                    1,
                )
            if armed_checkpoint:
                await_attention()
            effect(order[1])
            complete = state()
            self.assertEqual(complete["callback_ordinal"], 2)
            # Retry with the exact expected candidate transport (original,
            # absent, replaced or relocated): never readmit/debit or regain uses.
            game.sanity(40)
            whistle()
            game.wait_turns(10)
            fountain()
            final = state()
            for key in (
                "slot_w",
                "slot_f",
                "witnessed",
                "attention_claimed",
                "callback_ordinal",
                "spent",
            ):
                self.assertEqual(final[key], complete[key], key)
            self.assertEqual(final["spent"], spent_before + 2)
            self.assertEqual(final["source_sha256"], sha)
            self.assertEqual(evidence.read_bytes(), encoded)
            self.assertEqual(
                (game.run / "next_use-receipt.jsonl").read_bytes(), receipt
            )
            self.assertEqual(envelope, game.run / "next_use-envelope.json")
            if expected_envelope is None:
                self.assertFalse(envelope.exists())
            else:
                self.assertEqual(envelope.read_bytes(), expected_envelope)
            if original_transport is not None:
                self.assertEqual(
                    {
                        str(p.relative_to(original_run)): p.read_bytes()
                        for p in original_run.rglob("*")
                        if p.is_file()
                    },
                    original_transport,
                )
                self.assertEqual(final["run_token"], checkpoint["run_token"])
            trace = native_trace()
            witnesses = [r for r in trace if r["kind"] == "witness" and r["delivered"]]
            self.assertEqual(len(witnesses), 1, trace)
            self.assertEqual(witnesses[0]["displaced"], 1)
            self.assertEqual(witnesses[0]["classifier"], 1)
            self.assertEqual(witnesses[0]["pet_id"], fixture["pet_id"])
            if armed_checkpoint:
                self.assertEqual(witnesses[0]["pet_id"], checkpoint["armed_m_id"])
                self.assertGreaterEqual(
                    witnesses[0]["monstermoves"],
                    checkpoint["activation_monstermoves"] + 5,
                )
                self.assertLess(
                    witnesses[0]["monstermoves"],
                    checkpoint["activation_monstermoves"] + 10,
                )
            drinks = [r for r in trace if r["kind"] == "fountain"]
            self.assertEqual(len(drinks), 3)
            # Native contract enum: natural, remapped, default without intent.
            self.assertEqual([drink["outcome"] for drink in drinks], [1, 6, 4])
            self.assertEqual([drink["hunger_delta"] for drink in drinks], [4, 4, 0])
            summary = dict(
                final={
                    k: final[k]
                    for k in (
                        "slot_w",
                        "slot_f",
                        "w_runtime",
                        "witnessed",
                        "attention_claimed",
                        "callback_ordinal",
                        "spent",
                    )
                },
                witnesses=[
                    {k: r[k] for k in ("displaced", "delivered", "classifier")}
                    for r in witnesses
                ],
                drinks=drinks,
                source_sha256=sha,
            )
            (game.root / "continuation-boundary.json").write_text(
                json.dumps(
                    dict(
                        boundary=boundary,
                        interrupted=interrupted,
                        original_run=str(original_run),
                        original_run_hex=original_run_hex,
                        resumed_run=str(game.run),
                        resumed_run_hex=engine_run_hex(game.run),
                        expected_envelope_path=str(envelope),
                        expected_envelope_sha256=(
                            hashlib.sha256(expected_envelope).hexdigest()
                            if expected_envelope is not None
                            else None
                        ),
                        immutable_envelope_sha256=hashlib.sha256(encoded).hexdigest(),
                    ),
                    indent=2,
                )
            )
            (game.root / "assertions.json").write_text(json.dumps(summary, indent=2))
            results.append(summary)
            self.assertEqual(game.quit(), 0)
        self.assertEqual(results[0], results[1])

    def _exercise_save_exit_restore(self, *, save_before_origin, departure=None):
        saved = {
            key: os.environ.get(key)
            for key in ("NYARLATHACK_NEXT_USE_ADMIT", "NYARLATHACK_OBSERVATIONS")
        }

        def restore_env():
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.addCleanup(restore_env)
        os.environ["NYARLATHACK_NEXT_USE_ADMIT"] = "1"
        os.environ["NYARLATHACK_OBSERVATIONS"] = "1"
        game = Game(
            ROOT / "dnethackdir",
            self.clock,
            observe=True,
            wizard=True,
            root=self.artifacts
            / (departure or ("empty-first" if save_before_origin else "save")),
        )
        self.addCleanup(game.close)
        game.start()
        if save_before_origin:
            self.assertEqual(game.save(), 0)
            game.start()
        text = game.send("#wish\n")
        self.assertIn(b"For what do you wish?", text)
        text = game.more(game.send("uncursed tin whistle\n"))
        slot = None
        for line in text.splitlines():
            if b" - " in line and b"whistle" in line.lower():
                slot = line.split(b" - ", 1)[0][-1:]
                break
        self.assertIsNotNone(slot, text)
        text = game.send("a")
        self.assertIn(b"apply", text.lower())
        text = game.more(game.send(slot))
        self.assertIn(b"whistling sound", text)
        notices = [
            event
            for event in game.events()
            if event.get("event") == "observation"
            and event.get("observation", {}).get("stage") == "notice"
            and event["observation"].get("operation") == "whistling"
        ]
        completed = [
            event
            for event in game.events()
            if event.get("event") == "observation"
            and event.get("observation", {}).get("stage") == "completed"
            and event["observation"].get("operation") == "whistling"
        ]
        self.assertEqual(len(notices), 1)
        self.assertEqual(len(completed), 1)
        notice, done = notices[0], completed[0]
        row = {
            "family": "W",
            "op": "quiet",
            "origin": {
                "root_seq": notice["observation"]["root_seq"],
                "notice_seq": notice["seq"],
                "end_seq": done["seq"],
                "fact": notice["observation"]["fact"],
            },
        }
        host = {
            "at": 2,
            "id": 1,
            "level_dlevel": 1,
            "level_dnum": 0,
            "move": notice["turn"],
            "run": engine_run_hex(game.run),
            "variant": 0,
        }
        publish_envelope(game.run, row, host)
        before = game.events()[-1]["spent"]
        text = game.sanity(60)
        self.assertIn(b"The next whistle may call unusual attention.", text)
        text = game.sanity(40)
        self.assertNotIn(b"The next whistle may call unusual attention.", text)
        spent = game.events()[-1]["spent"]
        self.assertEqual(spent, before + 1)
        envelope = game.run / "next_use-envelope.json"
        self.assertTrue(envelope.is_file())
        envelope.unlink()
        if departure == "completed":
            self.assertIn(b"apply", game.send("a").lower())
            self.assertIn(b"whistling sound", game.more(game.send(slot)))
        if departure:
            self.assertIn(b"To what level", game.send("#levelport\n"))
            self.assertIn(b"Dlvl:2", game.more(game.send("2\n")))
        self.assertEqual(game.save(), 0)
        self.assertTrue(list((game.game / "save").iterdir()))
        game.start()
        restored = [
            event
            for event in game.events()
            if event.get("event") == "session" and event.get("detail") == "restore"
        ]
        self.assertEqual(len(restored), 2 if save_before_origin else 1)
        self.assertEqual(restored[-1]["spent"], spent)
        text = game.sanity(80)
        self.assertNotIn(b"The next whistle may call unusual attention.", text)
        self.assertEqual(game.events()[-1]["spent"], spent)
        self.assertEqual(game.quit(), 0)
