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
    # --- #201: never spawn within the pet's reach -------------------------------
    def assert_nothing_spent(self, fields, report, run):
        self.assertEqual(fields["checked"], "0", fields)
        self.assertIsNone(report)
        self.assertFalse((run / "haunting-used.lua").exists())
        self.assertFalse((run / "dreamlands.json").exists())
        events = (run / "events.jsonl").read_text().splitlines()
        self.assertFalse([e for e in events if '"event":"haunting"' in e], events)
        self.assertEqual(
            (fields["spent"], fields["active"], fields["telegraphs"], fields["rng"]),
            ("0", "0", "0", "0"),
            fields,
        )

    def test_pet_near_every_candidate_no_spend(self):
        # Every square that could hold the hound (in view, 3 to 5 from the
        # player) is within 4 of the pet. The tick returns before the one
        # trial: nothing is spent or written, no RNG is drawn, and repeating
        # the tick changes nothing. These are the #190 rooms whose trial used
        # to run with the pet beside the hound's path.
        for room, player, pet in (
            ((4, 4), (0, 2), (1, 2)),
            ((5, 4), (0, 2), (1, 2)),
            ((5, 5), (4, 3), (3, 3)),
            ((12, 6), (1, 2), (2, 2)),
        ):
            with self.subTest(room=room, player=player, pet=pet):
                fields, report, run = self.run_room(
                    "pet-near-%dx%d" % room,
                    [*room, *player, 1, 5],
                    HAUNT_ROOM_PET="%d,%d" % pet,
                )
                self.assert_nothing_spent(fields, report, run)

    def test_pet_moves_off_then_trial_runs_later(self):
        # Same 12x6 room: nothing qualifies while the pet is beside the
        # player. Before the third tick the pet walks to the far corner; that
        # tick places the hound more than 4 from it and runs the one trial.
        fields, report, run = self.run_room(
            "pet-away-12x6",
            [12, 6, 1, 2, 1, 3],
            HAUNT_ROOM_PET="2,2",
            HAUNT_ROOM_PET_AWAY="3,11,5",
        )
        self.assertEqual(fields["checked_before_away"], "0", fields)
        self.assertIsNotNone(report, fields)
        self.assertEqual((report["accepted"], report["escaped"]), (1, 1), report)
        self.assertEqual(
            (
                fields["checked"],
                fields["active"],
                fields["spent"],
                fields["telegraphs"],
            ),
            ("1", "1", "2", "1"),
        )

    def test_start_stairs_trial_passes(self):
        # #190: the player paces from the up staircase they started on. The
        # pet is out of the way (#201 would not place the hound near it).
        for room, player in (((5, 4), (1, 1)), ((6, 4), (2, 1))):
            with self.subTest(room=room, player=player):
                fields, report, _ = self.run_room(
                    "stairs-%dx%d" % room,
                    [*room, *player, 1],
                    HAUNT_ROOM_STAIRS="%d,%d" % player,
                )
                self.assertIsNotNone(report, fields)
                self.assertEqual(report["accepted"], 1, report)
                self.assertGreater(report["moved"], 8, report)

    def test_start_stairs_with_pet_waits(self):
        # The #190 start rooms with the pet beside the stairs, and the 4x3
        # "cornered" pocket (#194): the pet is within 4 of every candidate,
        # so since #201 the trial is not spent there at all.
        for room, player, pet in (
            ((5, 4), (1, 1), (2, 2)),
            ((6, 4), (2, 1), (3, 1)),
            ((4, 3), (0, 1), (1, 1)),
        ):
            with self.subTest(room=room, player=player, pet=pet):
                fields, report, run = self.run_room(
                    "stairs-pet-%dx%d" % room,
                    [*room, *player, 1],
                    HAUNT_ROOM_STAIRS="%d,%d" % player,
                    HAUNT_ROOM_PET="%d,%d" % pet,
                )
                self.assert_nothing_spent(fields, report, run)

    # --- #194: the evasive bot walks where a player can -----------------------
    CORNERED = ROOT / "tests/chaos/haunt_maps/cornered-190-game24.txt"

    def cornered(self, name, stairs="<", fountain="{"):
        """Recorded #190 cornered map (real game 24 of the widened sweep,
        rebuilt from its screen; the pet removed, since #201 refuses the trial
        while it stands that close). The player starts between the up stairs
        (west) and a fountain (north-west); the hound spawns in the room."""
        text = self.CORNERED.read_text().replace("<", stairs).replace("{", fountain)
        path = self.root / (name + ".map")
        path.write_text(text)
        return self.run_room(name, [1, 1, 0, 0, 1], HAUNT_ROOM_MAP=str(path))

    def test_cornered_map_bot_uses_stairs_and_fountain(self):
        # Before #194 the bot walked plain floor only: here it was boxed in by
        # the stairs, the fountain and the walls, never got 3 squares away and
        # the trial was refused (accepted 0, escaped 0, 60 contacts).
        _, report, _ = self.cornered("cornered-194")
        self.assertIsNotNone(report)
        self.assertEqual((report["accepted"], report["escaped"]), (1, 1), report)
        self.assertLessEqual(report["max_damage"], 4, report)

    def test_cornered_map_bot_still_avoids_water_doors_traps(self):
        # The same squares as water, a closed door, a trap or a doorless
        # doorway stay off limits: the bot is cornered exactly as before #194.
        # Doorways are excluded on purpose (see bot_square in chaos_haunt.c):
        # the one-step-greedy bot parks in them and the plain-floor hound pins
        # it there, which doubled cornered trials in the #194 sweep.
        for name, glyph in (
            ("water", "~"),
            ("closed-door", "+"),
            ("trap", "^"),
            ("doorway", "D"),
        ):
            with self.subTest(square=name):
                _, report, _ = self.cornered("cornered-" + name, glyph, glyph)
                self.assertIsNotNone(report)
                self.assertEqual(
                    (report["accepted"], report["escaped"]), (0, 0), report
                )

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
