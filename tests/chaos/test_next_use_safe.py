"""ENGINE-UNIT: opt-in safe-point admit once; not gameplay."""

from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest

from chaos.next_use_envelope import publish_envelope

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
HOST = {
    "at": 7,
    "id": 1,
    "level_dlevel": 1,
    "level_dnum": 0,
    "move": 40,
    "run": "ab" * 32,
    "variant": 0,
}


class NextUseSafeAdmitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="nyarl-next-use-safe-")
        cls.addClassCleanup(cls.build.cleanup)
        cls.binary = Path(cls.build.name) / "next-use-safe"
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
            str(ROOT / "tests/chaos/next_use_safe.c"),
            str(ROOT / "src/chaos_next_use.c"),
            str(ROOT / "src/chaos_next_use_admission.c"),
            str(ROOT / "src/chaos_next_use_runtime.c"),
            str(ROOT / "src/chaos_next_use_io.c"),
            str(ROOT / "src/chaos_next_use_safe.c"),
            str(ROOT / "src/chaos_protocol.c"),
            str(ROOT / "src/chaos_lua.c"),
            "-Wl,--gc-sections",
            *flags,
            "-lm",
            "-o",
            str(cls.binary),
        ]
        result = subprocess.run(command, capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr.decode())

    def publish(self):
        folder = tempfile.mkdtemp(prefix="nyarl-next-use-safe-run-")
        os.chmod(folder, 0o700)
        publish_envelope(folder, ROW, HOST)
        return folder

    def run_case(
        self,
        folder,
        at_safe=7,
        at_move=40,
        dnum=0,
        dlevel=1,
        run=None,
        polls=2,
        enabled=1,
    ):
        if run is None:
            run = HOST["run"]
        p = subprocess.run(
            [
                str(self.binary),
                folder,
                str(at_safe),
                str(at_move),
                str(dnum),
                str(dlevel),
                run,
                str(polls),
                str(enabled),
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return json.loads(p.stdout)

    def test_admits_once_and_second_poll_is_idle(self):
        row = self.run_case(self.publish())
        self.assertEqual(row["loaded"], 1)
        self.assertEqual(row["admitted"], 1)
        self.assertEqual(row["active"], 1)
        self.assertEqual(row["telegraph"], 1)
        self.assertEqual(row["spent"], 1)
        self.assertEqual(row["second_admitted"], 0)
        self.assertEqual(row["second_telegraph"], 0)
        self.assertEqual(row["second_spent"], 0)

    def test_disabled_does_not_load(self):
        row = self.run_case(self.publish(), enabled=0)
        self.assertEqual(row["loaded"], 0)
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["spent"], 0)

    def test_wrong_run_is_rejected(self):
        row = self.run_case(self.publish(), run="cd" * 32)
        self.assertEqual(row["loaded"], 1)
        self.assertEqual(row["rejected"], 1)
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["spent"], 0)

    def test_wrong_level_is_rejected(self):
        row = self.run_case(self.publish(), dlevel=2)
        self.assertEqual(row["rejected"], 1)
        self.assertEqual(row["admitted"], 0)

    def test_late_schedule_is_rejected(self):
        row = self.run_case(self.publish(), at_safe=8)
        self.assertEqual(row["rejected"], 1)
        self.assertEqual(row["admitted"], 0)

    def test_future_schedule_stays_pending(self):
        row = self.run_case(self.publish(), at_safe=6)
        self.assertEqual(row["pending"], 1)
        self.assertEqual(row["admitted"], 0)
        self.assertEqual(row["spent"], 0)

    def test_stale_origin_is_rejected(self):
        row = self.run_case(self.publish(), at_move=141)
        self.assertEqual(row["rejected"], 1)
        self.assertEqual(row["admitted"], 0)

    def test_tampered_source_cannot_be_admitted(self):
        folder = self.publish()
        path = Path(folder) / "next_use-envelope.json"
        payload = json.loads(path.read_text())
        payload["source"] = payload["source"] + " "
        path.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        os.chmod(path, 0o600)
        row = self.run_case(folder)
        self.assertEqual(row["rejected"], 1)
        self.assertEqual(row["admitted"], 0)


if __name__ == "__main__":
    unittest.main()
