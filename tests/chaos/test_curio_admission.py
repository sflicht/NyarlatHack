"""Task 3a only: exact-source admission; actual linked engine IO and Lua."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from chaos.protocol import parse_event
from chaos.director import State
from test_director import event
from gameplay_support import Game, ROOT

SOURCE = b"""-- exact observed bytes\nreturn {name="Exact counter",inspect=function(c)
if c.charges~=3 or c.state~=0 or c.sanity~=100 then error("context") end
return "Quiet." end,apply=function(c)
return {text="Still quiet.",state=255,sanity_delta=-2} end}\n"""


class CurioProtocolTests(unittest.TestCase):
    def test_generic_curio_events_no_model_detail(self):
        for detail in ("pre_admitted", "admitted", "rejected", "expired"):
            e = parse_event(json.dumps(event(event="curio", detail=detail)).encode())
            state = State()
            state.ingest(e)
            self.assertNotIn("detail", state.summary())
        with self.assertRaises(ValueError):
            parse_event(json.dumps(event(event="curio_other")).encode())


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class CurioAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert (ROOT / ".chaos-build").read_text().strip() == "1"
        cls.artifacts = Path(tempfile.mkdtemp(prefix="nyarl-curio-admission-"))
        print("CURIO_ADMISSION_ARTIFACTS=" + str(cls.artifacts), flush=True)
        subprocess.run(
            [
                "objcopy",
                "--redefine-sym",
                "main=original_game_main",
                str(ROOT / "sys/unix/unixmain.o"),
                str(cls.artifacts / "unixmain.o"),
            ],
            check=True,
        )
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
        cls.exe = cls.artifacts / "curio-admission"
        command = [
            "cc",
            "-g",
            "-DCHAOS",
            "-I" + str(ROOT / "include"),
            str(ROOT / "tests/chaos/curio_admission.c"),
            *map(str, objects),
            *[
                f"-Wl,--wrap={s}"
                for s in ("write", "fsync", "openat", "close", "pline")
            ],
            "-lncursesw",
            "-ltinfo",
            "-lm",
            *subprocess.check_output(
                ["pkg-config", "--libs", "lua5.4"], text=True
            ).split(),
            "-o",
            str(cls.exe),
        ]
        (cls.artifacts / "build-command.txt").write_text(repr(command))
        subprocess.run(command, check=True, timeout=45)

    def run_case(
        self, mode="valid", expected=2, source: bytes | None = SOURCE, setup=None
    ):
        run = self.artifacts / (mode + "-" + str(len(list(self.artifacts.iterdir()))))
        run.mkdir(mode=0o700)
        if source is not None:
            (run / "curio.lua").write_bytes(source)
            (run / "curio.lua").chmod(0o600)
        if setup:
            setup(run)
        command = [str(self.exe), mode, str(expected)]
        (run / "command.txt").write_text(repr(command))
        p = subprocess.run(
            command,
            env={**os.environ, "NYARLATHACK_RUN_DIR": str(run)},
            capture_output=True,
            text=True,
            timeout=10,
        )
        (run / "native.txt").write_text(p.stdout + p.stderr)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        events = [
            parse_event(line)
            for line in (run / "events.jsonl").read_bytes().splitlines()
        ]
        if expected == 2:
            self.assertEqual((run / "curio-used.lua").read_bytes(), source)
            self.assertEqual((run / "curio-used.lua").stat().st_mode & 0o777, 0o600)
            details = [e["detail"] for e in events if e["event"] == "curio"]
            self.assertIn("pre_admitted", details)
            if mode != "finalfail":
                self.assertIn("admitted", details)
            self.assertNotIn("Exact counter", (run / "events.jsonl").read_text())
        return run

    def test_real_normal_game_preinstalled_source(self):
        clock = self.artifacts / "clock.so"
        subprocess.run(
            [
                "cc",
                "-shared",
                "-fPIC",
                str(ROOT / "tests/chaos/replay_clock.c"),
                "-ldl",
                "-o",
                str(clock),
            ],
            check=True,
        )
        g = Game(
            ROOT / "dnethackdir",
            clock,
            wizard=False,
            root=self.artifacts / "normal-start",
        )
        self.addCleanup(g.close)
        (g.run / "curio.lua").write_bytes(SOURCE)
        (g.run / "curio.lua").chmod(0o600)
        g.start()
        records = [e for e in g.events() if e["event"] == "curio"]
        self.assertEqual([e["detail"] for e in records], ["pre_admitted", "admitted"])
        self.assertEqual(
            [(e["safe"], e["spent"], e["sanity"]) for e in records],
            [(1, 0, 100), (1, 1, 100)],
        )
        self.assertEqual((g.run / "curio-used.lua").read_bytes(), SOURCE)
        self.assertIn(b"curio may appear", g.raw)
        self.assertEqual(g.quit(), 0)

    def test_legacy_ack_schedule_unchanged(self):
        request = dict(
            v=1, id=1, mutation="ambient", value=1, duration=0, telegraph=1, at=1
        )
        run = self.run_case(
            "legacy",
            setup=lambda r: (r / "whisper.json").write_text(json.dumps(request)),
        )
        events = [
            parse_event(line)
            for line in (run / "events.jsonl").read_bytes().splitlines()
        ]
        acks = [e for e in events if e["event"] == "ack"]
        self.assertEqual(
            [(e["id"], e["safe"], e["status"]) for e in acks],
            [(1, 1, "accepted"), (1, 2, "rejected")],
        )
        journal = [
            json.loads(line)
            for line in (run / "whispers.jsonl").read_bytes().splitlines()
        ]
        self.assertEqual([(e["id"], e["safe"]) for e in journal], [(1, 1)])

    def test_valid_exact_bytes_first_safe(self):
        self.run_case()

    def test_unicode_comment_preserves_exact_source(self):
        self.run_case(source=b"-- caf\xc3\xa9\n" + SOURCE)

    def test_formfeed_whitespace_preserves_exact_source(self):
        self.run_case(source=b"\f" + SOURCE)

    def test_control_comment_preserves_exact_source(self):
        self.run_case(source=SOURCE + b"--\x01")

    def test_unicode_comment_does_not_relax_display_validation(self):
        source = b"-- caf\xc3\xa9\n" + SOURCE
        for original in (b"Exact counter", b"Quiet.", b"Still quiet."):
            for invalid in (b"\xc3\xa9", b"\\027"):
                with self.subTest(original=original, invalid=invalid):
                    self.run_case("invalid", 1, source.replace(original, invalid))

    def test_source_validation(self):
        for src in (
            b"",
            b"return {}",
            SOURCE + b" " * 4097,
            SOURCE + b"\0",
            SOURCE + b"\x01",
            SOURCE.replace(b'return "Quiet."', b'return "\\027"'),
            SOURCE.replace(b"state=255", b"state=256"),
        ):
            with self.subTest(src=src[:30]):
                self.run_case("invalid", 1, src)
        self.run_case("bounded", 2, SOURCE + b" " * (4096 - len(SOURCE)))

    def test_absent_and_eligibility(self):
        self.run_case("absent", 0, None)
        for mode in (
            "branch",
            "asleep",
            "busy",
            "dead",
            "gameover",
            "budget",
            "noadvance",
            "transportfail",
        ):
            with self.subTest(mode=mode):
                self.run_case(mode, 0)
        self.run_case("level2", 2)
        self.run_case("level3", 4)

    def test_unsafe_files(self):
        self.run_case("permissions", 1, setup=lambda r: (r / "curio.lua").chmod(0o644))
        self.run_case("execute", 1, setup=lambda r: (r / "curio.lua").chmod(0o700))
        self.run_case(
            "symlink", 1, None, lambda r: (r / "curio.lua").symlink_to("/dev/null")
        )
        self.run_case("fifo", 1, None, lambda r: os.mkfifo(r / "curio.lua", 0o600))
        self.run_case(
            "hardlink", 1, setup=lambda r: os.link(r / "curio.lua", r / "other")
        )

    def test_evidence_fail_closed(self):
        run = self.run_case(
            "conflict",
            1,
            setup=lambda r: (r / "curio-used.lua").write_bytes(b"old evidence"),
        )
        self.assertEqual((run / "curio-used.lua").read_bytes(), b"old evidence")
        for mode in ("writefail", "fsyncfail", "dirsyncfail", "prefail"):
            with self.subTest(mode=mode):
                run = self.run_case(mode, 1)
                self.assertTrue((run / "curio-used.lua").exists())
        self.run_case("shortwrite")
        self.run_case("finalfail")
