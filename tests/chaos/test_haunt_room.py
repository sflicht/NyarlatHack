"""#190: the real haunt tick, trial and pick in a room built in the test.

tests/chaos/haunt_room.c is linked against the built engine objects (a
controlled copy of rnd.o, as in test_haunt_lifecycle). Nothing in the haunt
path is wrapped: the forked shadow trial is the real one. Only pline is
wrapped, because there is no terminal.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from artifact_hygiene import RetainOnFailure
from native_rng import controlled_rng_objects

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "chaos/packs/footsteps.lua"


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class HauntRoomTests(RetainOnFailure):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(
            cls.track_class_artifacts(tempfile.mkdtemp(prefix="nyarl-haunt-room-"))
        )
        print("HAUNT_ROOM_ARTIFACTS=" + str(cls.root), flush=True)
        subprocess.run(
            [
                "objcopy",
                "--redefine-sym",
                "main=original_game_main",
                str(ROOT / "sys/unix/unixmain.o"),
                str(cls.root / "unixmain.o"),
            ],
            check=True,
        )
        objects = (
            sorted((ROOT / "src").glob("*.o"))
            + [
                ROOT / "sys/unix/unixres.o",
                ROOT / "sys/unix/unixunix.o",
                cls.root / "unixmain.o",
                ROOT / "sys/share/ioctl.o",
                ROOT / "sys/share/unixtty.o",
            ]
            + sorted((ROOT / "win/tty").glob("*.o"))
            + sorted((ROOT / "win/curses").glob("*.o"))
        )
        cls.exe = cls.root / "haunt_room"
        command = [
            "cc",
            "-g",
            "-DCHAOS",
            "-I" + str(ROOT / "include"),
            str(ROOT / "tests/chaos/haunt_room.c"),
            *map(str, controlled_rng_objects(objects, cls.root)),
            "-Wl,--wrap=pline",
            "-lncursesw",
            "-ltinfo",
            "-lm",
            *subprocess.check_output(
                ["pkg-config", "--libs", "lua5.4"], text=True
            ).split(),
            "-o",
            str(cls.exe),
        ]
        (cls.root / "link.json").write_text(json.dumps(command))
        subprocess.run(command, check=True, timeout=60)

    def run_room(self, name, args, **env):
        case = self.root / name
        run = case / "run"
        (run / "diag").mkdir(parents=True)
        run.chmod(0o700)
        shutil.copy(PACK, run / "haunting.lua")
        (run / "haunting.lua").chmod(0o600)
        environ = dict(os.environ, NYARLATHACK_ECHOES="0", NYARLATHACK_RUN_DIR=str(run))
        environ.update(env)
        p = subprocess.run(
            [str(self.exe), *map(str, args)],
            cwd=run / "diag",
            env=environ,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
        )
        (case / "stdout").write_text(p.stdout)
        (case / "stderr").write_text(p.stderr)
        self.assertEqual(p.returncode, 0, f"{case}\n{p.stdout}{p.stderr}")
        self.assertEqual(p.stderr, "", case)
        report = run / "dreamlands.json"
        fields = dict(kv.split("=", 1) for kv in p.stdout.split() if "=" in kv)
        return (
            fields,
            (json.loads(report.read_text()) if report.exists() else None),
            run,
        )

    def pick(self, name, player, hound, target, pet=None, stairs=None, door=None):
        """One real chaos_haunt_pick in a 5x5 room; offsets are in the room."""
        env = dict(
            HAUNT_ROOM_PACK=str(PACK),
            HAUNT_ROOM_PICK="%d,%d,%d,%d" % (*hound, *target),
        )
        if pet:
            env["HAUNT_ROOM_PET"] = "%d,%d" % pet
        if stairs:
            env["HAUNT_ROOM_STAIRS"] = "%d,%d" % stairs
        if door:
            env["HAUNT_ROOM_DOOR"] = "%d,%d" % door
        fields, _, _ = self.run_room(name, [5, 5, *player, 1], **env)
        return fields

    # --- the pick: an occupied target square ---------------------------------
    def test_pick_steps_around_pet_on_requested_square(self):
        # The pack asks for (2,2), where the pet stands. Of the squares nearer
        # the target (3,3), (1,2) and (2,1) tie; the game's candidate order
        # (x first) keeps (1,2). No RNG is drawn (asserted in the fixture).
        got = self.pick("pick-around", (4, 4), (1, 1), (3, 3), pet=(2, 2))
        self.assertEqual((got["square"], got["adjacent"]), ("1,2", "0"), got)

    def test_pick_never_steps_next_to_player_when_request_was_not(self):
        # Same, but the player at (0,2): (1,2) would touch the player, which
        # the requested (2,2) would not. The engine takes (2,1).
        got = self.pick("pick-no-contact", (0, 2), (1, 1), (3, 3), pet=(2, 2))
        self.assertEqual((got["square"], got["adjacent"]), ("2,1", "0"), got)

    def test_pick_stays_put_when_no_step_is_nearer(self):
        # The pet is on the target itself, next to the hound: no legal square
        # is strictly nearer to it, so the hound stays put, as before #190.
        got = self.pick("pick-stay", (4, 4), (1, 1), (2, 1), pet=(2, 1))
        self.assertEqual((got["choice"], got["square"]), ("-1", "-1,-1"), got)

    def test_pick_request_for_player_square_stays_put(self):
        # Asking for the player's own square never moves the hound: that
        # would be an attack the step request cannot make.
        got = self.pick("pick-player", (2, 2), (1, 1), (2, 2))
        self.assertEqual((got["choice"], got["square"]), ("-1", "-1,-1"), got)

    # --- the pick: a requested square that is not plain floor ----------------
    def test_pick_steps_around_start_stairs(self):
        # The trail target is the up staircase the player started on (2,2),
        # next to the hound. Before #190 the hound refused and stayed put.
        # Now it takes the nearer legal square; (1,2) and (2,1) tie and the
        # candidate order keeps (1,2).
        got = self.pick("pick-stairs", (4, 4), (1, 1), (2, 2), stairs=(2, 2))
        self.assertEqual((got["square"], got["adjacent"]), ("1,2", "0"), got)

    def test_pick_steps_around_stairs_on_the_way(self):
        # The stairs are on the way to the target (3,3): step around them.
        got = self.pick("pick-stairs-way", (4, 4), (1, 1), (3, 3), stairs=(2, 2))
        self.assertEqual((got["square"], got["adjacent"]), ("1,2", "0"), got)

    def test_pick_doorway_diagonal_stays_illegal(self):
        # A doorway in the east wall at (5,2). The hound at (4,1) asks for the
        # diagonal into it, which the game (mfndpos) does not offer; the
        # engine takes the orthogonal square next to the doorway instead and
        # never the doorway itself.
        got = self.pick("pick-door-diag", (0, 4), (4, 1), (5, 2), door=(5, 2))
        self.assertEqual((got["square"], got["adjacent"]), ("4,2", "0"), got)

    def test_pick_doorway_straight_stays_put(self):
        # Straight at the doorway from next to it: the doorway is not plain
        # floor and no legal square is strictly nearer, so the hound stays.
        got = self.pick("pick-door-straight", (0, 4), (4, 2), (5, 2), door=(5, 2))
        self.assertEqual((got["choice"], got["square"]), ("-1", "-1,-1"), got)

    def test_pick_free_request_unchanged(self):
        got = self.pick("pick-free", (4, 4), (1, 1), (3, 3))
        self.assertEqual(got["square"], "2,2", got)

    # --- the whole trial -------------------------------------------------------
    def test_pet_on_hound_target_trial_passes(self):
        # Before #190 these rejected the one trial: moved 1, blocked 63.
        for room, player, pet in (
            ((4, 4), (0, 2), (1, 2)),
            ((5, 4), (0, 2), (1, 2)),
            ((5, 5), (4, 3), (3, 3)),
        ):
            with self.subTest(room=room, player=player, pet=pet):
                name = "pet-%dx%d" % room
                fields, report, run = self.run_room(
                    name, [*room, *player, 1], HAUNT_ROOM_PET="%d,%d" % pet
                )
                self.assertEqual(report["accepted"], 1, report)
                self.assertGreater(report["moved"], 8, report)
                self.assertEqual(report["escaped"], 1, report)
                self.assertEqual(
                    (fields["checked"], fields["active"], fields["spent"]),
                    ("1", "1", "2"),
                )
                self.assertEqual(fields["telegraphs"], "1")

    def test_start_stairs_trial_passes(self):
        # The player paces from the up staircase they started on, with the
        # pet beside it, as in most real start rooms.
        for room, player, pet in (
            ((5, 4), (1, 1), (2, 2)),
            ((6, 4), (2, 1), (3, 1)),
        ):
            with self.subTest(room=room, player=player, pet=pet):
                fields, report, _ = self.run_room(
                    "stairs-%dx%d" % room,
                    [*room, *player, 1],
                    HAUNT_ROOM_STAIRS="%d,%d" % player,
                    HAUNT_ROOM_PET="%d,%d" % pet,
                )
                self.assertIsNotNone(report, fields)
                self.assertEqual(report["accepted"], 1, report)
                self.assertGreater(report["moved"], 8, report)

    def test_cornered_residual_documented(self):
        # Accepted residual (#190 option (c); #194 tracks the fix). The trial
        # bot walks only plain floor, so in a 4x3 room the stairs and the pet
        # leave it a pocket with no square 3 away from the hound: the hound
        # moves, reaches it and the trial rejects. This pins the known
        # behaviour; when #194 lets the bot use stairs, expect it to pass.
        fields, report, _ = self.run_room(
            "cornered-4x3",
            [4, 3, 0, 1, 1],
            HAUNT_ROOM_STAIRS="0,1",
            HAUNT_ROOM_PET="1,1",
        )
        self.assertIsNotNone(report, fields)
        self.assertEqual((report["accepted"], report["escaped"]), (0, 0), report)
        self.assertGreater(report["moved"], 0, report)
        self.assertGreater(report["contacts"], 0, report)

    def test_bare_rooms(self):
        # No hound can be placed 3 squares away in 3x3: nothing is spent or
        # written, as before. Small and larger bare rooms pass the trial.
        fields, report, run = self.run_room("bare-3x3", [3, 3, 1, 1, 1])
        self.assertEqual(fields["checked"], "0")
        self.assertIsNone(report)
        self.assertFalse((run / "haunting-used.lua").exists())
        self.assertFalse((run / "dreamlands.json").exists())
        events = (run / "events.jsonl").read_text().splitlines()
        self.assertFalse([e for e in events if '"event":"haunting"' in e], events)
        self.assertEqual(fields["spent"], "0")
        for room, player in (((4, 3), (0, 0)), ((6, 4), (2, 1)), ((12, 6), (5, 3))):
            with self.subTest(room=room, player=player):
                _, report, _ = self.run_room("bare-%dx%d" % room, [*room, *player, 1])
                self.assertEqual(report["accepted"], 1, report)


if __name__ == "__main__":
    unittest.main()
