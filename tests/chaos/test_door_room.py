"""#1 door_reluctance end to end against the real engine objects.

tests/chaos/door_room.c links the built game objects (a controlled copy of
rnd.o, as in test_haunt_room) and calls the real doopen_indir on a closed
door. The rule is not wrapped: the fixture predicts rnl(20) from the same
seed and checks every outcome against the threshold the engine must apply,
12 normally and 6 while an admitted door_reluctance effect is active.
"""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from artifact_hygiene import RetainOnFailure
from native_rng import controlled_rng_objects

ROOT = Path(__file__).resolve().parents[2]
N = 200


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class DoorRoomTests(RetainOnFailure):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(
            cls.track_class_artifacts(tempfile.mkdtemp(prefix="nyarl-door-room-"))
        )
        print("DOOR_ROOM_ARTIFACTS=" + str(cls.root), flush=True)
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
        cls.exe = cls.root / "door_room"
        command = [
            "cc",
            "-g",
            "-DCHAOS",
            "-I" + str(ROOT / "include"),
            str(ROOT / "tests/chaos/door_room.c"),
            *map(str, controlled_rng_objects(objects, cls.root)),
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

    def run_room(self, name, seed, active, observations):
        case = self.root / name
        run = case / "run"
        run.mkdir(parents=True)
        run.chmod(0o700)
        environ = dict(
            os.environ,
            NYARLATHACK_ECHOES="0",
            NYARLATHACK_RUN_DIR=str(run),
            NYARLATHACK_OBSERVATIONS="1" if observations else "0",
        )
        p = subprocess.run(
            [str(self.exe), str(seed), str(N), str(int(active))],
            cwd=case,
            env=environ,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=60,
        )
        (case / "stdout").write_text(p.stdout)
        (case / "stderr").write_text(p.stderr)
        self.assertEqual(p.returncode, 0, f"{case}\n{p.stdout}{p.stderr}")
        self.assertEqual(p.stderr, "", case)
        fields = {k: int(v) for k, v in (kv.split("=", 1) for kv in p.stdout.split())}
        events = run / "events.jsonl"
        rows = (
            [json.loads(line) for line in events.read_text().splitlines()]
            if events.exists()
            else []
        )
        return fields, rows

    def check(self, fields, active):
        self.assertEqual(fields["threshold"], 6 if active else 12)
        self.assertEqual(fields["mismatches"], 0, fields)
        self.assertEqual(fields["other_msg"], 0, fields)
        self.assertEqual(fields["opens_msg"], fields["opened"], fields)
        self.assertEqual(fields["opens_msg"] + fields["resists_msg"], N, fields)
        self.assertEqual(fields["spent"], int(active), fields)

    def test_effect_halves_the_open_threshold(self):
        off, _ = self.run_room("off", 1000, False, False)
        on, _ = self.run_room("on", 1000, True, False)
        self.check(off, False)
        self.check(on, True)
        # Same seeds, same native draws: the effect only closes doors that
        # would have opened (rnl in [6, 12)), never opens one.
        self.assertLess(on["opened"], off["opened"])
        self.assertGreater(on["opened"], 0)
        print(f"door opened {off['opened']}/{N} without, {on['opened']}/{N} with")

    def test_each_attempt_is_one_door_open_root(self):
        fields, rows = self.run_room("observed", 2000, True, True)
        self.check(fields, True)
        observed = [r for r in rows if r.get("event") == "observation"]
        doors = [
            r["observation"]
            for r in observed
            if r["observation"]["operation"] == "door_open"
        ]
        started = [o for o in doors if o["stage"] == "started"]
        self.assertEqual(len(started), N)
        # No window is initialised, so the native message is raw_print and
        # never tty-delivered: every root closes without a notice, and a door
        # attempt can never block.
        self.assertEqual(sorted({o["stage"] for o in doors}), ["completed", "started"])
        roots = [o["root_seq"] for o in doors if o["stage"] == "completed"]
        self.assertEqual(len(roots), N)
        self.assertEqual(len(set(roots)), N)

    def test_no_root_without_observations(self):
        fields, rows = self.run_room("unobserved", 3000, False, False)
        self.check(fields, False)
        self.assertFalse(
            any(r.get("observation", {}).get("operation") == "door_open" for r in rows)
        )


if __name__ == "__main__":
    unittest.main()
