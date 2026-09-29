"""Linked dog_move: extra attention vs no-candidate control. Not ordinary play."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from chaos.next_use_envelope import engine_run_hex, publish_envelope
from native_rng import controlled_rng_objects
from artifact_hygiene import RetainOnFailure, track

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
class NextUseDogMoveTests(RetainOnFailure):
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

    def run_case(self, name, row=ROW, move=40, pet=None):
        folder = Path(
            track(self, tempfile.mkdtemp(prefix="nyarl-next-use-dogmove-run-"))
        )
        os.chmod(folder, 0o700)
        host = dict(HOST)
        host["run"] = engine_run_hex(folder)
        host["move"] = move
        publish_envelope(folder, row, host)
        original = (folder / "next_use-envelope.json").read_bytes()
        env = dict(os.environ)
        env["NYARLATHACK_RUN_DIR"] = str(folder)
        env["NYARLATHACK_OBSERVATIONS"] = "1"
        env["TERM"] = "xterm"
        env["COLUMNS"] = "80"
        env["LINES"] = "24"
        env.pop("NYARLATHACK_TEST_PET", None)
        if pet is not None:
            env["NYARLATHACK_TEST_PET"] = pet
        p = subprocess.run(
            [str(self.exe), name, str(folder)],
            # The tty fixture may wait for a key at --More--; an inherited
            # open-but-silent stdin pipe blocks it until the timeout.
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
            cwd=folder,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        if name in (
            "safehit",
            "safemiss",
            "obsorigin",
            "unequalclock",
            "obsrebind",
            "obsrebind_level",
        ):
            self.assertEqual((folder / "next_use-envelope.json").read_bytes(), original)
            self.assertFalse((folder / "fixture-envelope-held.json").exists())
            self.assertRegex(
                (folder / "next_use-owner").read_text(), r"^NUO1:[0-9a-f]{16}\n$"
            )
            sessions = [
                json.loads(line)
                for line in (folder / "events.jsonl").read_text().splitlines()
            ]
            self.assertEqual(
                [row["detail"] for row in sessions if row["event"] == "session"],
                ["new"],
            )
        self.last_folder = folder
        return json.loads((folder / "result.json").read_text())

    def receipt_rows(self):
        path = self.last_folder / "next_use-receipt.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()]

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
        self.assertEqual(positive["post_glyph"], positive["pre_glyph"])
        self.assertEqual(positive["public"], 1)
        self.assertEqual(positive["public2"], 1)
        self.assertEqual(positive["displaced"], 1)
        self.assertEqual(positive["delivered"], 1)
        self.assertEqual(positive["pre_public"], 1)
        self.assertEqual((control["mx"], control["my"]), (bypass["mx"], bypass["my"]))
        self.assertEqual(control["rng_next"], bypass["rng_next"])
        self.assertEqual(control["reseed"], bypass["reseed"])

    # #196 (A2): the extra-attention move (dog_goal via dog_move) was only
    # validated on the little dog. Every companion type with dog data must
    # take the same visible, player-ward, still-tame move and deliver it.
    def test_extra_attention_move_on_other_companion_types(self):
        for pet in ("dog", "large_dog", "kitten", "housecat", "pony"):
            with self.subTest(pet=pet):
                control = self.run_case("none", pet=pet)
                bypass = self.run_case("bypass", pet=pet)
                row = self.run_case("admit", pet=pet)
                self.assertEqual(row["mtyp"], control["mtyp"])
                self.assertEqual(row["alive"], 1)
                self.assertEqual(row["mtame"], 10)
                self.assertEqual(row["mpeaceful"], 1)
                self.assertEqual(row["arm"], 2)
                self.assertEqual(row["telegraph"], 1)
                self.assertEqual(row["ready_before"], 1)
                self.assertEqual(row["ready_after"], 0)
                self.assertEqual(row["classifier"], 1)
                self.assertEqual(row["pre_public"], 1)
                self.assertEqual(row["displaced"], 1)
                self.assertEqual(row["delivered"], 1)
                self.assertEqual(row["invalid"], 0)
                # The move is the one the player sees: published on the map,
                # same glyph before and after, and toward the player.
                self.assertEqual(row["public"], 1)
                self.assertEqual(row["public2"], 1)
                self.assertEqual(row["post_glyph"], row["pre_glyph"])
                self.assertLess(row["dist_after"], row["dist_before"])
                # No-whisper equals stock: without a program, no extra draw.
                self.assertEqual(control["ready_before"], 0)
                self.assertEqual(
                    (control["mx"], control["my"]), (bypass["mx"], bypass["my"])
                )
                self.assertEqual(control["rng_next"], bypass["rng_next"])
                self.assertEqual(control["reseed"], bypass["reseed"])

    def pick(self, spec):
        os.environ["NYARLATHACK_TEST_PICK"] = spec
        try:
            return self.run_case("pick")
        finally:
            del os.environ["NYARLATHACK_TEST_PICK"]

    # #196 (B1): the player is at (10, 10). Nearest by squared distance wins;
    # ties go to the top row, then the leftmost column. List order and m_id
    # never decide, and the pick draws no RNG.
    def test_pick_nearest_wins_regardless_of_list_order(self):
        for spec in ("13,10,dog;11,11,kitten", "11,11,kitten;13,10,dog"):
            with self.subTest(spec=spec):
                row = self.pick(spec)
                self.assertEqual((row["px"], row["py"]), (11, 11), row)
                self.assertEqual(row["reason"], 0)

    def test_pick_tie_goes_to_top_row_then_leftmost(self):
        cases = {
            "10,12,dog;10,8,dog": (10, 8),
            "10,8,dog;10,12,dog": (10, 8),
            "12,10,pony;8,10,housecat": (8, 10),
            "8,10,housecat;12,10,pony": (8, 10),
            "12,12,dog;8,12,dog;12,8,dog;8,8,dog": (8, 8),
        }
        for spec, square in cases.items():
            with self.subTest(spec=spec):
                row = self.pick(spec)
                self.assertEqual((row["px"], row["py"]), square, row)

    def test_pick_ignores_m_id(self):
        low = self.pick("12,10,dog,7;8,10,dog,99")
        high = self.pick("12,10,dog,99;8,10,dog,7")
        self.assertEqual((low["px"], low["py"]), (8, 10))
        self.assertEqual((high["px"], high["py"]), (8, 10))
        self.assertEqual((low["m_id"], high["m_id"]), (99, 7))

    def test_pick_draws_no_rng(self):
        for spec in ("13,10,dog;11,11,kitten", "10,8,dog;10,12,dog",
                     "11,10,hostile", "11,10,leashed"):
            with self.subTest(spec=spec):
                row = self.pick(spec)
                self.assertEqual(row["after_pick"], row["control"], row)
                self.assertEqual(row["reseed_delta"], 0, row)

    # #196: the recorded reason. A hostile dog shows no pet glyph, so no
    # companion is in view (1); a leashed pet is in view but excluded (2).
    def test_pick_records_why_nothing_qualified(self):
        self.assertEqual(self.pick("11,10,hostile")["reason"], 1)
        row = self.pick("11,10,leashed")
        self.assertEqual((row["picked"], row["reason"]), (0, 2))
        row = self.pick("11,10,leashed;14,10,large_dog")
        self.assertEqual((row["px"], row["py"], row["reason"]), (14, 10, 0))

    def test_changed_presentation_target_or_level_cannot_certify_old_event(self):
        for name in ("postid", "postlevel"):
            with self.subTest(name=name):
                row = self.run_case(name)
                self.assertEqual(row["delivered"], 1)
                self.assertEqual(row["displaced"], 1)
                self.assertEqual(row["public"], 0)
                self.assertEqual(row["public2"], 0)

    def test_unrelated_glyph_cannot_certify_companion_attention(self):
        row = self.run_case("postglyph")
        self.assertEqual(row["delivered"], 1)
        self.assertEqual(row["displaced"], 1)
        self.assertEqual(row["public"], 0)
        self.assertEqual(row["public2"], 0)

    def test_same_companion_id_cannot_cross_game_or_level_lifetime(self):
        for name in ("level_lifetime", "game_lifetime"):
            with self.subTest(name=name):
                row = self.run_case(name)
                self.assertEqual(row["arm"], 2)
                self.assertEqual(row["ready_before"], 0)
                self.assertEqual(row["public"], 0)
                self.assertEqual(row["delivered"], 0)

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

    def test_superseded_origin_rebinds_to_newest_whistle_and_delivers(self):
        # #177 option 1, real observation path: envelope names root 10; a
        # newer delivered whistle on the same level replaces it before the
        # safe point. The engine binds the newest origin, W delivers.
        row = self.run_case("obsrebind")
        self.assertGreater(row["bound_root"], 10)
        self.assertEqual(row["spent"], 1)
        self.assertEqual(row["arm"], 2)
        self.assertEqual(row["ready_before"], 1)
        self.assertEqual(row["public"], 1)
        self.assertEqual(row["delivered"], 1)
        admission = [r for r in self.receipt_rows() if r.get("kind") == 2]
        self.assertEqual(
            admission[0]["origins"],
            [{"family": "W", "published": 10, "bound": row["bound_root"]}],
        )

    def test_rebound_run_replays_identically(self):
        first = self.run_case("obsrebind")
        second = self.run_case("obsrebind")
        for key in ("mx", "my", "rng_next", "reseed", "bound_root", "public"):
            self.assertEqual(first[key], second[key], key)

    def test_newer_origin_on_other_level_does_not_rebind(self):
        row = self.run_case("obsrebind_level")
        self.assertEqual(row["spent"], 0)
        self.assertEqual(row["arm"], 0)
        self.assertEqual(row["public"], 0)
        decisions = [r for r in self.receipt_rows() if "next_use_decision_v" in r]
        self.assertEqual(len(decisions), 1)
        self.assertIn("origin_superseded", decisions[0]["reasons"])

    def test_save_restore_mid_rebind_keeps_bound_origin(self):
        row = self.run_case("obsrebind_save")
        self.assertEqual(row["restored"], 1)
        self.assertEqual(row["spent2"], 1)
        self.assertEqual(row["arm"], 2)
        self.assertEqual(row["public"], 1)

    def test_save_restore_continues_without_readmit(self):
        row = self.run_case("save")
        self.assertEqual(row["arm"], 2)
        self.assertEqual(row["restored"], 1)
        self.assertEqual(row["spent2"], 0)
        self.assertEqual(row["ready_before"], 1)
        self.assertEqual(row["ready_after"], 0)
        self.assertEqual(row["public"], 1)

    def test_save_restore_missing_companion_does_not_witness(self):
        row = self.run_case("savegone")
        self.assertEqual(row["arm"], 2)
        self.assertEqual(row["restored"], 1)
        self.assertEqual(row["public"], 0)

    def test_save_restore_other_monster_does_not_rebind(self):
        row = self.run_case("saveother")
        self.assertEqual(row["arm"], 2)
        self.assertEqual(row["restored"], 1)
        self.assertEqual(row["ready_before"], 0)
        self.assertEqual(row["orig_ready_after"], 1)
        self.assertEqual(row["public"], 0)


if __name__ == "__main__":
    unittest.main()
