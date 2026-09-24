"""Real W publication and autonomous ending journals; controlled, not ordinary."""

import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import test_next_use_dogmove as native
import test_next_use_journal as journal_fixture
from chaos.next_use_envelope import engine_run_hex, publish_envelope
from chaos.next_use_journal import JournalError, read_journal

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class NextUseWhistleJournalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        native.NextUseDogMoveTests.setUpClass()
        base = native.NextUseDogMoveTests
        cls.build = base.root
        cls.exe = cls.build / "journal-w-native"
        subprocess.run(
            [
                "cc",
                "-g",
                "-DCHAOS",
                "-I" + str(ROOT / "include"),
                str(ROOT / "tests/chaos/next_use_journal_w_native.c"),
                *map(str, base.objects),
                "-lncursesw",
                "-ltinfo",
                "-lm",
                *subprocess.check_output(
                    ["pkg-config", "--libs", "lua5.4"], text=True
                ).split(),
                "-o",
                str(cls.exe),
            ],
            check=True,
            timeout=45,
        )

    @classmethod
    def tearDownClass(cls):
        for path in cls.build.iterdir():
            if path.is_file() and (
                path.suffix == ".o" or path.name in ("dogmove", "journal-w-native")
            ):
                path.unlink()

    def run_native(self, blocked=False):
        folder = Path(tempfile.mkdtemp(prefix="nyarl-journal-w-run-"))
        publish_envelope(
            folder, native.ROW, dict(native.HOST, run=engine_run_hex(folder))
        )
        original = (folder / "next_use-envelope.json").read_bytes()
        env = dict(os.environ, TERM="xterm", COLUMNS="80", LINES="24")
        env.pop("JOURNAL_W_BLOCK", None)
        if blocked:
            env["JOURNAL_W_BLOCK"] = "1"
        result = subprocess.run(
            [str(self.exe), "admit", str(folder)],
            cwd=folder,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        (folder / "native.log").write_text(result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        physical = json.loads((folder / "result.json").read_text())
        status = json.loads((folder / "journal-status.json").read_text())
        self.assertEqual((physical["displaced"], physical["delivered"]), (1, 1))
        self.assertNotEqual(
            (physical["ox"], physical["oy"]), (physical["mx"], physical["my"])
        )
        self.assertEqual(
            (physical["public"], physical["public2"], status["witnessed"]),
            (int(not blocked),) * 3,
        )
        self.assertEqual(
            (
                status["phase"],
                status["termination_emitted"],
                status["spent"],
                status["incomplete"],
            ),
            (4, 1, 1, 0),
        )
        self.assertEqual((folder / "next_use-envelope.json").read_bytes(), original)
        print("JOURNAL_W_ARTIFACT=" + str(folder), flush=True)
        return folder, status

    def check_ending(self, blocked):
        folder, status = self.run_native(blocked)
        path = folder / "next_use-journal.jsonl"
        self.assertEqual(read_journal(path)["status"], "structurally_complete")
        capture = {
            key: status[key]
            for key in (
                "sink_connected",
                "incomplete",
                "transaction_open",
                "acknowledged_cursor",
            )
        }
        trace = read_journal(path, capture_status=capture)
        self.assertEqual(trace["status"], "acknowledged_complete")
        transitions = [r["data"] for r in trace["records"] if r["kind"] == "transition"]
        self.assertEqual(len(transitions), status["acknowledged_cursor"])
        endings = [
            p
            for t in transitions
            for p in t["private_records"]
            if p["kind"] == 4 and p["data"]["outcome"] in (4, 5)
        ]
        self.assertEqual(len(endings), 1)
        self.assertEqual(endings[0]["data"]["root"], 0)
        self.assertEqual(endings[0]["data"]["outcome"], 5 if blocked else 4)
        self.assertEqual(
            endings[0]["at_move"], endings[0]["data"]["activation_monstermoves"] + 10
        )
        public = [p for t in transitions for p in t["public_records"]]
        self.assertEqual(len(public), int(not blocked))
        self.assertEqual(trace["records"][-1]["kind"], "end")

    def test_published_whistle_and_zero_root_window_end(self):
        self.check_ending(False)

    def test_unpublished_delivery_and_zero_root_window_end(self):
        self.check_ending(True)

    def test_rehashed_native_witness_and_ending_tampering_rejected(self):
        folder, _ = self.run_native()
        rows = [
            json.loads(line)
            for line in (folder / "next_use-journal.jsonl").read_text().splitlines()
        ]
        witness_index = next(
            i
            for i, r in enumerate(rows)
            if r["payload"]["kind"] == "transition"
            and r["payload"]["data"]["public_count"]
        )
        ending_index = next(
            i
            for i, r in enumerate(rows)
            if r["payload"]["kind"] == "transition"
            and any(
                p["kind"] == 4 and p["data"]["outcome"] == 4
                for p in r["payload"]["data"]["private_records"]
            )
        )
        for field in (
            "published",
            "manifestation_delivered",
            "displaced",
            "pre_public",
            "m_id",
            "notice_seq",
            "end_seq",
            "witnessed",
            "public_root",
            "ending_outcome",
            "early_ending",
        ):
            with self.subTest(field=field):
                bad = copy.deepcopy(rows)
                t = bad[witness_index]["payload"]["data"]
                if field in ("ending_outcome", "early_ending"):
                    t = bad[ending_index]["payload"]["data"]
                    if field == "early_ending":
                        t["at_move"] -= 1
                        for p in t["private_records"]:
                            p["at_move"] = t["at_move"]
                    else:
                        next(p for p in t["private_records"] if p["kind"] == 4)["data"][
                            "outcome"
                        ] = 5
                elif field == "public_root":
                    # Preserve valid ordering, but break the native binding.
                    for key in ("root", "notice_seq", "end_seq"):
                        t["public_records"][0][key] += 100
                elif field == "witnessed":
                    t["post"]["witnessed"] = 0
                elif field in ("m_id", "notice_seq", "end_seq"):
                    t[field] += 1
                else:
                    t[field] = 0
                # Explicitly corrupted copies, never replacements for native evidence.
                target = journal_fixture.NextUseJournalTests.rehashed(
                    folder / ("tampered-" + field + ".jsonl"), bad
                )
                with self.assertRaises(JournalError):
                    read_journal(target)
        self.assertEqual(
            read_journal(folder / "next_use-journal.jsonl")["status"],
            "structurally_complete",
        )
