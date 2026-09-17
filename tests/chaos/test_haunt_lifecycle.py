"""Real linked lifecycle: transport admission and ongoing rules are distinct."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from native_rng import controlled_rng_objects

ROOT = Path(__file__).resolve().parents[2]

# Captured before development comparison; never regenerated from new caller.
BASELINE_SUCCESS = b'{"v":1,"seq":1,"turn":10,"safe":0,"event":"session","phase":"result","detail":"restore","sanity":100,"insight":0,"budget":2,"spent":0,"reserved":0,"last_id":0,"vitals":{"hp":20,"hp_max":20,"power":0,"power_max":0}}\n{"v":1,"seq":2,"turn":10,"safe":0,"event":"haunting","phase":"result","detail":"pre_admitted","sanity":100,"insight":0,"budget":2,"spent":0,"reserved":0,"last_id":0,"vitals":{"hp":20,"hp_max":20,"power":0,"power_max":0}}\n{"v":1,"seq":3,"turn":10,"safe":0,"event":"haunting","phase":"result","detail":"accepted","sanity":100,"insight":0,"budget":0,"spent":2,"reserved":0,"last_id":0,"vitals":{"hp":20,"hp_max":20,"power":0,"power_max":0}}\n'


# Independent old-caller capture: issue34/haunt-baseline6/hooks/{events.jsonl,stdout}.
# These are literal historical bytes, not expectations derived from this caller.
BASELINE_HOOKS = (
    b'{"v":1,"seq":1,"turn":10,"safe":0,"event":"session","phase":"result","detail":"restore","sanity":100,"insight":0,"budget":2,"spent":0,"reserved":0,"last_id":0,"vitals":{"hp":20,"hp_max":20,"power":0,"power_max":0}}\n'
    b'{"v":1,"seq":2,"turn":10,"safe":0,"event":"haunting","phase":"result","detail":"pre_admitted","sanity":100,"insight":0,"budget":2,"spent":0,"reserved":0,"last_id":0,"vitals":{"hp":20,"hp_max":20,"power":0,"power_max":0}}\n'
    b'{"v":1,"seq":3,"turn":10,"safe":0,"event":"read","phase":"attempt","detail":"","sanity":100,"insight":0,"budget":2,"spent":0,"reserved":0,"last_id":0,"vitals":{"hp":20,"hp_max":20,"power":0,"power_max":0}}\n'
    b'{"v":1,"seq":4,"turn":10,"safe":0,"event":"read","phase":"attempt","detail":"","sanity":100,"insight":0,"budget":2,"spent":0,"reserved":0,"last_id":0,"vitals":{"hp":20,"hp_max":20,"power":0,"power_max":0}}\n'
    b'{"v":1,"seq":5,"turn":10,"safe":0,"event":"haunting","phase":"result","detail":"accepted","sanity":100,"insight":0,"budget":0,"spent":2,"reserved":0,"last_id":0,"vitals":{"hp":20,"hp_max":20,"power":0,"power_max":0}}\n'
)
BASELINE_HOOKS_STDOUT = (
    "mode=hooks spent=2 spawns=1 trials=1 rng_count=10 next_draw=99824 seq=5\n"
)


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class HauntLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Keep per-case stdout/stderr and diagnostics even when an assertion fails.
        cls.root = Path(tempfile.mkdtemp(prefix="nyarl-haunt-lifecycle-"))
        print("HAUNT_LIFECYCLE_ARTIFACTS=" + str(cls.root), flush=True)
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
        cls.exe = cls.root / "lifecycle"
        cls.link(cls.exe, cls.objects)

    @classmethod
    def link(cls, exe, objects):
        command = [
            "cc",
            "-g",
            "-DCHAOS",
            "-I" + str(ROOT / "include"),
            str(ROOT / "tests/chaos/haunt_lifecycle.c"),
            *map(str, objects),
            *[
                f"-Wl,--wrap={s}"
                for s in (
                    "chaos_spend_non_effect",
                    "makemon",
                    "pline",
                    "paniclog",
                    "chaos_shadow_run",
                    "openat",
                    "close",
                    "write",
                )
            ],
            "-lncursesw",
            "-ltinfo",
            "-lm",
            *subprocess.check_output(
                ["pkg-config", "--libs", "lua5.4"], text=True
            ).split(),
            "-o",
            str(exe),
        ]
        (cls.root / (exe.name + "-link.json")).write_text(json.dumps(command))
        subprocess.run(command, check=True, timeout=45)

    def run_native(self, case, args, *, run=None, exe=None):
        diagnostics = case / "diagnostics"
        diagnostics.mkdir(mode=0o700)
        env = dict(os.environ)
        env.pop("NYARLATHACK_RUN_DIR", None)
        env["NYARLATHACK_ECHOES"] = "0"
        if run is not None:
            env["NYARLATHACK_RUN_DIR"] = str(run)
        command = [str(exe or self.exe), *args]
        (case / "command.json").write_text(
            json.dumps({"argv": command, "cwd": str(diagnostics), "run": str(run)})
        )
        # Files are opened before launching, so even timeout output is retained.
        with (case / "stdout").open("w") as out, (case / "stderr").open("w") as err:
            p = subprocess.run(
                command, cwd=diagnostics, env=env, stdout=out, stderr=err, timeout=10
            )
        (case / "returncode").write_text(str(p.returncode) + "\n")
        p.stdout = (case / "stdout").read_text()
        p.stderr = (case / "stderr").read_text()
        return p

    def assert_clean(self, p, case):
        self.assertEqual(p.returncode, 0, f"{case}\n{p.stdout}{p.stderr}")
        self.assertEqual(p.stderr, "", f"unexpected diagnostic: {case}")
        self.assertFalse(
            (case / "diagnostics/paniclog").exists(), f"unexpected paniclog: {case}"
        )

    def check(self, failed_log):
        case = self.root / ("failed-log" if failed_log else "absent-run-dir")
        case.mkdir(mode=0o700)
        args = []
        run = None
        if failed_log:
            run = case / "run"
            run.mkdir(mode=0o700)
            args.append(str(run / "events.jsonl"))
        result = self.run_native(case, args, run=run)
        self.assert_clean(result, case)
        self.assertIn(
            "history maintained; level expiry permanent; deadline maintained",
            result.stdout,
        )

    def test_caller_accounting_matrix(self):
        # Controlled trial outcomes, NOT actual shadow acceptance.
        for mode in (
            "valid",
            "hooks",
            "spawnfail",
            "finalfail",
            "source",
            "absent",
            "usedfail",
            "usedwrite",
            "reportfail",
            "reportwrite",
            "trialfail",
            "rejected",
            "prefail",
            "budget",
            "invalid",
        ):
            with self.subTest(mode=mode):
                run = self.root / mode
                run.mkdir(mode=0o700)
                if mode != "absent":
                    source = run / "haunting.lua"
                    source.write_bytes(
                        b""
                        if mode == "source"
                        else b"return function(c) return {dx=0,dy=0,state=c.state} end\n"
                    )
                    source.chmod(0o600)
                p = self.run_native(run, ["--admission", mode], run=run)
                self.assert_clean(p, run)
                # Independently measured on unchanged old native core.
                expected = (
                    "rng_count=10 next_draw=99824"
                    if mode in ("valid", "hooks", "finalfail")
                    else "rng_count=0 next_draw=59393"
                )
                self.assertIn(expected, p.stdout)
                if mode == "valid":
                    self.assertEqual(
                        (run / "events.jsonl").read_bytes(), BASELINE_SUCCESS
                    )
                if mode == "hooks":
                    self.assert_hooks(run, p.stdout)

    def assert_hooks(self, run, stdout):
        self.assertEqual(
            (run / "events.jsonl").read_bytes(),
            BASELINE_HOOKS,
            "hook event sequence differs from independent old-caller capture",
        )
        self.assertEqual(stdout, BASELINE_HOOKS_STDOUT)

    def test_whole_state_publication_negative_control(self):
        # Compile a separate defective caller; never edit the selected source or
        # overwrite its object. The ordinary C checks/RNG still pass this mutant.
        original = ROOT / "src/chaos_haunt.c"
        source = original.read_text()
        old = "u.chaos.spent=charged.spent;"
        self.assertEqual(source.count(old), 1, "publication mutation seam changed")
        mutant = self.root / "whole-state-publication.c"
        mutant.write_text(source.replace(old, "u.chaos=charged;"))
        obj = self.root / "whole-state-publication.o"
        command = [
            "cc",
            "-g",
            "-DCHAOS",
            "-DDLB",
            "-std=gnu17",
            "-I" + str(ROOT / "include"),
            "-c",
            str(mutant),
            "-o",
            str(obj),
        ]
        (self.root / "mutant-compile.json").write_text(json.dumps(command))
        subprocess.run(command, check=True, timeout=45)
        exe = self.root / "whole-state-publication"
        self.assertEqual(sum(p.name == "chaos_haunt.o" for p in self.objects), 1)
        self.link(exe, [obj if p.name == "chaos_haunt.o" else p for p in self.objects])
        run = self.root / "rewind-hooks"
        run.mkdir(mode=0o700)
        (run / "haunting.lua").write_text(
            "return function(c) return {dx=0,dy=0,state=c.state} end\n"
        )
        (run / "haunting.lua").chmod(0o600)
        p = self.run_native(run, ["--admission", "hooks"], run=run, exe=exe)
        self.assert_clean(p, run)
        rows = [
            json.loads(line)
            for line in (run / "events.jsonl").read_bytes().splitlines()
        ]
        self.assertEqual([row["seq"] for row in rows], [1, 2, 3, 4, 3])
        self.assertEqual(rows[-1]["detail"], "accepted")
        self.assertIn("rng_count=10 next_draw=99824 seq=3", p.stdout)
        with self.assertRaisesRegex(AssertionError, "hook event sequence") as caught:
            self.assert_hooks(run, p.stdout)
        (run / "oracle-failure.txt").write_text(str(caught.exception))
        self.assertEqual(original.read_text(), source)

    def test_engine_diagnostic_negative_controls(self):
        # The first probe calls real impossible(), not the wrapper directly.
        for kind in ("impossible", "paniclog"):
            with self.subTest(kind=kind):
                case = self.root / ("diagnostic-" + kind)
                case.mkdir(mode=0o700)
                p = self.run_native(case, ["--diagnostic-" + kind])
                self.assertEqual(p.returncode, 86, f"{case}\n{p.stdout}{p.stderr}")
                reason = "haunt lifecycle diagnostic negative control: " + kind
                self.assertIn(
                    "unexpected engine diagnostic: " + kind + ": " + reason, p.stderr
                )
                self.assertIn(reason, (case / "diagnostics/paniclog").read_text())
                self.assertNotIn("diagnostic escaped", p.stdout)

    def test_absent_run_directory_keeps_lifecycle(self):
        self.check(False)

    def test_failed_event_log_keeps_lifecycle(self):
        self.check(True)
