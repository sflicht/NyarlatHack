"""Controlled real Unix next-use save/restore boundaries. Not ordinary play."""

import hashlib
import json
import os
import re
import shutil
import struct
from pathlib import Path
import subprocess
import tempfile
import unittest

from chaos import next_use_author as author
from chaos.next_use_envelope import engine_run_hex, publish_envelope
from chaos.next_use_journal import read_journal
from gameplay_support import Game, ROOT
from native_rng import controlled_rng_objects
from test_next_use_offline_author import fixture_sources, response


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class NextUseUnixSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert (ROOT / ".chaos-build").read_text().strip() == "1"
        cls.artifacts = Path(tempfile.mkdtemp(prefix="nyarl-next-use-unix-save-"))
        # One readonly snapshot per unique executable/data image for this suite;
        # all logs, saves, runs and other case files remain private.
        cls.asset_pool = cls.artifacts / "assets"
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
            "chaos_next_use_save",
            "chaos_next_use_restore_bound",
            "chaos_observe",
            "rhack",
            "dog_move",
            "chaos_whistle_attention_message",
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
            str(ROOT / "tests/chaos/next_use_unix_restore_diagnostics.c"),
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
        library = cls.artifacts / "author.so"
        validator_command = [
            "/usr/bin/cc",
            "-shared",
            "-fPIC",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wno-misleading-indentation",
            "-std=c99",
            "-Wl,-z,defs",
            "-I" + str(ROOT / "include"),
            str(ROOT / "src/chaos_next_use.c"),
            str(ROOT / "src/chaos_lua.c"),
            str(ROOT / "tests/chaos/next_use_author_native.c"),
            *subprocess.check_output(
                ["/usr/bin/pkg-config", "--cflags", "--libs", "lua5.4"], text=True
            ).split(),
            "-lm",
            "-o",
            str(library),
        ]
        commands.append(validator_command)
        subprocess.run(validator_command, check=True, capture_output=True, timeout=30)
        cls.validator = author.NativeAuthorValidator(library)
        (cls.artifacts / "build-commands.json").write_text(
            json.dumps(commands, indent=2)
        )
        (cls.artifacts / "compiled-inputs.json").write_text(
            json.dumps(hashes, indent=2)
        )
        for name in (
            "next_use_unix_game.c",
            "next_use_unix_restore_diagnostics.c",
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

    @unittest.skipIf(os.geteuid() == 0, "0400 permission denial requires non-root")
    def test_complete_readonly_journal_restore_remains_acknowledged(self):
        self._two_family_order("WF", readonly_complete=True)

    def test_resume_rejects_damaged_prefix_without_changing_gameplay(self):
        for damage in ("tamper", "truncated", "extra", "missing", "rehashed"):
            with self.subTest(damage=damage):
                self._two_family_order("WF", journal_damage=damage)

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

    def test_active_wrong_level_restore_rejected_before_healthy_continuation(self):
        self._two_family_order("WF", boundary="wrong-level")

    def test_armed_restore_missing_target_does_not_rebind(self):
        self._two_family_order("WF", boundary="armed-missing-target")

    def test_armed_restore_replacement_target_does_not_rebind(self):
        self._two_family_order("WF", boundary="armed-replacement-target")

    def test_corrupt_admitted_save_preserved_before_healthy_continuation(self):
        self._two_family_order("WF", boundary="corrupt-save")

    def test_author_state_checkpoint_preserves_nonzero_state_and_quiet_f(self):
        self._two_family_order("WF", program="state")

    def test_author_witness_checkpoint_preserves_delivered_w_and_refresh_f(self):
        self._two_family_order("WF", program="witness")

    def test_author_unpublished_checkpoint_does_not_invent_witness_for_f(self):
        self._two_family_order("WF", program="witness", unpublished=True)

    def test_w_only_claimed_witness_survives_inside_window(self):
        self._two_family_order("W")

    def test_w_only_claimed_undelivered_survives_inside_window(self):
        self._two_family_order("W", unpublished=True)

    def test_drop_program_on_save_loses_remaining_native_f_effect(self):
        self._two_family_order("WF", boundary="drop-program")

    def test_new_game_reusing_old_transport_has_no_admission_authority(self):
        self._new_game_reusing_old_transport()

    def test_new_game_reusing_old_transport_stays_foreign_after_restore(self):
        self._new_game_reusing_old_transport(checkpoint=True)

    def test_new_game_reusing_old_transport_cannot_repair_missing_owner(self):
        self._new_game_reusing_old_transport(missing_owner=True, checkpoint=True)

    def _new_game_reusing_old_transport(self, *, checkpoint=False, missing_owner=False):
        """Actual new native game, same inode/clock/seed, not forged identity."""
        self._build_two_family_game()
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

        suffix = ("-checkpoint" if checkpoint else "") + (
            "-missing" if missing_owner else ""
        )

        def new_game(name):
            game = Game(
                ROOT / "dnethackdir",
                self.clock,
                wizard=True,
                asset_pool=self.asset_pool,
                executable=self.two_family_exe,
                root=self.artifacts / (name + suffix),
            )
            self.addCleanup(game.close)
            return game

        def state(game, name="state.json"):
            return json.loads((game.game / name).read_text())

        def whistle(game):
            slot = state(game, "fixture.json")["letter"]
            self.assertIn(b"apply", game.send("a").lower())
            game.more(game.send(slot))

        def fountain(game):
            self.assertIn(b"fountain", game.send("q").lower())
            game.more(game.send("y"))

        old = new_game("reuse-old")
        old.start()
        if checkpoint:
            # Both lifetimes take the same native empty-save path so their
            # later real root/notice/end references still collide exactly.
            self.assertEqual(old.save(), 0)
            old.start()
        whistle(old)
        fountain(old)
        # Real author publication from the real delivered origin history. Never
        # patch its ID, time, origins, source or receipt for the fresh game.
        source = fixture_sources()[1]
        authored = author.author_offline(
            old.run,
            transport=author.FakeAuthorTransport(response(source)),
            validator=self.validator,
        )
        self.assertEqual(authored["status"], "envelope_published_not_admitted")
        envelope = old.run / "next_use-envelope.json"
        encoded = envelope.read_bytes()
        payload = json.loads(encoded)
        old.sanity(60)
        self.assertEqual(state(old)["spent"], 2)
        self.assertEqual(state(old)["valid"], 1)
        old_identity = state(old, "identity.json")
        self.assertGreater(old_identity["game_token"], 0)
        self.assertEqual(old.save(), 0)
        self.assertTrue(list((old.game / "save").iterdir()))
        # Retain old native save and all evidence in place; second Game has an
        # empty save directory, so main must create another logical lifetime.
        protected = {p.name: p.read_bytes() for p in old.run.iterdir() if p.is_file()}
        (old.root / "transport-baseline.json").write_text(
            json.dumps(
                {
                    name: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                    for name, raw in protected.items()
                },
                indent=2,
            )
        )
        history = protected["events.jsonl"]
        receipt = protected["next_use-receipt.jsonl"]
        self.assertEqual(len(receipt.splitlines()), 1)
        owner = old.run / "next_use-owner"
        self.assertEqual(owner.read_text(), f"NUO1:{old_identity['game_token']:016x}\n")
        if missing_owner:
            # Remove only the transport binding; preserve its original bytes
            # outside the mailbox, and keep candidate/receipt/history untouched.
            (old.root / "removed-next_use-owner").write_bytes(owner.read_bytes())
            owner.unlink()
        transport = (old.run.stat().st_dev, old.run.stat().st_ino)
        fresh = new_game("reuse-new")
        self.assertFalse(list((fresh.game / "save").iterdir()))
        fresh.run = old.run
        fresh.start()
        fresh_identity = state(fresh, "identity.json")
        self.assertEqual(fresh_identity["birthday"], old_identity["birthday"])
        self.assertNotEqual(fresh_identity["game_token"], old_identity["game_token"])
        self.assertGreater(fresh_identity["game_token"], 0)
        self.assertEqual(state(fresh, "fixture.json"), state(old, "fixture.json"))
        if checkpoint:
            self.assertEqual(fresh.save(), 0)
            saves = list((fresh.game / "save").iterdir())
            self.assertTrue(saves)
            for save in saves:
                shutil.copy2(save, fresh.root / ("saved-" + save.name))
            fresh.start()
            self.assertEqual(state(fresh, "identity.json"), fresh_identity)
        whistle(fresh)
        fountain(fresh)
        # Deliberately prove the dangerous collision: actual new observations
        # repeat every candidate reference, including root/notice/end and move.
        new_events = [
            json.loads(row)
            for row in (fresh.run / "events.jsonl")
            .read_bytes()[len(history) :]
            .splitlines()
        ]
        self.assertEqual(
            [e["detail"] for e in new_events if e["event"] == "session"],
            ["new", "restore"] if checkpoint else ["new"],
        )
        for ref in payload["origin_refs"]:
            operation = "whistling" if ref["family"] == "W" else "fountain_drink"
            for stage, seq in (
                ("started", ref["root"]),
                ("notice", ref["notice_seq"]),
                ("completed", ref["end_seq"]),
            ):
                matching = [e for e in new_events if e["seq"] == seq]
                self.assertEqual(len(matching), 1)
                event = matching[0]
                self.assertEqual(event["turn"], ref["move"])
                self.assertEqual(event["observation"]["operation"], operation)
                self.assertEqual(event["observation"]["stage"], stage)
                self.assertEqual(
                    event["observation"]["root_seq"],
                    0 if stage == "started" else ref["root"],
                )
                if stage == "notice":
                    self.assertEqual(
                        event["observation"]["fact"],
                        "sound_high" if ref["family"] == "W" else ref["fact"],
                    )
            self.assertEqual(ref["run"], engine_run_hex(fresh.run))
            self.assertEqual(
                (ref["level_dnum"], ref["level_dlevel"]),
                (state(fresh)["dnum"], state(fresh)["dlevel"]),
            )
        self.assertEqual(state(fresh)["safe"] + 1, payload["at"])
        fresh.sanity(60)
        at_safe = state(fresh)
        # Continue far enough to expose both effects if stale admission occurs.
        whistle(fresh)
        fresh.wait_turns(7)
        fountain(fresh)
        final = state(fresh)
        trace = [
            json.loads(row)
            for row in (fresh.game / "native.jsonl").read_text().splitlines()
        ]
        evidence = dict(
            old_identity=old_identity,
            new_identity=fresh_identity,
            transport=transport,
            at_safe=at_safe,
            final=final,
            native_trace=trace,
            candidate=payload,
        )
        (fresh.root / "reuse-evidence.json").write_text(json.dumps(evidence, indent=2))
        self.assertEqual(fresh.quit(), 0)
        self.assertEqual(transport, (fresh.run.stat().st_dev, fresh.run.stat().st_ino))
        self.assertEqual(envelope.read_bytes(), encoded)
        self.assertTrue((fresh.run / "events.jsonl").read_bytes().startswith(history))
        # These are admission/effect assertions, not rejection by changed refs.
        self.assertEqual(at_safe["spent"], 0, evidence)
        self.assertEqual(at_safe["valid"], 0)
        self.assertEqual(final["callback_ordinal"], 0)
        self.assertNotIn(b"The next whistle", fresh.raw)
        self.assertFalse([r for r in trace if r["kind"] == "witness"])
        self.assertEqual(
            [r["outcome"] for r in trace if r["kind"] == "fountain"], [1, 1]
        )
        for name, raw in protected.items():
            if name in ("events.jsonl", "next_use-schedule.jsonl"):
                # Native observation/schedule history may append, never reset.
                self.assertTrue((fresh.run / name).read_bytes().startswith(raw), name)
            elif name == "next_use-owner" and missing_owner:
                self.assertFalse(owner.exists())
                self.assertEqual(
                    (old.root / "removed-next_use-owner").read_bytes(), raw
                )
            else:
                self.assertEqual((fresh.run / name).read_bytes(), raw, name)

    def _two_family_order(
        self,
        order,
        *,
        boundary="unchanged",
        program=None,
        unpublished=False,
        journal_damage=None,
        readonly_complete=False,
    ):
        """Controlled wizard geometry/RNG; NOT ordinary play or #66 evidence."""
        self.assertIn(
            boundary,
            (
                "unchanged",
                "deleted-candidate",
                "replaced-candidate",
                "relocated-transport",
                "armed-whistle",
                "corrupt-save",
                "drop-program",
                "wrong-level",
                "armed-missing-target",
                "armed-replacement-target",
            ),
        )
        target_fault = boundary in ("armed-missing-target", "armed-replacement-target")
        w_only = order == "W"
        mutant = boundary == "drop-program"
        armed_checkpoint = (
            boundary == "armed-whistle" or target_fault or boundary == "wrong-level"
        )
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
        if program is not None:
            self.assertIn(program, ("state", "witness"))
            self.assertEqual((order, boundary), ("WF", "unchanged"))
            source = fixture_sources()[0 if program == "state" else 1].decode("ascii")
        if unpublished and not w_only:
            self.assertEqual(program, "witness")
        refresh = program is None or (program == "witness" and not unpublished)
        sha = hashlib.sha256(source.encode("ascii")).hexdigest()
        results = []
        self._build_two_family_game()
        for interrupted in (False, True):
            game = Game(
                ROOT / "dnethackdir",
                self.clock,
                wizard=True,
                asset_pool=self.asset_pool,
                executable=self.two_family_exe,
                root=self.artifacts
                / (
                    order
                    + "-"
                    + boundary
                    + ("-" + program if program else "")
                    + ("-" + journal_damage if journal_damage else "")
                    + ("-readonly-complete" if readonly_complete else "")
                    + ("-unpublished" if unpublished else "")
                    + ("-restore" if interrupted else "-continuous")
                ),
            )
            self.addCleanup(game.close)
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
            if not w_only:
                fountain()
            origins = []
            for family, operation, fact in (
                ("W", "whistling", "ordinary_whistle"),
                ("F", "fountain_drink", "water_refreshed"),
            ):
                if w_only and family == "F":
                    continue
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
            author_evidence = {}
            if w_only:
                origin = origins[0]
                publish_envelope(
                    game.run,
                    dict(
                        family="W",
                        op="whistle_attention",
                        origin=dict(
                            root_seq=origin["root"],
                            notice_seq=origin["notice_seq"],
                            end_seq=origin["end_seq"],
                            fact="sound_high",
                        ),
                    ),
                    dict(
                        at=state()["safe"] + 1,
                        id=1,
                        variant=0,
                        level_dnum=origin["level_dnum"],
                        level_dlevel=origin["level_dlevel"],
                        move=origin["move"],
                        run=origin["run"],
                    ),
                )
                encoded = envelope.read_bytes()
                payload = json.loads(encoded)
                self.assertEqual(payload["operations"], ["W"])
                source = payload["source"]
                sha = payload["source_sha256"]
            elif program is None:
                envelope.write_bytes(encoded)
                envelope.chmod(0o600)
            else:
                # Real engine-origin history and schedule, not synthetic rows.
                # The author owns capabilities and timing. Never patch its output.
                transport = author.FakeAuthorTransport(response(source.encode("ascii")))
                authored = author.author_offline(
                    game.run, transport=transport, validator=self.validator
                )
                self.assertEqual(len(transport.calls), 1)
                self.assertEqual(authored["validation"], "native_parser_and_load")
                self.assertEqual(authored["status"], "envelope_published_not_admitted")
                self.assertEqual(authored["source_sha256"], sha)
                encoded = envelope.read_bytes()
                # Compare independently derived native origins, not retimed ones.
                self.assertEqual(json.loads(encoded), payload)
                self.assertEqual(
                    authored["envelope_sha256"], hashlib.sha256(encoded).hexdigest()
                )
                self.assertEqual(
                    (game.run / "next_use-author-response.json").read_bytes(),
                    transport.response,
                )
                author_evidence = {
                    path.name: path.read_bytes()
                    for path in game.run.glob("next_use-author-*.json")
                }

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
            self.assertEqual(
                admitted["spent"], spent_before + (1 if w_only else 2), admitted
            )
            self.assertEqual(
                (admitted["slot_w"], admitted["slot_f"]), (1, 0) if w_only else (1, 1)
            )
            self.assertEqual(admitted["source_sha256"], sha)
            receipt = (game.run / "next_use-receipt.jsonl").read_bytes()
            admissions = [json.loads(line) for line in receipt.splitlines()]
            self.assertEqual(len(admissions), 1)
            self.assertEqual(admissions[0]["kind"], 2)  # native admission receipt

            def await_attention():
                # Fixed bound: witness at A+5, finish inside (not exactly
                # on) A+10. Never re-whistle to resume an armed saved target.
                game.wait_turns(7)
                self.assertEqual(state()["witnessed"], int(not unpublished), state())
                self.assertEqual(state()["attention_claimed"], 1)

            def effect(family):
                if family == "W":
                    whistle()
                    await_attention()
                else:
                    fountain()
                    self.assertEqual(state()["slot_f"], 2 if refresh else 4, state())

            if unpublished:
                # Only the eligible native W decision's presentation route is denied.
                (game.game / "deny-w-message").touch()
            if armed_checkpoint:
                whistle()
            else:
                effect(order[0])
            checkpoint = state()
            self.assertEqual(checkpoint["valid"], 1)
            if w_only:
                self.assertEqual(checkpoint["slot_w"], 2)
                self.assertEqual(checkpoint["w_runtime"], 1)
                self.assertEqual(checkpoint["callback_ordinal"], 1)
                self.assertEqual(checkpoint["callback_w"], 1)
                self.assertEqual(checkpoint["attempted"], 1)
                self.assertEqual(
                    len([r for r in native_trace() if r["kind"] == "witness"]), 1
                )
                self.assertEqual(checkpoint["slot_f"], 0)  # UNDECLARED, not pending
                self.assertEqual(checkpoint["callback_f"], 0)
                self.assertEqual(checkpoint["attention_claimed"], 1)
                self.assertEqual(checkpoint["witnessed"], int(not unpublished))
                self.assertEqual(checkpoint["armed_m_id"], fixture["pet_id"])
                self.assertGreaterEqual(
                    checkpoint["monstermoves"],
                    checkpoint["activation_monstermoves"] + 5,
                )
                self.assertLess(
                    checkpoint["monstermoves"],
                    checkpoint["activation_monstermoves"] + 10,
                )
            if program:
                self.assertEqual(checkpoint["state"], int(program == "state"))
                self.assertEqual(checkpoint["witnessed"], int(not unpublished))
                self.assertEqual(checkpoint["attention_claimed"], 1)
                self.assertEqual(checkpoint["callback_ordinal"], 1)
                self.assertEqual(checkpoint["callback_w"], 1)
                self.assertEqual(checkpoint["callback_f"], 0)
                self.assertEqual(checkpoint["slot_f"], 1)
                # Production safe_try currently installs zero count inputs;
                # they are NOT observed-event totals. Preserve the real values
                # without claiming nonzero/count-sensitive production coverage.
                self.assertEqual(checkpoint["whistle_count"], 0)
                self.assertEqual(checkpoint["fountain_count"], 0)
                self.assertLess(
                    checkpoint["monstermoves"],
                    checkpoint["activation_monstermoves"] + 10,
                )
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
            prefix = (game.run / "next_use-journal.jsonl").read_bytes()
            damaged = None
            if interrupted:
                if mutant:
                    (game.game / "drop-program-on-save").touch()
                self.assertEqual(game.save(), 0)
                if mutant:
                    # Never re-enable the seam for restore-time insurance writes.
                    (game.game / "drop-program-on-save").unlink()
                saves = list((game.game / "save").iterdir())
                self.assertTrue(saves)
                for save in saves:
                    retained = game.root / ("saved-" + save.name)
                    shutil.copy2(save, retained)
                    retained.chmod(0o400)
                    if w_only:
                        self.assertEqual(
                            retained.read_bytes().count(source.encode("ascii")), 1
                        )
                if boundary == "wrong-level":
                    self._reject_wrong_level(game, saves, checkpoint)
                if target_fault:
                    # Fault is AFTER world restore, BEFORE chaos_start/observe;
                    # the serialized world still contains the original pet.
                    (game.game / boundary).touch()
                if boundary == "corrupt-save":
                    # Disposable current uncompressed native save, with a used W
                    # and pending F. Preserve the readonly original as evidence.
                    self.assertEqual(len(saves), 1)
                    save = saves[0]
                    original = save.read_bytes()
                    source_bytes = source.encode("ascii")
                    self.assertEqual(original.count(source_bytes), 1)
                    source_at = original.index(source_bytes)
                    self.assertEqual(original.count(b"NUS1"), 1)
                    marker = original.index(b"NUS1")
                    word = struct.calcsize("i")
                    self.assertEqual(
                        original[marker + 4 : marker + 4 + word], struct.pack("i", 1)
                    )
                    version_at = marker + 4 + word
                    self.assertEqual(
                        original[version_at : version_at + word], struct.pack("i", 5)
                    )
                    changed_source = bytearray(original)
                    changed_source[source_at] ^= 1
                    incompatible = bytearray(original)
                    incompatible[version_at : version_at + word] = struct.pack("i", 3)
                    # Alter the independently saved player identity BEFORE the
                    # next-use extension, leaving its self-consistent binding
                    # and source intact. This tests the trusted native binding,
                    # not merely the snapshot's internal digest checker.
                    logical = struct.pack("l", checkpoint["run_token"])
                    self.assertEqual(original[:marker].count(logical), 1)
                    logical_at = original[:marker].index(logical)
                    wrong_game = bytearray(original)
                    replacement_identity = checkpoint["run_token"] ^ 1
                    if replacement_identity == 0:
                        replacement_identity = 2
                    wrong_game[logical_at : logical_at + len(logical)] = struct.pack(
                        "l", replacement_identity
                    )
                    faults = {
                        "source-digest": bytes(changed_source),
                        "short-source": original[: source_at + len(source_bytes) // 2],
                        "unsupported-version": bytes(incompatible),
                        "independent-game-identity": bytes(wrong_game),
                    }
                    protected_paths = [
                        game.run / "events.jsonl",
                        game.run / "next_use-receipt.jsonl",
                        game.game / "native.jsonl",
                        game.game / "state.json",
                    ]
                    protected = {p: p.read_bytes() for p in protected_paths}
                    for fault, damaged in faults.items():
                        with self.subTest(save_fault=fault):
                            save.write_bytes(damaged)
                            retained_fault = game.root / (fault + ".save")
                            retained_fault.write_bytes(damaged)
                            retained_fault.chmod(0o400)
                            raw_begin = len(game.raw)
                            text = game.start()
                            self.assertEqual(game.finish(text), 1)
                            self.assertIn(b"save file preserved", game.raw[raw_begin:])
                            self.assertEqual(save.read_bytes(), damaged)
                            for path, raw in protected.items():
                                self.assertEqual(path.read_bytes(), raw, str(path))
                            self.assertFalse(
                                list(game.game.glob(f"{os.getuid()}wizard.*"))
                            )
                    # Only the disposable active input is restored. The corrupt
                    # and pristine evidence files remain byte-identical.
                    save.write_bytes(original)
                    self.assertEqual(
                        (game.root / ("saved-" + save.name)).read_bytes(), original
                    )
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
                if journal_damage:
                    journal_path = game.run / "next_use-journal.jsonl"
                    damaged = prefix
                    if journal_damage == "tamper":
                        damaged = prefix.replace(
                            b'"snapshot_v":5', b'"snapshot_v":4', 1
                        )
                    elif journal_damage == "truncated":
                        damaged = prefix[:-1]
                    elif journal_damage == "extra":
                        damaged = prefix + b"\n"
                    elif journal_damage == "rehashed":
                        rows = [json.loads(line) for line in prefix.splitlines()]
                        rows[0]["payload"]["data"]["snapshot"]["state"] = 1
                        previous = "0" * 64
                        rebuilt = []
                        for row in rows:
                            row["payload"]["prev"] = previous
                            payload_bytes = json.dumps(
                                row["payload"], separators=(",", ":")
                            ).encode()
                            previous = hashlib.sha256(payload_bytes).hexdigest()
                            rebuilt.append(
                                b'{"payload":'
                                + payload_bytes
                                + b',"sha256":"'
                                + previous.encode()
                                + b'"}\n'
                            )
                        damaged = b"".join(rebuilt)
                        self.assertEqual(len(damaged), len(prefix))
                    if journal_damage == "missing":
                        journal_path.unlink()
                    else:
                        journal_path.write_bytes(damaged)
                    (game.root / "damaged-prefix.bin").write_bytes(damaged)
                game.start()
                restored = state()
                if journal_damage:
                    self.assertEqual(restored["journal_state"], 3)
                    for key in ("journal_bytes", "journal_sha256", "replay_cursor"):
                        self.assertEqual(restored[key], checkpoint[key], key)
                    self.assertEqual(
                        json.loads((game.game / "capture.json").read_text())[
                            "incomplete"
                        ],
                        1,
                    )
                if mutant:
                    self._lost_program_control(
                        game,
                        checkpoint,
                        restored,
                        fountain,
                        whistle,
                        state,
                        native_trace,
                        receipt,
                    )
                    continue
                self.assertEqual(restored["valid"], 1)
                (game.root / "restored.json").write_text(json.dumps(restored, indent=2))
                # Read-only exported fields, never imported/assigned by the test.
                for key in (
                    "attempted",
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
                    "whistle_count",
                    "fountain_count",
                    "callback_w",
                    "callback_f",
                    "next_seq",
                    "admission_move",
                    "variant",
                    "delay_used",
                    "delay_until",
                    "last_root",
                    "binding_sha256",
                    "snapshot_v",
                    "program_id",
                    "phase",
                    "origin_w_live",
                    "origin_f_live",
                    "identity_unsafe",
                    "termination_emitted",
                    "source_length",
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
            if target_fault and interrupted:
                self._missing_target_continuation(
                    game,
                    checkpoint,
                    state,
                    native_trace,
                    whistle,
                    fountain,
                    receipt,
                    encoded,
                    boundary,
                )
                continue
            if w_only:
                results.append(
                    self._claimed_w_continuation(
                        game,
                        checkpoint,
                        state,
                        native_trace,
                        whistle,
                        receipt,
                        encoded,
                        sha,
                        unpublished,
                        fixture,
                    )
                )
                # W-only has no F callback to finish the recorder: its native
                # window ending must complete the resumed journal itself.
                journal_path = game.run / "next_use-journal.jsonl"
                raw = journal_path.read_bytes()
                self.assertTrue(raw.startswith(prefix))
                capture = json.loads((game.game / "capture.json").read_text())
                self.assertEqual(
                    read_journal(journal_path, capture_status=capture)["status"],
                    "acknowledged_complete",
                )
                self.assertEqual(state()["journal_state"], 2)
                rows = [json.loads(line)["payload"] for line in raw.splitlines()]
                self.assertEqual(sum(r["kind"] == "header" for r in rows), 1)
                self.assertEqual(sum(r["kind"] == "end" for r in rows), 1)
                first = json.loads(raw[len(prefix) :].splitlines()[0])["payload"]
                self.assertEqual(first["cursor"], checkpoint["replay_cursor"] + 1)
                self.assertEqual(game.quit(), 0)
                continue
            if armed_checkpoint:
                await_attention()
            effect(order[1])
            complete = state()
            self.assertEqual(complete["callback_ordinal"], 2)
            if program:
                self.assertEqual(complete["state"], int(program == "state" or refresh))
                self.assertEqual(
                    (complete["callback_w"], complete["callback_f"]), (1, 1)
                )
            (game.root / "complete.json").write_text(json.dumps(complete, indent=2))
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
            for name, raw in author_evidence.items():
                self.assertEqual((game.run / name).read_bytes(), raw, name)
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
            if not mutant and not (interrupted and journal_damage):
                journal_path = game.run / "next_use-journal.jsonl"
                raw = journal_path.read_bytes()
                self.assertTrue(raw.startswith(prefix))
                capture = json.loads((game.game / "capture.json").read_text())
                journal_result = read_journal(journal_path, capture_status=capture)
                self.assertEqual(journal_result["status"], "acknowledged_complete")
                self.assertEqual(final["journal_state"], 2)
                rows = [json.loads(line)["payload"] for line in raw.splitlines()]
                self.assertEqual(sum(r["kind"] == "header" for r in rows), 1)
                self.assertEqual(sum(r["kind"] == "end" for r in rows), 1)
                first = json.loads(raw[len(prefix) :].splitlines()[0])["payload"]
                self.assertEqual(first["cursor"], checkpoint["replay_cursor"] + 1)
                if interrupted:
                    # A COMPLETE checkpoint validates but never appends/resurrects.
                    self.assertEqual(game.save(), 0)
                    if readonly_complete:
                        journal_path.chmod(0o400)
                        st = journal_path.stat()
                        self.assertEqual(st.st_mode & 0o777, 0o400)
                        self.assertEqual(st.st_uid, os.getuid())
                        self.assertEqual(st.st_nlink, 1)
                        self.assertEqual(journal_path.read_bytes(), raw)
                        with self.assertRaises(PermissionError):
                            with journal_path.open("r+b"):
                                pass
                        print(
                            f"COMPLETE_READONLY uid={os.getuid()} "
                            f"euid={os.geteuid()} mode=0400 nlink=1 "
                            f"read=ok write=denied path={journal_path}",
                            flush=True,
                        )
                    terminal_trace = native_trace()
                    game.start()
                    terminal_state = state()
                    terminal_capture = json.loads(
                        (game.game / "capture.json").read_text()
                    )
                    (game.root / "terminal-restored.json").write_text(
                        json.dumps(terminal_state, indent=2)
                    )
                    self.assertEqual(journal_path.read_bytes(), raw)
                    self.assertEqual(native_trace(), terminal_trace)
                    for key in (
                        "journal_bytes",
                        "journal_sha256",
                        "replay_cursor",
                        "slot_w",
                        "slot_f",
                        "witnessed",
                        "attention_claimed",
                        "callback_ordinal",
                        "spent",
                        "source_sha256",
                    ):
                        self.assertEqual(terminal_state[key], final[key], key)
                    self.assertEqual(
                        read_journal(journal_path, capture_status=terminal_capture)[
                            "status"
                        ],
                        "acknowledged_complete",
                    )
                    self.assertEqual(terminal_state["journal_state"], 2)
            if interrupted and journal_damage:
                journal_path = game.run / "next_use-journal.jsonl"
                self.assertEqual(final["replay_cursor"], checkpoint["replay_cursor"])
                self.assertEqual(game.save(), 0)
                game.start()
                self.assertEqual(state()["journal_state"], 3)
                for key in ("journal_bytes", "journal_sha256", "replay_cursor"):
                    self.assertEqual(state()[key], checkpoint[key], key)
                self.assertEqual(
                    json.loads((game.game / "capture.json").read_text())["incomplete"],
                    1,
                )
                if journal_damage == "missing":
                    self.assertFalse(journal_path.exists())
                else:
                    self.assertEqual(journal_path.read_bytes(), damaged)
            trace = native_trace()
            witnesses = [r for r in trace if r["kind"] == "witness" and r["delivered"]]
            attempts = [r for r in trace if r["kind"] == "witness"]
            self.assertEqual(len(attempts), 1, trace)
            self.assertEqual(len(witnesses), int(not unpublished), trace)
            self.assertEqual(attempts[0]["displaced"], 1)
            self.assertEqual(attempts[0]["classifier"], 1)
            self.assertEqual(attempts[0]["pet_id"], fixture["pet_id"])
            attention = [
                e["observation"]
                for e in game.events()
                if e.get("observation", {}).get("operation") == "whistle_attention"
            ]
            self.assertEqual(len(attention), 2 if unpublished else 3)
            if unpublished:
                self.assertEqual(
                    [e["stage"] for e in attention], ["started", "blocked"]
                )
            else:
                self.assertEqual(
                    [e["stage"] for e in attention], ["started", "notice", "completed"]
                )
                self.assertEqual(attention[1]["fact"], "attention")
            refresh_notices = [
                e
                for e in game.events()
                if e.get("observation", {}).get("fact") == "water_refreshed"
            ]
            self.assertEqual(len(refresh_notices), 2 if refresh else 1)

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
            self._assert_fountain_continuation(drinks, refresh)
            self.assertEqual(
                [drink["hunger_delta"] for drink in drinks], [4, 4 if refresh else 0, 0]
            )
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
                checkpoint_context={
                    k: checkpoint[k]
                    for k in (
                        "state",
                        "whistle_count",
                        "fountain_count",
                        "callback_w",
                        "callback_f",
                        "callback_ordinal",
                        "witnessed",
                        "variant",
                        "admission_move",
                        "moves",
                        "monstermoves",
                    )
                },
                complete_context={
                    k: complete[k]
                    for k in (
                        "state",
                        "whistle_count",
                        "fountain_count",
                        "callback_w",
                        "callback_f",
                        "callback_ordinal",
                        "witnessed",
                        "variant",
                        "admission_move",
                        "moves",
                        "monstermoves",
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
        if not mutant and not target_fault:
            self.assertEqual(results[0], results[1])

    def _reject_wrong_level(self, game, saves, checkpoint):
        self.assertEqual(len(saves), 1)
        save = saves[0]
        original = save.read_bytes()
        # sizeof/offsetof and member widths from this exact compiled fixture.
        probe = subprocess.run(
            [str(self.two_family_exe), "--native-save-layout"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(
            probe.returncode, 0, "missing native layout diagnostic: " + probe.stderr
        )
        (game.root / "native-save-layout.json").write_text(probe.stdout)
        self.assertTrue(
            probe.stdout.startswith("{"), "missing native layout diagnostic"
        )
        layout = json.loads(probe.stdout)
        self.assertEqual(layout["compressed"], 0)
        self.assertEqual(layout["dlevel_size"], struct.calcsize("i"))
        self.assertEqual(original.count(b"NUS1"), 1)
        marker = original.index(b"NUS1")
        player_at = marker - layout["you_size"]
        level_at = player_at + layout["dlevel_offset"]
        width = layout["dlevel_size"]
        self.assertGreater(player_at, 0)
        self.assertEqual(
            original[level_at : level_at + width],
            struct.pack("i", checkpoint["dlevel"]),
        )
        changed = bytearray(original)
        changed[level_at : level_at + width] = struct.pack(
            "i", checkpoint["dlevel"] + 1
        )
        damaged = bytes(changed)
        self.assertNotEqual(damaged, original)
        self.assertEqual(damaged[:level_at], original[:level_at])
        self.assertEqual(damaged[level_at + width :], original[level_at + width :])
        self.assertEqual(damaged[marker:], original[marker:])
        retained = game.root / "independent-level-identity.save"
        retained.write_bytes(damaged)
        retained.chmod(0o400)
        protected = {
            path: path.read_bytes()
            for path in (
                game.run / "events.jsonl",
                game.run / "next_use-receipt.jsonl",
                game.run / "next_use-journal.jsonl",
                game.game / "native.jsonl",
                game.game / "state.json",
            )
        }
        save.write_bytes(damaged)
        (game.game / "diagnose-restore-bound").touch()
        raw_begin = len(game.raw)
        text = game.start()
        self.assertEqual(game.finish(text), 1)
        rejected_output = game.raw[raw_begin:]
        self.assertIn(b"save file preserved", rejected_output)
        self.assertNotIn(b"The next whistle", rejected_output)
        diag = json.loads((game.game / "restore-bound.json").read_text())
        self.assertEqual(diag["snapshot_valid"], 1)
        self.assertEqual(diag["result"], 0)
        self.assertEqual(diag["published"], 0)
        for key in ("run_token", "level_token", "armed_m_id", "phase"):
            self.assertEqual(diag[key], checkpoint[key], key)
        self.assertEqual(diag["trusted_run"], checkpoint["run_token"])
        self.assertNotEqual(diag["trusted_level"], checkpoint["level_token"])
        self.assertEqual(diag["trusted_dlevel"], checkpoint["dlevel"] + 1)
        self.assertEqual(diag["phase"], 3)  # COMMITTED, not terminal departure
        for path, raw in protected.items():
            self.assertEqual(path.read_bytes(), raw, str(path))
        self.assertEqual(save.read_bytes(), damaged)
        self.assertEqual(retained.read_bytes(), damaged)
        self.assertEqual((game.root / ("saved-" + save.name)).read_bytes(), original)
        self.assertFalse(list(game.game.glob(f"{os.getuid()}wizard.*")))
        (game.root / "wrong-level-evidence.json").write_text(
            json.dumps(
                dict(
                    player_at=player_at,
                    level_at=level_at,
                    width=width,
                    marker=marker,
                    original_sha256=hashlib.sha256(original).hexdigest(),
                    damaged_sha256=hashlib.sha256(damaged).hexdigest(),
                    extension_sha256=hashlib.sha256(original[marker:]).hexdigest(),
                    rejected_exit=game.exitcode,
                    diagnostic=diag,
                ),
                indent=2,
            )
        )
        (game.game / "diagnose-restore-bound").unlink()
        save.write_bytes(original)  # pristine continuation uses unchanged oracles

    def _missing_target_continuation(
        self,
        game,
        checkpoint,
        state,
        native_trace,
        whistle,
        fountain,
        receipt,
        encoded,
        boundary,
    ):
        diagnostic = game.game / "restore-target.json"
        self.assertTrue(
            diagnostic.exists(), "missing post-world-restore target fault seam"
        )
        world = json.loads(diagnostic.read_text())
        self.assertEqual(world["boundary"], "after-world-restore-before-chaos-start")
        self.assertEqual(world["captured_id"], checkpoint["armed_m_id"])
        self.assertEqual(world["before_ids"], [checkpoint["armed_m_id"]])
        self.assertNotIn(checkpoint["armed_m_id"], world["after_ids"])
        replacement = boundary == "armed-replacement-target"
        self.assertEqual(len(world["after_ids"]), int(replacement))
        self.assertEqual(world["eligible_replacement"], int(replacement))
        self.assertEqual(world["runtime_unchanged"], 1)
        self.assertEqual(world["moves"], checkpoint["moves"])
        self.assertEqual(world["monstermoves"], checkpoint["monstermoves"])
        self.assertEqual(world["spent"], checkpoint["spent"])
        self.assertEqual(world["game_token"], checkpoint["run_token"])
        self.assertEqual(world["level_token"], checkpoint["level_token"])
        (game.game / boundary).unlink()  # exactly one restore-world fault
        deadline = checkpoint["activation_monstermoves"] + 10
        samples = []
        while state()["monstermoves"] <= deadline:
            current = state()
            self.assertEqual(current["w_runtime"], 1)
            for key in (
                "armed_m_id",
                "activation_monstermoves",
                "witnessed",
                "attention_claimed",
                "callback_ordinal",
                "callback_w",
                "callback_f",
                "slot_w",
                "slot_f",
                "source_sha256",
                "binding_sha256",
                "run_token",
                "level_token",
                "spent",
            ):
                self.assertEqual(current[key], checkpoint[key], key)
            samples.append(current)
            game.wait_turns(1)
        ended = state()
        self.assertEqual(ended["w_runtime"], 2)
        self.assertEqual(ended["monstermoves"], deadline + 1)
        self.assertEqual(
            json.loads((game.game / "window-ended.json").read_text()),
            dict(
                monstermoves=deadline,
                activation_monstermoves=deadline - 10,
            ),
        )
        self.assertEqual(ended["slot_f"], 1)
        # Exact wf-families source refreshes F unconditionally: target loss must
        # not consume its pending slot or make it dependent on a fake witness.
        fountain()
        complete = state()
        self.assertEqual((complete["slot_w"], complete["slot_f"]), (2, 2))
        self.assertEqual((complete["callback_w"], complete["callback_f"]), (1, 1))
        self.assertEqual(complete["callback_ordinal"], 2)
        game.sanity(40)
        whistle()
        game.wait_turns(10)
        fountain()
        final = state()
        for key in (
            "slot_w",
            "slot_f",
            "callback_ordinal",
            "spent",
            "armed_m_id",
            "activation_monstermoves",
            "source_sha256",
            "binding_sha256",
        ):
            self.assertEqual(final[key], complete[key], key)
        self.assertEqual(final["spent"], checkpoint["spent"])
        self.assertEqual((final["witnessed"], final["attention_claimed"]), (0, 0))
        self.assertFalse([r for r in native_trace() if r["kind"] == "witness"])
        self.assertFalse(
            [
                e
                for e in game.events()
                if e.get("observation", {}).get("operation") == "whistle_attention"
            ]
        )
        self.assertNotIn(b"echo sharpens", game.raw)
        drinks = [r for r in native_trace() if r["kind"] == "fountain"]
        self._assert_fountain_continuation(drinks, True)
        self.assertEqual([r["hunger_delta"] for r in drinks], [4, 4, 0])
        self.assertEqual((game.run / "next_use-receipt.jsonl").read_bytes(), receipt)
        self.assertEqual((game.run / "next_use-envelope.json").read_bytes(), encoded)
        capture = json.loads((game.game / "capture.json").read_text())
        self.assertEqual(
            read_journal(
                game.run / "next_use-journal.jsonl",
                capture_status=capture,
            )["status"],
            "acknowledged_complete",
        )
        self.assertEqual(game.quit(), 0)
        (game.root / "target-negative-evidence.json").write_text(
            json.dumps(
                dict(
                    world=world,
                    samples=samples,
                    ended=ended,
                    complete=complete,
                    final=final,
                    native_trace=native_trace(),
                    exitcode=game.exitcode,
                ),
                indent=2,
            )
        )

    def _assert_fountain_continuation(self, drinks, refresh):
        self.assertEqual(
            [drink["outcome"] for drink in drinks],
            [1, 6 if refresh else 4, 4],
            "remaining native F effect lost",
        )

    def _lost_program_control(
        self,
        game,
        checkpoint,
        restored,
        fountain,
        whistle,
        state,
        native_trace,
        receipt,
    ):
        # A successful native restoration is prerequisite, not the mutant oracle.
        self.assertEqual(
            sum(
                e.get("event") == "session" and e.get("detail") == "restore"
                for e in game.events()
            ),
            1,
        )
        self.assertEqual(restored["valid"], 0)
        self.assertEqual(checkpoint["slot_f"], 1)
        dropped = [r for r in native_trace() if r["kind"] == "drop-program-save"]
        self.assertEqual(
            dropped,
            [
                dict(
                    kind="drop-program-save",
                    serializer_result=1,
                    spent=checkpoint["spent"],
                    attempted=1,
                )
            ],
        )
        self.assertNotEqual(restored["source_sha256"], checkpoint["source_sha256"])
        for key in ("moves", "monstermoves", "safe", "spent", "attempted"):
            self.assertEqual(restored[key], checkpoint[key], key)
        self.assertEqual(restored["attempted"], 1)
        (game.root / "restored.json").write_text(json.dumps(restored, indent=2))
        fountain()
        game.sanity(40)
        whistle()
        game.wait_turns(10)
        fountain()
        drinks = [r for r in native_trace() if r["kind"] == "fountain"]
        self.assertEqual(len(drinks), 3)
        self.assertEqual([r["hunger_delta"] for r in drinks], [4, 0, 0])
        self.assertEqual([r["outcome"] for r in drinks], [1, 4, 4])
        with self.assertRaisesRegex(
            AssertionError, "remaining native F effect lost"
        ) as caught:
            self._assert_fountain_continuation(drinks, True)
        self.assertEqual(state()["spent"], checkpoint["spent"])
        self.assertEqual((game.run / "next_use-receipt.jsonl").read_bytes(), receipt)
        self.assertEqual(game.quit(), 0)
        (game.root / "negative-control.json").write_text(
            json.dumps(
                dict(
                    oracle_failure=str(caught.exception),
                    drinks=drinks,
                    save_exit=0,
                    restored_session_count=1,
                    final_exit=game.exitcode,
                ),
                indent=2,
            )
        )

    def _claimed_w_continuation(
        self,
        game,
        checkpoint,
        state,
        native_trace,
        whistle,
        receipt,
        encoded,
        sha,
        unpublished,
        fixture,
    ):
        # Sample every native turn through the ORIGINAL deadline, not a restarted
        # ten-turn window. No witness/claimed fields are imported or assigned.
        deadline = checkpoint["activation_monstermoves"] + 10
        samples = []
        while state()["monstermoves"] <= deadline:
            current = state()
            # Command-boundary clock has advanced past the preceding observe.
            self.assertEqual(current["w_runtime"], 1)
            samples.append(current)
            game.wait_turns(1)
        ended = state()
        self.assertEqual(ended["w_runtime"], 2)
        self.assertEqual(ended["monstermoves"], deadline + 1)
        window_end = json.loads((game.game / "window-ended.json").read_text())
        self.assertEqual(
            window_end,
            dict(monstermoves=deadline, activation_monstermoves=deadline - 10),
        )
        game.sanity(40)
        whistle()
        game.wait_turns(10)
        final = state()
        for key in (
            "slot_w",
            "slot_f",
            "witnessed",
            "attention_claimed",
            "callback_ordinal",
            "callback_w",
            "callback_f",
            "spent",
            "source_sha256",
            "activation_monstermoves",
            "armed_m_id",
            "attempted",
        ):
            self.assertEqual(final[key], checkpoint[key], key)
        self.assertEqual(final["source_sha256"], sha)
        self.assertEqual(final["slot_f"], 0)
        self.assertEqual((game.run / "next_use-envelope.json").read_bytes(), encoded)
        self.assertEqual((game.root / "published-envelope.json").read_bytes(), encoded)
        self.assertEqual((game.run / "next_use-receipt.jsonl").read_bytes(), receipt)
        attempts = [r for r in native_trace() if r["kind"] == "witness"]
        self.assertEqual(len(attempts), 1)
        attempt = attempts[0]
        self.assertEqual(attempt["displaced"], 1)
        self.assertEqual(attempt["classifier"], 1)
        self.assertEqual(attempt["delivered"], int(not unpublished))
        self.assertEqual(attempt["pet_id"], fixture["pet_id"])
        self.assertGreaterEqual(attempt["monstermoves"], deadline - 5)
        self.assertLess(attempt["monstermoves"], deadline)
        attention = [
            e["observation"]
            for e in game.events()
            if e.get("observation", {}).get("operation") == "whistle_attention"
        ]
        self.assertEqual(
            [e["stage"] for e in attention],
            ["started", "blocked"]
            if unpublished
            else ["started", "notice", "completed"],
        )
        if not unpublished:
            self.assertEqual(attention[1]["fact"], "attention")
        summary = dict(
            samples=[
                {
                    k: s[k]
                    for k in (
                        "monstermoves",
                        "w_runtime",
                        "attention_claimed",
                        "witnessed",
                    )
                }
                for s in samples
            ],
            window_end=window_end,
            attempts=attempts,
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
                    "source_sha256",
                    "moves",
                    "monstermoves",
                )
            },
        )
        (game.root / "assertions.json").write_text(json.dumps(summary, indent=2))
        return summary

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
            asset_pool=self.asset_pool,
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
