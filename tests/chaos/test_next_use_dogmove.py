"""Linked dog_move: extra attention vs no-candidate control. Not ordinary play."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from chaos.next_use_envelope import engine_run_hex, publish_envelope
from native_rng import controlled_rng_objects

ROOT = Path(__file__).resolve().parents[2]
ROW = {
    "family": "W",
    "op": "whistle_attention",
    "origin": {
        "root_seq": 10,
        "notice_seq": 11,
        "end_seq": 12,
        "fact": "sound_high",
    },
}
QUIET = {
    "family": "W",
    "op": "quiet",
    "origin": {
        "root_seq": 10,
        "notice_seq": 11,
        "end_seq": 12,
        "fact": "sound_high",
    },
}
HOST = {
    "at": 7,
    "id": 1,
    "level_dlevel": 1,
    "level_dnum": 0,
    "move": 40,
    "run": "ab" * 32,
    "variant": 0,
}


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class NextUseDogMoveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix="nyarl-next-use-dogmove-"))
        print("NEXT_USE_DOGMOVE_ARTIFACTS=" + str(cls.root), flush=True)
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
        cls.objects = controlled_rng_objects(objects, cls.root)
        cls.exe = cls.root / "dogmove"
        command = [
            "cc",
            "-g",
            "-DCHAOS",
            "-I" + str(ROOT / "include"),
            str(ROOT / "tests/chaos/next_use_dogmove.c"),
            *map(str, cls.objects),
            "-lncursesw",
            "-ltinfo",
            "-lm",
            *subprocess.check_output(
                ["pkg-config", "--libs", "lua5.4"], text=True
            ).split(),
            "-o",
            str(cls.exe),
        ]
        result = subprocess.run(command, capture_output=True, timeout=45)
        if result.returncode:
            raise RuntimeError(result.stderr.decode())

    def run_case(self, name, row=ROW, move=40):
        folder = Path(tempfile.mkdtemp(prefix="nyarl-next-use-dogmove-run-"))
        os.chmod(folder, 0o700)
        host = dict(HOST)
        host["run"] = engine_run_hex(folder)
        host["move"] = move
        publish_envelope(folder, row, host)
        env = dict(os.environ)
        env["NYARLATHACK_RUN_DIR"] = str(folder)
        env["NYARLATHACK_OBSERVATIONS"] = "1"
        env["TERM"] = "xterm"
        env["COLUMNS"] = "80"
        env["LINES"] = "24"
        p = subprocess.run(
            [str(self.exe), name, str(folder)],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
            cwd=folder,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return json.loads((folder / "result.json").read_text())

    def test_admitted_dog_move_consumes_extra_attention(self):
        control = self.run_case("none")
        positive = self.run_case("admit")
        bypass = self.run_case("bypass")
        self.assertEqual(control["ready_before"], 0)
        self.assertEqual(bypass["ready_before"], 0)
        self.assertEqual(positive["arm"], 2)
        self.assertEqual(positive["telegraph"], 1)
        self.assertEqual(positive["ready_before"], 1)
        self.assertEqual(positive["ready_after"], 0)
        self.assertEqual(positive["public"], 1)
        self.assertEqual(positive["public2"], 1)
        self.assertEqual(positive["displaced"], 1)
        self.assertEqual(positive["delivered"], 1)
        self.assertEqual(positive["pre_public"], 1)
        self.assertEqual((control["mx"], control["my"]), (bypass["mx"], bypass["my"]))
        self.assertEqual(control["rng_next"], bypass["rng_next"])
        self.assertEqual(control["reseed"], bypass["reseed"])

    def test_late_window_does_not_take_extra_attention(self):
        late = self.run_case("late")
        self.assertEqual(late["ready_before"], 0)
        self.assertEqual(late["ready_after"], 0)

    def test_quiet_intent_does_not_arm_attention(self):
        quiet = self.run_case("quiet", QUIET)
        self.assertEqual(quiet["arm"], 1)
        self.assertEqual(quiet["ready_before"], 0)
        self.assertEqual(quiet["ready_after"], 0)

    def test_dead_companion_does_not_publish_witness(self):
        dead = self.run_case("dead")
        self.assertEqual(dead["public"], 0)

    def test_wrong_id_does_not_rebind(self):
        row = self.run_case("wrongid")
        self.assertEqual(row["ready_before"], 0)
        self.assertEqual(row["orig_ready_after"], 1)

    def test_early_window_does_not_take_extra_attention(self):
        early = self.run_case("early")
        self.assertEqual(early["ready_before"], 0)
        self.assertEqual(early["ready_after"], 0)

    def test_no_eligible_companion_does_not_take_extra_attention(self):
        row = self.run_case("nonepet")
        self.assertEqual(row["ready_before"], 0)
        self.assertEqual(row["public"], 0)

    def test_wrong_family_action_does_not_apply(self):
        row = self.run_case("wrongfam")
        self.assertEqual(row["arm"], 2)
        self.assertEqual(row["f_action"], 0)

    def test_no_production_is_a_w_effect_bypass(self):
        """If extra_attention no longer requires witness.production, this fails."""
        row = self.run_case("noprod")
        self.assertEqual(row["ready_before"], 1)
        self.assertEqual(row["ready_after"], 1)
        self.assertEqual(row["public"], 0)

    def test_hidden_map_does_not_publish_witness(self):
        row = self.run_case("hidden")
        self.assertEqual(row["ready_before"], 1)
        self.assertEqual(row["public"], 0)

    def test_changed_companion_does_not_publish_witness(self):
        row = self.run_case("changed")
        self.assertEqual(row["public"], 0)

    def test_chaos_safe_without_origin_does_not_admit(self):
        row = self.run_case("safemiss")
        self.assertEqual(row["arm"], 0)
        self.assertEqual(row["spent"], 0)
        self.assertEqual(row["ready_before"], 0)
        self.assertEqual(row["public"], 0)

    def test_chaos_safe_with_origin_admits_once(self):
        row = self.run_case("safehit")
        self.assertEqual(row["spent"], 1)
        self.assertEqual(row["arm"], 2)
        self.assertEqual(row["ready_before"], 1)

    def test_observation_origin_admits_via_chaos_safe(self):
        row = self.run_case("obsorigin")
        self.assertEqual(row["spent"], 1)
        self.assertEqual(row["arm"], 2)
        self.assertEqual(row["ready_before"], 1)

    def test_unequal_moves_uses_monstermoves_origin_clock(self):
        row = self.run_case("unequalclock", move=200)
        self.assertEqual(row["spent"], 1)
        self.assertEqual(row["arm"], 2)


if __name__ == "__main__":
    unittest.main()
