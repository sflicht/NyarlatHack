"""Task 8c: native user-option inspection, atomic failure, invalid admission.

Handwritten sources, not model output. Reuse the one Task 8a visible-derived
route and unmodified no-wizard Game, with no source replacement, state-injecting
wrapper, hidden-map query, launcher, director, seed search or model call. Native
save bytes supply the player-record oracle; they are not full physical-object
or RNG snapshots. Only in-memory oracle copies are corrupted by negative tests.
MAIL selects an owned private mailbox: controlled external input, not game-state
injection or a biff patch. Only the separate mail control deliberately changes it.
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from gameplay_support import ANSI, ROOT, Game
from test_curio_gameplay import DISCOVERY, NOTE
from test_curio_restart_gameplay import assert_record_delta, saved_record, sha
from chaos import curio_continuity as continuity
from chaos.curio_store import install_saved_source, read_candidate, store_candidate

# Admission dry-runs state 0 without committing its returned state. The first
# actual use succeeds, but the entire second intent must fail native validation.
SOURCE = b"""return {name='Offline counter',inspect=function(c) return 'A plain counter with a faulty second stage.' end,apply=function(c)
if c.state==0 then return {text='First stage.',state=1,sanity_delta=-2}
else return {text='Invalid stage must never appear.',state=256,sanity_delta=2} end end}
"""
# Valid UTF-8/Lua and valid authoring envelope, deliberately invalid hook table.
INVALID_SOURCE = b"""return {name='Rejected counter',inspect=function(c) return 'Rejected prose must never appear.' end,apply=17}
"""
INSPECT = b"A plain counter with a faulty second stage."
INVALID_TEXT = b"Invalid stage must never appear."


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class CurioFailureGameplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert (ROOT / ".chaos-build").read_text().strip() == "1"
        cls.artifacts = Path(tempfile.mkdtemp(prefix="curio8c-mail-"))
        print("CURIO8C_ARTIFACTS=" + str(cls.artifacts), flush=True)
        inputs = [
            Path(__file__),
            *[
                ROOT / "tests/chaos" / name
                for name in (
                    "test_curio_gameplay.py",
                    "test_curio_restart_gameplay.py",
                    "gameplay_support.py",
                    "replay_clock.c",
                    "curio_save_layout.c",
                )
            ],
        ]
        cls.protected = (
            inputs
            + sorted((ROOT / "include").glob("*.h"))
            + sorted((ROOT / "src").glob("*.c"))
            + [ROOT / "dnethackdir" / n for n in ("dnethack", "nhdat", "license")]
        )
        cls.hashes = {str(p): sha(p.read_bytes()) for p in cls.protected}
        (cls.artifacts / "protected-before.json").write_text(
            json.dumps(cls.hashes, indent=2)
        )
        for p in inputs:
            shutil.copy2(p, cls.artifacts / p.name)
        cls.clock, layout = cls.artifacts / "clock.so", cls.artifacts / "layout"
        commands = [
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
            [
                "cc",
                "-std=gnu17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-DCHAOS",
                "-DDLB",
                "-isystem" + str(ROOT / "include"),
                str(ROOT / "tests/chaos/curio_save_layout.c"),
                "-o",
                str(layout),
            ],
        ]
        (cls.artifacts / "build-commands.json").write_text(
            json.dumps(commands, indent=2)
        )
        for command in commands:
            result = subprocess.run(command, capture_output=True, timeout=30)
            with (cls.artifacts / "build.log").open("ab") as f:
                f.write(result.stdout + result.stderr)
            assert result.returncode == 0, result.stderr
        output = subprocess.check_output([str(layout)], timeout=5)
        (cls.artifacts / "layout.json").write_bytes(output)
        cls.schema = json.loads(output)

    def setUp(self):
        self.root = self.artifacts / self._testMethodName
        self.root.mkdir(mode=0o700)
        self.mailbox = self.root / "native-mail"
        self.mailbox.touch(mode=0o600, exist_ok=False)
        os.utime(self.mailbox, (1_000_000_000, 1_000_000_000))
        self.mail_before = self.mail_metadata()
        self.mail_expected = self.mail_before
        self.mail_empty_required = True
        self.enterContext(patch.dict(os.environ, {"MAIL": str(self.mailbox)}))
        self.g = Game(
            ROOT / "dnethackdir", self.clock, wizard=False, root=self.root / "session"
        )
        self.addCleanup(self.g.close)
        self.actions, self.snapshots, self.environments = {}, {}, []

    def tearDown(self):
        mail_after = self.mail_metadata()
        (self.root / "native-mail-receipt.json").write_text(
            json.dumps(
                {
                    "purpose": "controlled external input, not game-state injection or biff patch",
                    "empty_required": self.mail_empty_required,
                    "before": self.mail_before,
                    "expected": self.mail_expected,
                    "after": mail_after,
                },
                indent=2,
            )
        )
        self.assertEqual(mail_after, self.mail_expected)
        if self.mail_empty_required:
            self.assertEqual(self.mailbox.read_bytes(), b"")
        after = {str(p): sha(p.read_bytes()) for p in self.protected}
        (self.root / "protected-after.json").write_text(json.dumps(after, indent=2))
        self.assertEqual(after, self.hashes)
        self.assertTrue(all(not s["wizard"] for s in self.g.sessions))
        inputs = b"".join(bytes.fromhex(s) for s in self.g.inputs)
        for forbidden in (b"setsanity", b"levelport", b"\x16"):
            self.assertNotIn(forbidden, inputs)

    def mail_metadata(self):
        info = self.mailbox.stat()
        return {
            "path": str(self.mailbox),
            "device": info.st_dev,
            "inode": info.st_ino,
            "uid": info.st_uid,
            "mode": info.st_mode,
            "size": info.st_size,
            "mtime_ns": info.st_mtime_ns,
            "ctime_ns": info.st_ctime_ns,
            "sha256": sha(self.mailbox.read_bytes()),
        }

    def install(self, source):
        self.source = source
        self.bundles, self.journal = self.root / "bundles", self.root / "journal"
        self.bundles.mkdir(mode=0o700)
        self.journal.mkdir(mode=0o700)
        continuity.create_journal(self.journal)
        self.candidate = store_candidate(
            self.bundles,
            json.dumps({"lua_source": source.decode(), "continuity_note": NOTE}),
        )
        self.assertEqual(self.candidate.candidate_id, sha(source))
        continuity.register(self.journal, self.bundles, self.candidate.candidate_id)
        self.receipt = install_saved_source(
            self.g.run,
            bundle_root=self.bundles,
            candidate_id=self.candidate.candidate_id,
        )
        continuity.bind_run(self.journal, self.candidate.candidate_id, self.g.run)
        self.assertEqual(continuity.prior_notes(self.journal)[0]["status"], "installed")
        self.verify_source()
        self.assertFalse((self.g.run / "events.jsonl").exists())

    def verify_source(self):
        self.assertEqual(
            read_candidate(self.bundles, self.candidate.candidate_id), self.candidate
        )
        self.assertEqual((self.g.run / "curio.lua").read_bytes(), self.source)
        self.assertEqual(
            install_saved_source(
                self.g.run,
                bundle_root=self.bundles,
                candidate_id=self.candidate.candidate_id,
                mode="verify",
            ),
            self.receipt,
        )

    def start(self):
        self.assertTrue(
            os.environ.get("MAIL") == str(self.mailbox),
            "fixture must select private native MAIL before exec",
        )
        offset = len(self.g.raw)
        self.g.start()
        proc = Path(f"/proc/{self.g.pid}")
        env = dict(
            part.split(b"=", 1)
            for part in (proc / "environ").read_bytes().split(b"\0")
            if b"=" in part
        )
        # Allowlist only: never preserve unrelated inherited secrets.
        selected: dict = {
            key: env.get(key.encode(), b"").decode()
            for key in (
                "NYARLATHACK_RUN_DIR",
                "LD_PRELOAD",
                "NETHACKOPTIONS",
                "TZ",
                "MAIL",
            )
        }
        selected["argv"] = [
            a.decode() for a in (proc / "cmdline").read_bytes().split(b"\0") if a
        ]
        selected["pid"] = self.g.pid
        selected["exe_sha256"] = sha((proc / "exe").read_bytes())
        selected["run_dir_present"] = b"NYARLATHACK_RUN_DIR" in env
        self.assertEqual(selected["argv"], ["./dnethack"])
        self.assertEqual(
            selected["exe_sha256"], self.hashes[str(ROOT / "dnethackdir/dnethack")]
        )
        self.assertEqual(selected["LD_PRELOAD"], str(self.clock))
        self.assertEqual(selected["MAIL"], str(self.mailbox))
        self.assertEqual(selected["run_dir_present"], self.g.observe)
        self.assertEqual(
            selected["NYARLATHACK_RUN_DIR"], str(self.g.run) if self.g.observe else ""
        )
        self.environments.append(selected)
        (self.root / "session-env.json").write_text(
            json.dumps(self.environments, indent=2)
        )
        output = bytes(self.g.raw[offset:])
        (self.root / f"startup-{len(self.environments)}.raw").write_bytes(output)
        self.assertNotIn(b"Configuration incompatibility", output)
        if self.snapshots:
            self.assertNotIn(b"An uncanny curio may appear", output)
            self.assertFalse(list((self.g.game / "save").iterdir()))
            last = list(self.snapshots.values())[-1]
            self.assertEqual(self.turn("restored"), last["turn"])

    def response(self, name, command):
        start = len(self.g.raw)
        self.g.more(self.g.send(command))
        raw = bytes(self.g.raw[start:])
        (self.root / (name + ".raw")).write_bytes(raw)
        return ANSI.sub(b"", raw)

    def turn(self, name):
        output = self.response(name + "-redraw", b"\x12")
        values = re.findall(rb"T:(\d+)", output)
        self.assertTrue(values, output)
        return int(values[-1])

    def curio_events(self):
        return [e for e in self.g.events() if e["event"] == "curio"]

    def option_page(self, name):
        start = len(self.g.raw)
        text = self.g.send("O")
        for page in range(1, 13):
            match = re.search(rb"([a-zA-Z]) - item_use_menu\s+\[(true|false)\]", text)
            if match:
                (self.root / (name + ".raw")).write_bytes(self.g.raw[start:])
                return match
            pages = re.search(rb"\((\d+) of (\d+)\)", text)
            assert pages is not None, text
            self.assertEqual(int(pages[1]), page)
            self.assertLess(page, int(pages[2]), "option absent from native menu")
            text = self.g.send(" ")
        self.fail("options paging exceeded bound")

    def direct_inspect(self, name, expected=INSPECT):
        before = self.turn(name + "-before")
        events = self.curio_events()
        # Change only a real, visible player option; no .nethackrc assumption or
        # iflags wrapper. Reopen to prove the selected value actually changed.
        option = self.option_page(name + "-option-before")
        self.assertEqual(option[2], b"true")
        self.g.send(option[1])
        self.response(name + "-option-toggle", "\n")
        self.assertEqual(self.option_page(name + "-option-after")[2], b"false")
        self.g.send(b"\x1b")
        offset = len(self.g.raw)
        self.g.send("i")
        self.assertIn(b"s - an Offline counter", self.g.send(" "))
        text = self.g.send("s")
        # The selection itself describes it: no I command/action submenu.
        self.assertIn(expected, text)
        self.g.more(text)
        raw = bytes(self.g.raw[offset:])
        (self.root / (name + ".raw")).write_bytes(raw)
        for forbidden in (
            b"I - Describe",
            b"a - Apply",
            b"whistle",
            b"This spends one use.",
            b"The curio requests",
            INVALID_TEXT,
        ):
            self.assertNotIn(forbidden, raw)
        self.assertEqual(self.turn(name + "-after"), before)
        self.assertEqual(self.curio_events(), events)
        self.actions[name] = {
            "before": before,
            "after": before,
            "item_use_menu": [True, False],
        }

    def snapshot(self, name, charges, state, sanity, disabled=0, previous=None):
        turn = self.turn(name + "-save")
        self.assertEqual(self.g.save(), 0)
        self.assertIsNone(self.g.pid)
        self.assertIsNone(self.g.fd)
        dest = self.root / name
        dest.mkdir()
        saves = [p for p in (self.g.game / "save").iterdir() if p.is_file()]
        self.assertEqual(len(saves), 1)
        data = saves[0].read_bytes()
        (dest / "native.savefile").write_bytes(data)
        for filename in ("terminal.raw", "inputs.json", "manifest.json"):
            shutil.copy2(self.g.root / filename, dest / filename)
        shutil.copytree(self.g.run, dest / "run")
        owner = (
            self.snapshots["discovered"]["fields"]["owner"] if self.snapshots else None
        )
        record, fields = saved_record(
            self,
            data,
            self.schema,
            charges,
            state,
            owner,
            source=SOURCE,
            name=b"Offline counter",
            disabled=disabled,
        )
        self.assertEqual(fields["sanity"], sanity)
        self.assertEqual(fields["insight"], 0)
        if previous:
            assert_record_delta(
                self,
                self.snapshots[previous]["record"],
                record,
                self.schema,
                charges,
                state,
                disabled=disabled,
            )
        (dest / "record.bin").write_bytes(record)
        (dest / "fields.json").write_text(json.dumps(fields, indent=2))
        self.snapshots[name] = {"record": record, "fields": fields, "turn": turn}
        return data

    def inert_apply(self, name):
        before = self.turn(name + "-before")
        events = self.curio_events()
        output = self.response(name, "as")
        self.assertIn(b"This curio is inert.", output)
        for forbidden in (
            b"The curio requests",
            b"This spends one use.",
            b"First stage.",
            INVALID_TEXT,
            b"whistle",
        ):
            self.assertNotIn(forbidden, output)
        self.assertEqual(self.turn(name + "-after"), before)
        self.assertEqual(self.curio_events(), events)
        self.actions[name] = {"before": before, "after": before}

    def reconcile(self, status):
        self.verify_source()
        events = (self.g.run / "events.jsonl").read_bytes()
        continuity.observe(self.journal, self.candidate.candidate_id)
        notes = continuity.prior_notes(self.journal)
        self.assertEqual(
            notes,
            [
                {
                    "candidate_id": self.candidate.candidate_id,
                    "status": status,
                    "continuity_note": NOTE,
                }
            ],
        )
        self.assertEqual((self.g.run / "events.jsonl").read_bytes(), events)
        return notes, sha(events)

    def test_direct_inspection_runtime_failure_and_disabled_restore(self):
        self.install(SOURCE)
        self.start()
        admitted = self.curio_events()
        self.assertEqual([e["detail"] for e in admitted], ["pre_admitted", "admitted"])
        self.assertEqual([e["sanity"] for e in admitted], [100, 100])
        self.assertEqual([e["spent"] for e in admitted], [0, 1])
        self.assertIn(b"An uncanny curio may appear on a later floor.", self.g.raw)
        for key in DISCOVERY:
            self.g.send(key)
        self.assertIn(b"Dlvl:2", self.response("stairs", ">"))
        self.assertEqual(
            [e["detail"] for e in self.curio_events()],
            ["pre_admitted", "admitted", "placed"],
        )
        self.g.more(self.g.send("y"))
        self.g.send(",")
        self.g.send("i")
        self.assertIn(b"q - a chest", self.g.send(" "))
        self.g.send(b"\x1b")
        self.assertIn(b"You drop a chest", self.g.send("dq"))
        self.assertIn(b"s - an Offline counter", self.g.more(self.g.send("y")))
        self.g.send(",")
        # Dry-run intent at admission did not commit state=1 or spend a use.
        self.snapshot("discovered", 3, 0, 100)
        self.start()
        self.direct_inspect("direct-inspect")
        self.snapshot("inspected", 3, 0, 100, previous="discovered")
        self.assertEqual(
            self.snapshots["discovered"]["record"],
            self.snapshots["inspected"]["record"],
        )
        self.start()
        before = self.turn("first-apply-before")
        output = re.sub(rb"\s+", b" ", self.response("first-apply", "as"))
        warning = (
            b"The curio requests a Sanity change of -2; native limits may reduce it."
        )
        for text in (warning, b"This spends one use.", b"First stage."):
            self.assertEqual(output.count(text), 1, output)
            self.assertLessEqual(output.index(text), output.index(b"First stage."))
        self.assertNotIn(INVALID_TEXT, output)
        self.assertNotIn(b"inert", output)
        self.assertNotIn(b"whistle", output.lower())
        self.assertEqual(self.turn("first-apply-after"), before + 1)
        self.actions["first-apply"] = {"before": before, "after": before + 1}
        self.snapshot("first", 2, 1, 98, previous="inspected")
        self.start()
        self.inert_apply("invalid-apply")
        self.inert_apply("repeat-disabled-apply")
        failed_save = self.snapshot("disabled", 2, 1, 98, disabled=1, previous="first")
        # Exact whole-record delta above permits only disabled=1 here; the
        # charge/state writes reproduce their unchanged values, not a refund.
        applied = [e for e in self.curio_events() if e["detail"].startswith("applied ")]
        self.assertEqual(
            [e["detail"] for e in self.curio_events()],
            ["pre_admitted", "admitted", "placed", "applied requested=-2 actual=-2"],
        )
        self.assertEqual(
            [(e["sanity"], e["spent"], e["turn"]) for e in applied], [(98, 1, before)]
        )
        native_events = (self.g.run / "events.jsonl").read_bytes()
        self.g.observe = False
        self.start()
        self.direct_inspect("disabled-direct-inspect", b"This curio is inert.")
        self.inert_apply("restored-disabled-apply")
        self.snapshot("restored-disabled", 2, 1, 98, disabled=1, previous="disabled")
        self.assertEqual(
            self.snapshots["disabled"]["record"],
            self.snapshots["restored-disabled"]["record"],
        )
        self.assertEqual((self.g.run / "events.jsonl").read_bytes(), native_events)
        self.assertEqual([s["observe"] for s in self.g.sessions], [True] * 4 + [False])
        self.assertEqual((self.g.run / "curio-used.lua").read_bytes(), SOURCE)
        self.assertFalse(list(self.g.game.rglob("*.lua")))
        notes, event_hash = self.reconcile("placed")
        # Historical placed is deliberately NOT a claim of executable health.
        # Negative controls only alter copies read by the oracle, never native input.
        fields = self.snapshots["disabled"]["fields"]
        offsets = {
            name: fields["record_offset"] + self.schema["record"][name]["offset"]
            for name in ("disabled", "charges", "state", "owner", "source")
        }
        for name, offset in offsets.items():
            changed = bytearray(failed_save)
            changed[offset] ^= 1
            with self.subTest(negative=name), self.assertRaises(AssertionError):
                saved_record(
                    self,
                    bytes(changed),
                    self.schema,
                    2,
                    1,
                    fields["owner"],
                    source=SOURCE,
                    name=b"Offline counter",
                    disabled=1,
                )
        changed = bytearray(self.snapshots["disabled"]["record"])
        changed[-1] ^= 1
        with self.assertRaisesRegex(
            AssertionError, "unexpected owned-record byte change"
        ):
            assert_record_delta(
                self,
                self.snapshots["first"]["record"],
                bytes(changed),
                self.schema,
                2,
                1,
                disabled=1,
            )
        (self.root / "evidence.json").write_text(
            json.dumps(
                {
                    "candidate_id": self.candidate.candidate_id,
                    "authorship": NOTE,
                    "path": "standalone bundle install/verify + unmodified direct native exec",
                    "snapshots": {
                        n: {"fields": s["fields"], "turn": s["turn"]}
                        for n, s in self.snapshots.items()
                    },
                    "actions": self.actions,
                    "applied": applied,
                    "notes": notes,
                    "native_events_sha256": event_hash,
                    "negative_controls": [*offsets, "unexpected_record_byte"],
                    "limits": [
                        "checkpoint between valid and invalid use; no same-process record snapshot",
                        "player-record equality, not full physical object or RNG snapshots",
                        "no whistle text/fallback turn, not nearby monster wake-state instrumentation",
                        "historical placed continuity does not encode executable health",
                        "launcher, both builds, full suite/reviews and live Task 9 remain",
                    ],
                },
                indent=2,
            )
        )

    def test_private_native_mail_arrival_control(self):
        # No curio installed. Exercise unchanged src/mail.c using only synthetic
        # bytes in this test's mailbox; never read a scroll or real host mail.
        self.start()
        self.assertEqual(self.turn("mail-start"), 1)
        for step in range(12):
            self.response(f"mail-empty-rest-{step}", ".")
        self.assertEqual(self.mail_metadata(), self.mail_before)
        prefix = bytes(self.g.raw)
        for marker in (b"mail for you", b"stamped scroll"):
            self.assertNotIn(marker, prefix)
        (self.root / "mail-before-arrival.raw").write_bytes(prefix)
        (self.root / "mail-before-arrival-inputs.json").write_text(
            json.dumps(self.g.inputs)
        )
        before_turn = self.turn("mail-before-arrival")
        self.assertEqual(before_turn, 13)
        self.mail_empty_required = False  # Explicit exception ONLY in this control.
        self.mailbox.write_bytes(b"Harmless offline native-mail fixture.\n")
        next_mtime = self.mail_before["mtime_ns"] + 1_000_000_000
        os.utime(self.mailbox, ns=(next_mtime, next_mtime))
        self.mail_expected = self.mail_metadata()
        offset = len(self.g.raw)
        # Native ckmailstatus polls every ten moves, not elapsed wall time.
        # Fixed bounded ordinary commands, no retry/seed/clock changes.
        for step in range(12):
            self.response(f"mail-arrival-rest-{step}", ".")
        delivered = bytes(self.g.raw[offset:])
        (self.root / "mail-arrival.raw").write_bytes(delivered)
        self.assertEqual(delivered.count(b"I have some mail for you"), 1)
        self.assertIn(b"stamped scroll", delivered)
        self.assertEqual(self.turn("mail-after-arrival"), 25)
        self.assertEqual(self.curio_events(), [])
        self.assertEqual(self.g.quit(), 0)
        self.assertIsNone(self.g.pid)
        self.assertIsNone(self.g.fd)
        (self.root / "evidence.json").write_text(
            json.dumps(
                {
                    "control": "native-mail external-input causality, NOT curio-engine RED",
                    "prefix_sha256": sha(prefix),
                    "arrival_sha256": sha(delivered),
                    "rest_commands": [12, 12],
                    "arrival_boundary_turn": before_turn,
                    "exit": self.g.exitcode,
                    "scroll_read": False,
                },
                indent=2,
            )
        )

    def test_invalid_hook_table_rejected_before_admission(self):
        self.install(INVALID_SOURCE)
        self.start()
        events = self.g.events()
        self.assertEqual((events[0]["event"], events[0]["detail"]), ("session", "new"))
        rejected = self.curio_events()
        self.assertEqual([e["detail"] for e in rejected], ["rejected"])
        self.assertEqual(
            [(e["sanity"], e["spent"], e["turn"]) for e in rejected], [(100, 0, 1)]
        )
        self.assertTrue(all(e["spent"] == 0 for e in events))
        self.assertFalse((self.g.run / "curio-used.lua").exists())
        for text in (
            b"An uncanny curio may appear",
            b"Rejected counter",
            b"Rejected prose must never appear.",
            b"The curio requests",
        ):
            self.assertNotIn(text, self.g.raw)
        self.assertEqual(self.turn("rejected-start"), 1)
        self.assertEqual(self.g.quit(), 0)
        self.assertEqual([e["detail"] for e in self.curio_events()], ["rejected"])
        self.assertTrue(all(e["spent"] == 0 for e in self.g.events()))
        self.assertFalse((self.g.run / "curio-used.lua").exists())
        notes, event_hash = self.reconcile("rejected")
        (self.root / "evidence.json").write_text(
            json.dumps(
                {
                    "candidate_id": self.candidate.candidate_id,
                    "authorship": NOTE,
                    "notes": notes,
                    "rejected": rejected,
                    "native_events_sha256": event_hash,
                    "source_preserved": True,
                    "curio_used_exists": False,
                    "limits": [
                        "native event rejection + absent used-source; no rejected player-record decode",
                        "no source replacement or later-floor rejection-latch/nonreplacement test",
                        "one malformed hook-table case; resource/malformed intent matrix remains linked-unit coverage",
                        "direct native exec, not launcher acceptance",
                    ],
                },
                indent=2,
            )
        )
