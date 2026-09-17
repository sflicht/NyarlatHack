"""Executable Lua sandbox tests; no C/game stubs stand in for the interpreter."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class LuaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="nyarl-lua-")
        cls.exe = Path(cls.tmp.name) / "lua-test"
        if (ROOT / "src/chaos_lua.c").exists():
            flags = subprocess.check_output(
                ["pkg-config", "--cflags", "--libs", "lua5.4"], text=True
            ).split()
            subprocess.run(
                [
                    "cc",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-std=c99",
                    "-I" + str(ROOT / "include"),
                    str(ROOT / "src/chaos_lua.c"),
                    str(ROOT / "tests/chaos/lua_harness.c"),
                    *flags,
                    "-o",
                    str(cls.exe),
                ],
                check=True,
                timeout=30,
            )
            cls.whitebox = Path(cls.tmp.name) / "lua-whitebox"
            subprocess.run(
                [
                    "cc",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-std=c99",
                    "-DLUA_SANDBOX_WHITEBOX",
                    "-I" + str(ROOT / "include"),
                    str(ROOT / "tests/chaos/lua_harness.c"),
                    *flags,
                    "-o",
                    str(cls.whitebox),
                ],
                check=True,
                timeout=30,
            )

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_script(self, source, mode="normal"):
        self.assertTrue(self.exe.exists(), "Lua runtime is missing")
        p = subprocess.run(
            [str(self.exe), mode],
            input=source.encode() if isinstance(source, str) else source,
            capture_output=True,
            timeout=3,
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        result = json.loads(p.stdout)
        if os.environ.get("LUA_ISOLATION_RECEIPT"):
            with open(os.environ["LUA_ISOLATION_RECEIPT"], "a") as receipt:
                receipt.write(
                    json.dumps(
                        {
                            "mode": mode,
                            "source_hex": (
                                source.encode() if isinstance(source, str) else source
                            ).hex(),
                            "result": result,
                        }
                    )
                    + "\n"
                )
        return result

    def test_shared_lifecycle_and_protected_setup(self):
        for mode in ("normal", "setup-oom"):
            with self.subTest(mode=mode):
                p = subprocess.run(
                    [str(self.whitebox), mode], capture_output=True, timeout=3
                )
                self.assertEqual(p.returncode, 0, p.stderr)
                r = json.loads(p.stdout)
                self.assertEqual(r["bad"], 0, r)
                self.assertEqual(r["clean"], 1, r)
                for key in ("states", "closes", "hooks", "calls"):
                    self.assertEqual(r[key], 4, r)
                # Entry stack growth can fail before the bootstrap reaches parsing.
                if mode == "normal":
                    self.assertEqual(r["loads"], 4, r)
                else:
                    self.assertIn(r["loads"], range(5), r)
                self.assertEqual(r["refused"] > 0, mode == "setup-oom", r)

    def resource_case(self, *args, source=""):
        p = subprocess.run(
            [str(self.whitebox), *args],
            input=source.encode(),
            capture_output=True,
            timeout=3,
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        r = json.loads(p.stdout)

        if os.environ.get("LUA_RESOURCE_RECEIPT"):
            with open(os.environ["LUA_RESOURCE_RECEIPT"], "a") as receipt:
                receipt.write(
                    json.dumps({"args": args, "source": source, "result": r}) + "\n"
                )
        return r

    def test_allocator_accounting(self):
        r = self.resource_case("allocator")
        self.assertEqual(r["checks"], 19, r)
        self.assertEqual(r["bad"], 0, r)
        self.assertEqual(r["used"], 0, r)

    def test_resource_stages(self):
        for op in range(4):
            for stage in ("init", "parser", "diagnostic", "context", "history"):
                if (stage == "context" and op == 1) or (stage == "history" and op != 0):
                    continue
                with self.subTest(op=op, stage=stage):
                    r = self.resource_case("resource", str(op), stage)
                    self.assertEqual(r["status"], 2, r)
                    self.assertGreater(r["refused"], 0, r)
                    self.assertGreater(r["stage_refused"], 0, r)
                    if stage != "init":
                        self.assertGreaterEqual(r["stage_refused"], 2, r)
                    self.assertEqual(r["bad"], 0, r)
                    self.assertEqual(r["clean"], 1, r)
                    self.assertEqual(r["states"], r["closes"], r)
                    self.assertEqual(r["states"], 0 if stage == "init" else 1, r)
                    self.assertEqual(r["used"], 0, r)
                    self.assertEqual(r["recovery"], 0, r)
                    self.assertEqual(r["recovery_used"], 0, r)
            diagnostic = (
                "return function() return 1 end"
                if op == 0
                else "return {}"
                if op == 1
                else "return {name='N',inspect=function() return {} end,apply=function() return {} end}"
            )
            control = self.resource_case("execute", str(op), source=diagnostic)
            self.assert_resource_result(control, 2)
            self.assertEqual(control["refused"], 0, control)

    def assert_resource_result(self, r, status):
        self.assertEqual(r["status"], status, r)
        for key, value in (
            ("bad", 0),
            ("clean", 1),
            ("used", 0),
            ("recovery", 0),
            ("recovery_used", 0),
        ):
            self.assertEqual(r[key], value, r)
        self.assertEqual(r["states"], r["closes"], r)

    @staticmethod
    def workload(op, root="", handler=""):
        if op == 0:
            return (
                root
                + " return function(c) "
                + handler
                + " return {dx=0,dy=0,state=0} end"
            )
        return (
            root
            + " return {name='N',inspect=function(c) "
            + handler
            + " return 'Read.' end,apply=function(c) "
            + handler
            + " return {text='Used.',state=0,sanity_delta=0} end}"
        )

    def test_independent_fuel_and_pressure(self):
        tail = "local function f() return f() end; f();"
        for op in range(4):
            for phase in ("root", "handler"):
                for loop in ("while true do end;", tail):
                    source = self.workload(op, **{phase: loop})
                    r = self.resource_case("execute", str(op), source=source)
                    # Load checks function shapes, never executes either hook.
                    self.assert_resource_result(
                        r, 0 if op == 1 and phase == "handler" else 2
                    )
                    self.assertEqual(r["refused"], 0, r)
                    if r["status"]:
                        self.assertEqual(r["instructions"], 20000, r)
            for pressure in (
                "local s='xxxxxxxx'; while true do s=s..s end;",
                "local t={} for i=1,1000000 do t[i]={i,i,i,i} end;",
            ):
                r = self.resource_case(
                    "execute", str(op), source=self.workload(op, root=pressure)
                )
                self.assert_resource_result(r, 2)
                self.assertGreater(r["refused"], 0, r)
                self.assertLess(r["instructions"], 20000, r)
        r = self.resource_case("execute", "0", source="return function() return {} end")
        self.assert_resource_result(r, 3)
        self.assertEqual(r["refused"], 0, r)

    def test_cumulative_fuel_calibrated_on_real_lua(self):
        for op in (0, 2, 3):
            found = False
            for n in (2500, 3500, 4500, 5500, 6500):
                loop = f"local x=0; for i=1,{n} do x=x+1 end;"
                root = self.resource_case(
                    "execute", str(op), source=self.workload(op, root=loop)
                )
                handler = self.resource_case(
                    "execute", str(op), source=self.workload(op, handler=loop)
                )
                combined = self.resource_case(
                    "execute",
                    str(op),
                    source=self.workload(op, root=loop, handler=loop),
                )
                for r in (root, handler, combined):
                    self.assert_resource_result(r, r["status"])
                    self.assertEqual(r["refused"], 0, r)
                    self.assertEqual(r["bad"], 0, r)
                    self.assertEqual(r["used"], 0, r)
                    self.assertEqual(r["recovery"], 0, r)
                if root["status"] == handler["status"] == 0 and combined["status"] == 2:
                    self.assertLess(root["instructions"], 20000)
                    self.assertLess(handler["instructions"], 20000)
                    self.assertEqual(combined["instructions"], 20000)
                    found = True
                    break
            self.assertTrue(
                found, "bounded calibration did not find shared-budget witness"
            )

    def test_hook_quantum_without_reset(self):
        r = self.resource_case("hook-unit")
        self.assertEqual(r["checks"], 200, r)
        self.assertEqual(r["instructions"], 20000, r)
        self.assertEqual(r["bad"], 0, r)
        self.assertEqual(r["used"], 0, r)
        self.assertEqual(r["refused"], 0, r)
        self.assertEqual(r["recovery"], 0, r)
        self.assertEqual(r["recovery_used"], 0, r)

    def test_exact_statuses_and_discarded_extra_returns(self):
        good = "return function(c) return {dx=-1,dy=1,state=1000000},99 end,88"
        self.assertEqual(
            self.run_script(good), {"status": 0, "dx": -1, "dy": 1, "state": 1000000}
        )
        for source, status in [
            ("", 1),
            ("x", 2),
            (" ", 2),
            (" " * 4097, 1),
            (good + "\0", 1),
            ("return 1", 2),
            ("return function() return 1 end", 2),
            ("return function() return {} end", 3),
        ]:
            with self.subTest(source=repr(source)[:60]):
                self.assertEqual(
                    self.run_script(source),
                    {"status": status, "dx": 0, "dy": 0, "state": 0},
                )
        for value in ("1.0", "'1'", "true", "0/0", "1/0", "2", "nil"):
            self.assertEqual(
                self.run_script(
                    "return function() return {dx=" + value + ",dy=0,state=0} end"
                )["status"],
                3,
            )
        self.assertEqual(self.run_script(good + " " * (4096 - len(good)))["status"], 0)
        self.assertEqual(self.run_script(b"--\xff\xfe\n" + good.encode())["status"], 0)
        self.assertEqual(self.run_script(b"\xef\xbb\xbf" + good.encode())["status"], 2)

    def test_cross_family_sequence_and_actual_argument_types(self):
        r = self.resource_case("isolation")
        self.assertEqual(r["bad"], 0, r)
        self.assertEqual(r["operations"], 25, r)
        self.assertEqual(r["states"], r["closes"], r)
        self.assertEqual(r["states"], 25, r)
        self.assertEqual(r["used"], 0, r)
        for key in ("haunt_arguments", "curio_arguments", "history_entries"):
            self.assertGreater(r[key], 0, r)

    def test_haunt_context_endpoints_and_native_coordinates(self):
        source = "return function(c) return {dx=0,dy=0,state=c.state} end"
        for count in (-1, 0, 8, 9):
            for state in (-1, 0, 1000000, 1000001):
                r = self.run_script(source, f"context:{count}:{state}")
                status = 0 if 0 <= count <= 8 and 0 <= state <= 1000000 else 1
                self.assertEqual(
                    r,
                    {
                        "status": status,
                        "dx": 0,
                        "dy": 0,
                        "state": state if status == 0 else 0,
                    },
                )
        r = self.run_script(
            "return function(c) if c.mx ~= -2147483648 or c.my ~= 2147483647 or c.history[1].x ~= -2147483648 or c.history[1].y ~= 2147483647 then return nil end return {dx=0,dy=0,state=0} end",
            "extremes",
        )
        self.assertEqual(r["status"], 0)

    def test_haunt_complete_result_schema(self):
        for field, bounds in (
            ("dx", (-1, 1)),
            ("dy", (-1, 1)),
            ("state", (0, 1000000)),
        ):
            for value in (
                *map(str, bounds),
                str(bounds[0] - 1),
                str(bounds[1] + 1),
                "nil",
                "1.0",
                "0.5",
                "'0'",
                "false",
                "{}",
                "0/0",
                "1/0",
                "-1/0",
            ):
                source = (
                    "return function() local t={dx=0,dy=0,state=0};t."
                    + field
                    + "="
                    + value
                    + ";return t end"
                )
                r = self.run_script(source)
                expected = {"status": 0, "dx": 0, "dy": 0, "state": 0}
                if value in tuple(map(str, bounds)):
                    expected[field] = int(value)
                else:
                    expected["status"] = 3
                self.assertEqual(r, expected, (field, value))
        for key in ("extra", "[1]", "[true]", "[{}]", r'["dx\0alias"]'):
            r = self.run_script(
                "return function() return {dx=0,dy=0,state=0," + key + "=0} end"
            )
            self.assertEqual(r, {"status": 3, "dx": 0, "dy": 0, "state": 0})

    def test_empty_capabilities_root_and_handler(self):
        names = "_G io os package require load loadfile dofile debug coroutine math string table utf8 collectgarbage pcall xpcall print next pairs ipairs getmetatable setmetatable rawget rawset rawequal rawlen tonumber tostring type assert error select warn _VERSION random rn2 native game host engine player u pointer pointers".split()
        guard = (
            "if "
            + " or ".join(f"{name} ~= nil" for name in names)
            + " then return nil end;"
        )
        copied = "if c.sanity ~= nil or c.insight ~= nil or c.charges ~= nil or c.host ~= nil or c.player ~= nil or c.u ~= nil or c.pointer ~= nil or c.source ~= nil then return nil end;"
        source = (
            guard
            + " _ENV.marker=17; return function(c) "
            + guard
            + copied
            + " if marker ~= 17 then return nil end; c.history[1].x=99;c.mx=99;c.state=99;return {dx=0,dy=0,state=c.state} end"
        )
        self.assertEqual(
            self.run_script(source), {"status": 0, "dx": 0, "dy": 0, "state": 99}
        )
        for expression in (
            "pcall(function() return xpcall(function() while true do end end,function() end) end)",
            "require('x')",
            "load('while true do end')()",
            "debug.getregistry()",
            "coroutine.create(function() while true do end end)",
            "math.random()",
            "rn2(2)",
        ):
            for phase in ("root", "handler"):
                r = self.run_script(self.workload(0, **{phase: expression + ";"}))
                self.assertEqual(r, {"status": 2, "dx": 0, "dy": 0, "state": 0})

    def test_genuine_dumped_bytecode_public_nul_gate(self):
        p = subprocess.run(
            [str(self.exe), "dump"],
            input=b"return function(c) return {dx=0,dy=0,state=0} end",
            capture_output=True,
            timeout=3,
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(p.stdout.startswith(b"\x1bLua"))
        self.assertIn(b"\0", p.stdout)
        self.assertLessEqual(len(p.stdout), 4096)
        # Status 1 proves the public NUL gate, not independently text-only loading.
        # test_shared_lifecycle observes mode='t' on all four ordinary API paths.
        self.assertEqual(
            self.run_script(p.stdout), {"status": 1, "dx": 0, "dy": 0, "state": 0}
        )

    def test_pure_movement_and_state(self):
        r = self.run_script(
            "return function(c) return {dx=c.history[1].x-c.mx,dy=0,state=c.state+1} end"
        )
        self.assertEqual(r, {"status": 0, "dx": 1, "dy": 0, "state": 8})

    def test_bounds_errors_and_no_capabilities(self):
        for source in [
            "return function(c) while true do end end",
            "while true do end",
            "return function(c) local t={} for i=1,1000000 do t[i]={i} end return t end",
            'return function(c) return io.open("/etc/passwd") end',
            'return function(c) return os.execute("true") end',
            'return function(c) return load("return 1")() end',
            "return function(c) return {dx=2,dy=0,state=0} end",
            "return function(c) return {dx=true,dy=0,state=0} end",
            "return function(c) return {dx=0.5,dy=0,state=0} end",
            "return function(c) return {dx=0,dy=0,state=-1} end",
            "return function(c) return {dx=0,dy=0,state=0,damage=99} end",
            "return 4",
            "syntax ???",
            "\x1bLua",
            " " * 4097,
        ]:
            with self.subTest(source=source[:40]):
                self.assertNotEqual(self.run_script(source)["status"], 0)

    def test_handwritten_and_generated_follow_delayed_not_current_position(self):
        for name in ("footsteps.lua", "luna-footsteps.lua"):
            r = self.run_script((ROOT / "chaos/packs" / name).read_text(), "delay")
            self.assertEqual((r["status"], r["dx"]), (0, 1))

    def test_embedded_nul_in_result_key_is_rejected(self):
        source = r'return function(c) return {["dx\0x"]=0,dy=0,state=0} end'
        self.assertNotEqual(self.run_script(source)["status"], 0)

    def test_fresh_vm_no_hidden_persistent_globals(self):
        source = "hidden=(hidden or 0)+1; return function(c) return {dx=0,dy=0,state=hidden} end"
        self.assertEqual(self.run_script(source, "repeat")["state"], 1)
        self.assertEqual(self.run_script(source, "repeat")["state"], 1)
