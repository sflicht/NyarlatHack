"""ENGINE-UNIT: C (broad next-use) runtime after real admit/install.

Each case publishes a real envelope with chaos.next_use_envelope, admits it
through the safe layer and drives the runtime's public entry points. A v2
(single-use) envelope is the control: its rules must not change.
"""

from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest

from chaos.next_use_envelope import BROAD_USES, publish_envelope

ROOT = Path(__file__).resolve().parents[2]
CALLBACKS = 8  # CHAOS_NEXT_USE_BROAD_CALLBACKS
ROWS = {
    "W": {
        "family": "W",
        "op": "whistle_attention",
        "origin": {
            "root_seq": 10,
            "notice_seq": 11,
            "end_seq": 12,
            "fact": "sound_high",
        },
    },
    "F": {
        "family": "F",
        "op": "fountain_refresh",
        "origin": {
            "root_seq": 10,
            "notice_seq": 11,
            "end_seq": 12,
            "fact": "water_refreshed",
        },
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
COMMITTED, TERMINATED = 3, 4  # enum chaos_next_use_attempt_phase


class NextUseBroadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="nyarl-next-use-broad-")
        cls.addClassCleanup(cls.build.cleanup)
        cls.binary = Path(cls.build.name) / "next-use-broad"
        flags = subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "lua5.4"], text=True
        ).split()
        command = [
            "/usr/bin/gcc",
            "-DCHAOS",
            "-ffunction-sections",
            "-fdata-sections",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wno-misleading-indentation",
            "-isystem",
            str(ROOT / "include"),
            str(ROOT / "tests/chaos/next_use_broad.c"),
            str(ROOT / "src/chaos_next_use.c"),
            str(ROOT / "src/chaos_next_use_admission.c"),
            str(ROOT / "src/chaos_next_use_runtime.c"),
            str(ROOT / "src/chaos_next_use_io.c"),
            str(ROOT / "src/chaos_next_use_journal.c"),
            str(ROOT / "src/chaos_next_use_safe.c"),
            str(ROOT / "src/chaos_protocol.c"),
            str(ROOT / "src/chaos_lua.c"),
            "-Wl,--gc-sections",
            *flags,
            "-lm",
            "-o",
            str(cls.binary),
        ]
        result = subprocess.run(command, capture_output=True, timeout=60)
        if result.returncode:
            raise RuntimeError(result.stderr.decode())

    def run_case(self, family, scenario, broad=True, journal=False):
        folder = tempfile.mkdtemp(prefix="nyarl-next-use-broad-run-")
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", folder], check=False))
        os.chmod(folder, 0o700)
        publish_envelope(folder, ROWS[family], HOST, repair=True, broad=broad)
        env = dict(os.environ)
        if journal:
            env["NYARL_BROAD_JOURNAL"] = "1"
        p = subprocess.run(
            [str(self.binary), folder, "40", "7", HOST["run"], family, scenario],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        self.folder = Path(folder)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        rows = [json.loads(line) for line in p.stdout.splitlines() if line]
        admit = rows[0]
        self.assertEqual(admit["result"], 1, rows)
        return admit, {r["step"]: r for r in rows[1:]}, rows[1:]

    def test_broad_telegraph_and_snapshot_version(self):
        for family in "WF":
            with self.subTest(family=family):
                admit, steps, _ = self.run_case(family, "none")
                self.assertEqual(admit["telegraphs"], 1)
                self.assertEqual(admit["telegraph"], f"next-use-v3-{family}")
                self.assertEqual(steps["installed"]["snapshot_v"], 7)
                self.assertEqual(steps["installed"]["broad_uses"], BROAD_USES)
                self.assertEqual(steps["installed"]["broad_active"], 1)

    def test_single_use_control_keeps_v6_and_old_telegraph(self):
        admit, steps, _ = self.run_case("W", "none", broad=False)
        self.assertEqual(admit["telegraph"], "next-use-v2-W")
        self.assertEqual(steps["installed"]["snapshot_v"], 6)
        self.assertEqual(steps["installed"]["broad_uses"], 0)
        self.assertEqual(steps["installed"]["broad_active"], 0)

    def test_repeat_uses_deliver_up_to_the_declared_bound(self):
        for family in "WF":
            with self.subTest(family=family):
                _, steps, _ = self.run_case(family, "repeat")
                self.assertEqual(steps["use1"]["result"], 1)
                self.assertEqual(steps["use1"]["delivered"], 1)
                self.assertEqual(steps["use1"]["phase"], COMMITTED)
                self.assertEqual(steps["use2"]["result"], 1)
                self.assertEqual(steps["use2"]["delivered"], 2)
                # Bound reached between uses: COMPLETED, no third callback.
                self.assertEqual(steps["use2"]["phase"], TERMINATED)
                self.assertEqual(steps["use3"]["result"], 0)
                self.assertEqual(steps["use3"]["callbacks"], 2)

    def test_single_use_control_answers_one_use(self):
        _, steps, _ = self.run_case("F", "repeat", broad=False)
        self.assertEqual(steps["use1"]["result"], 1)
        self.assertEqual(steps["use1"]["phase"], TERMINATED)
        self.assertEqual(steps["use2"]["result"], 0)

    def test_undelivered_uses_stop_at_the_callback_bound(self):
        _, _, rows = self.run_case("F", "quiet-uses")
        self.assertEqual([r["result"] for r in rows[1:]], [1] * CALLBACKS + [0])
        self.assertEqual(rows[CALLBACKS - 1 + 1]["phase"], TERMINATED)
        self.assertTrue(all(r["phase"] == COMMITTED for r in rows[1:CALLBACKS]))
        self.assertTrue(all(r["delivered"] == 0 for r in rows[1:]))

    def test_broad_program_survives_a_level_change(self):
        for family in "WF":
            with self.subTest(family=family):
                _, steps, _ = self.run_case(family, "level")
                self.assertEqual(steps["level2"]["phase"], COMMITTED)
                self.assertEqual(steps["level2-use"]["result"], 1)
                self.assertEqual(steps["level2-use"]["delivered"], 1)

    def test_single_use_control_ends_on_level_change(self):
        _, steps, _ = self.run_case("W", "level", broad=False)
        self.assertEqual(steps["level2"]["phase"], TERMINATED)
        self.assertEqual(steps["level2-use"]["result"], 0)

    def test_open_window_ends_on_leaving_its_level_program_lives(self):
        _, steps, _ = self.run_case("W", "level-window")
        self.assertEqual(steps["window-left-level"]["result"], 1)
        self.assertEqual(steps["window-left-level"]["phase"], COMMITTED)
        self.assertEqual(steps["window-left-level"]["delivered"], 0)
        self.assertEqual(steps["next-level-use"]["result"], 1)
        self.assertEqual(steps["next-level-use"]["delivered"], 1)

    def test_suppressed_whistle_consumes_nothing(self):
        _, steps, _ = self.run_case("W", "suppressed")
        self.assertEqual(steps["suppressed"]["phase"], COMMITTED)
        self.assertEqual(steps["suppressed"]["callbacks"], 0)
        # Nothing is written either: a broad program may see many suppressed
        # whistles, and its private record bound counts only callbacks.
        self.assertEqual(steps["suppressed"]["private"], steps["installed"]["private"])
        self.assertEqual(steps["suppressed"]["slot_w"], steps["installed"]["slot_w"])
        self.assertEqual(steps["suppressed"]["result"], 1)  # still open
        self.assertEqual(steps["after-suppressed"]["result"], 1)
        self.assertEqual(steps["after-suppressed"]["delivered"], 1)

    def test_single_use_control_suppression_consumes_the_program(self):
        _, steps, _ = self.run_case("W", "suppressed", broad=False)
        self.assertEqual(steps["suppressed"]["phase"], TERMINATED)
        self.assertEqual(steps["after-suppressed"]["result"], 0)

    def test_program_expiry_still_applies(self):
        for family in "WF":
            with self.subTest(family=family):
                _, steps, _ = self.run_case(family, "expiry")
                self.assertEqual(steps["expired"]["phase"], TERMINATED)

    def journal(self):
        from chaos.next_use_journal import read_journal

        (path,) = self.folder.glob("next_use-journal*.jsonl")
        return path, read_journal(path)

    def test_reader_accepts_broad_journals_and_their_controls(self):
        cases = {
            "W": ("repeat", "level", "quiet-uses", "suppressed", "level-window"),
            "F": ("repeat", "level", "quiet-uses"),
        }
        for family, scenarios in cases.items():
            for scenario in scenarios + ("expiry",):
                for broad in (True, False):
                    with self.subTest(family=family, scenario=scenario, broad=broad):
                        self.run_case(family, scenario, broad=broad, journal=True)
                        _, trace = self.journal()
                        header = trace["records"][0]["data"]["snapshot"]
                        self.assertEqual(header["snapshot_v"], 7 if broad else 6)
                        self.assertEqual("broad_uses" in header, broad)

    def test_broad_quiet_uses_reach_the_callback_bound_in_the_journal(self):
        self.run_case("F", "quiet-uses", journal=True)
        _, trace = self.journal()
        self.assertTrue(trace["structurally_complete"])
        ordinals = [
            r["data"]["callback_ordinal"]
            for r in trace["records"][1:]
            if r["kind"] == "transition"
        ]
        self.assertEqual(max(ordinals), CALLBACKS)

    def test_save_restore_resumes_the_broad_journal(self):
        for family in "WF":
            with self.subTest(family=family):
                _, steps, _ = self.run_case(family, "restore", journal=True)
                self.assertEqual(steps["use1"]["delivered"], 1)
                self.assertEqual(steps["restored"]["result"], 1)
                self.assertEqual(steps["restored"]["snapshot_v"], 7)
                self.assertEqual(steps["restored"]["delivered"], 1)
                self.assertEqual(steps["resumed"]["result"], 1)  # C mirror
                self.assertEqual(steps["use2"]["delivered"], 2)
                self.assertEqual(steps["use2"]["phase"], TERMINATED)
                _, trace = self.journal()
                self.assertTrue(trace["structurally_complete"])

    def test_tampered_broad_snapshot_is_refused(self):
        _, steps, _ = self.run_case("W", "tamper")
        self.assertEqual(steps["untampered"]["result"], 1)
        for step in ("tamper-uses", "tamper-version", "tamper-delivered"):
            with self.subTest(step=step):
                self.assertEqual(steps[step]["result"], 0)

    def edit_header(self, path, edit):
        """Rewrite the header payload and re-chain every digest."""
        import hashlib

        lines = path.read_bytes().splitlines(keepends=True)
        out, prev = [], "0" * 64
        for index, line in enumerate(lines):
            payload = json.loads(line)["payload"]
            payload["prev"] = prev
            if index == 0:
                edit(payload["data"])
            raw = json.dumps(payload, separators=(",", ":")).encode()
            prev = hashlib.sha256(raw).hexdigest()
            out.append(b'{"payload":' + raw + b',"sha256":"' + prev.encode() + b'"}\n')
        path.write_bytes(b"".join(out))

    def test_reader_rejects_broad_header_tampering(self):
        from chaos.next_use_journal import JournalError, read_journal

        def bump_uses(d):
            d["snapshot"]["broad_uses"] = 1

        def old_version(d):
            d["snapshot"]["snapshot_v"] = 6

        def drop_broad(d):
            for key in ("broad_uses", "delivered", "armed_level_token"):
                del d["snapshot"][key]

        for name, edit in (
            ("uses", bump_uses),
            ("version", old_version),
            ("fields", drop_broad),
        ):
            with self.subTest(edit=name):
                self.run_case("W", "repeat", journal=True)
                path, _ = self.journal()
                self.edit_header(path, edit)
                with self.assertRaises(JournalError):
                    read_journal(path)

    def test_reader_rechain_helper_preserves_a_valid_journal(self):
        from chaos.next_use_journal import read_journal

        self.run_case("W", "repeat", journal=True)
        path, _ = self.journal()
        self.edit_header(path, lambda d: None)
        self.assertTrue(read_journal(path)["structurally_complete"])


if __name__ == "__main__":
    unittest.main()
