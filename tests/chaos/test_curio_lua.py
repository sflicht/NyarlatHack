"""Pure curio API contract against real Lua 5.4, without game or model calls."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = """
return {
    name = "Marked counter",
    inspect = function(c)
        if c.insight >= 10 and c.state == 7 then return "Seven marks." end
        return "An unmarked face."
    end,
    apply = function(c)
        if c.sanity < 50 then
            return {text="One mark added.",state=c.state+1,sanity_delta=2}
        end
        return {text="One mark removed.",state=c.state-1,sanity_delta=-2}
    end
}
"""


def curio(name='"Counter"', inspect='return "Read."', apply=None, extra=""):
    if apply is None:
        apply = 'return {text="Used.",state=c.state,sanity_delta=0}'
    return (
        f"return {{name={name},inspect=function(c) {inspect} end,"
        f"apply=function(c) {apply} end{extra}}}"
    )


class CurioLuaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="nyarl-curio-lua-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.exe = Path(cls.tmp.name) / "curio-lua-test"
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
                str(ROOT / "tests/chaos/curio_lua_harness.c"),
                *flags,
                "-o",
                str(cls.exe),
            ],
            check=True,
        )

    def run_script(
        self, source=FIXTURE, operation="apply", mode="normal", context=None
    ):
        args = [str(self.exe), operation, mode]
        if context is not None:
            args.extend(map(str, context))
        p = subprocess.run(
            args,
            input=source.encode() if isinstance(source, str) else source,
            capture_output=True,
            timeout=3,
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        result = json.loads(p.stdout)
        self.assertEqual(result["unchanged"], 1, "caller context was mutated")
        result["text"] = bytes.fromhex(result.pop("hex")).decode(
            "ascii", errors="replace"
        )
        if result["status"] and mode != "null-output":
            self.assertEqual(result["cleared"], 1, result)
            self.assertEqual(result["text"], "")
            self.assertEqual((result["state"], result["sanity_delta"]), (0, 0))
        return result

    def reject(self, source, operations=("load", "inspect", "apply"), **kwargs):
        for operation in operations:
            with self.subTest(operation=operation, source=repr(source)[:100], **kwargs):
                self.assertNotEqual(
                    self.run_script(source, operation, **kwargs)["status"], 0
                )

    def test_neutral_fixture_and_state_transitions(self):
        r = self.run_script(operation="load")
        self.assertEqual((r["status"], r["text"]), (0, "Marked counter"))
        for context, text in [
            ((50, 10, 3, 7), "Seven marks."),
            ((50, 9, 3, 7), "An unmarked face."),
            ((50, 10, 3, 8), "An unmarked face."),
        ]:
            r = self.run_script(operation="inspect", context=context)
            self.assertEqual((r["status"], r["text"]), (0, text))
        for sanity, state, delta, text in [
            (49, 8, 2, "One mark added."),
            (50, 6, -2, "One mark removed."),
        ]:
            r = self.run_script(context=(sanity, 10, 3, 7))
            self.assertEqual(
                (r["status"], r["state"], r["sanity_delta"], r["text"]),
                (0, state, delta, text),
            )
        r = self.run_script(context=(49, 10, 3, 8))
        self.assertEqual((r["status"], r["state"]), (0, 9))

    def test_source_limits_and_text_only(self):
        source = curio()
        for length in (len(source), 4096):
            padded = source + " " * (length - len(source))
            for operation in ("load", "inspect", "apply"):
                self.assertEqual(self.run_script(padded, operation)["status"], 0)
        for bad in (
            b"",
            b" ",
            b"x",
            source + " " * (4097 - len(source)),
            source + "\0",
            b"\x1bLua",
            b"\x1bLua\x54\0",
            "syntax ???",
        ):
            self.reject(bad)

    def test_compiled_bytecode_is_rejected(self):
        binary = subprocess.run(
            [str(self.exe), "dump"],
            input=FIXTURE.encode(),
            capture_output=True,
            timeout=3,
        )
        self.assertEqual(binary.returncode, 0, binary.stderr)
        self.assertTrue(binary.stdout.startswith(b"\x1bLua"))
        self.assertLessEqual(len(binary.stdout), 4096)
        self.reject(binary.stdout)

    def test_null_pointers(self):
        for mode in ("null-source", "null-output"):
            self.reject(FIXTURE, mode=mode)
        self.reject(FIXTURE, ("inspect", "apply"), mode="null-context")

    def test_context_bounds_including_zero_charges(self):
        defaults = [50, 10, 3, 7]
        for field, high in enumerate((100, 1000000, 3, 255)):
            for value in (-1, 0, high, high + 1):
                c = defaults.copy()
                c[field] = value
                for operation in ("inspect", "apply"):
                    with self.subTest(field=field, value=value, operation=operation):
                        r = self.run_script(curio(), operation, context=c)
                        self.assertEqual(r["status"] == 0, 0 <= value <= high)

    def test_only_copied_context_fields_and_no_caller_mutation(self):
        # Explicit nil checks rule out movement fields or native engine pointers;
        # writes to this disposable Lua table must not affect the caller's struct.
        check = """
            if c.sanity ~= 50 or c.insight ~= 10 or c.charges ~= 0 or c.state ~= 7
               or c.mx ~= nil or c.history ~= nil or c.player ~= nil
               or c.source ~= nil then return nil end
            c.sanity=0; c.insight=0; c.charges=99; c.state=12; c.extra={}
        """
        for operation in ("inspect", "apply"):
            source = curio(
                inspect=check + 'return "Copied."',
                apply=check + 'return {text="Copied.",state=c.state,sanity_delta=0}',
            )
            r = self.run_script(source, operation, context=(50, 10, 0, 7))
            self.assertEqual((r["status"], r["text"]), (0, "Copied."))
            if operation == "apply":
                self.assertEqual(r["state"], 12)

    def test_root_and_function_schema(self):
        for bad in (
            "return nil",
            "return 3",
            "return true",
            'return "table"',
            "return function() end",
            "return {}",
            "return {name='N'}",
            "return {name='N',inspect=function() end}",
            "return {name='N',apply=function() end}",
            "return {inspect=function() end,apply=function() end}",
            curio(extra=",damage=9"),
            curio(extra=",[1]=9"),
            curio(extra=",[true]=9"),
            curio(extra=",[{}]=9"),
            curio(extra=r', ["name\0x"]="N"'),
            curio().replace('inspect=function(c) return "Read." end', "inspect=5"),
            curio().replace(
                'apply=function(c) return {text="Used.",state=c.state,sanity_delta=0} end',
                "apply={}",
            ),
            curio() + ", 2",
        ):
            self.reject(bad)
        for field in ("inspect", "apply"):
            for value in ("nil", "false", "0", '"function"', "{}"):
                source = (
                    "local t={name='N',inspect=function() end,apply=function() end};"
                    f"t.{field}={value};return t"
                )
                self.reject(source)

    def test_name_ascii_limits_and_nonblank(self):
        for name in ("x", "x" * 48, " x ", 'Quote " slash \\ !~'):
            source = curio(name=json.dumps(name))
            for operation in ("load", "inspect", "apply"):
                r = self.run_script(source, operation)
                self.assertEqual(r["status"], 0)
                if operation == "load":
                    self.assertEqual(r["text"], name)
        for expression in (
            '""',
            '" "',
            '"' + "n" * 49 + '"',
            "0",
            "false",
            "{}",
            "nil",
        ):
            self.reject(curio(name=expression))
        for byte in (0, 1, 9, 10, 13, 31, 127, 128, 255):
            self.reject(curio(name=f'"name\\{byte:03d}"'))
        self.reject(curio(name='"é"'))

    def test_hook_text_ascii_limits_and_nonblank(self):
        for text in ("x", "x" * 160, " x ", 'Quote " slash \\ !~'):
            source = curio(
                inspect="return " + json.dumps(text),
                apply="return {text=" + json.dumps(text) + ",state=0,sanity_delta=0}",
            )
            for operation in ("inspect", "apply"):
                r = self.run_script(source, operation)
                self.assertEqual((r["status"], r["text"]), (0, text))
        invalid = ['""', '" "', '"' + "x" * 161 + '"', "0", "false", "nil", "{}", '"é"']
        invalid += [
            f'"text\\{byte:03d}"' for byte in (0, 1, 9, 10, 13, 31, 127, 128, 255)
        ]
        for expression in invalid:
            source = curio(
                inspect="return " + expression,
                apply="return {text=" + expression + ",state=0,sanity_delta=0}",
            )
            self.reject(source, ("inspect", "apply"))

    def test_apply_exact_schema_and_integer_bounds(self):
        for state in (0, 255):
            for delta in (-2, -1, 0, 1, 2):
                source = curio(
                    apply=f'return {{text="Used.",state={state},sanity_delta={delta}}}'
                )
                r = self.run_script(source)
                self.assertEqual(
                    (r["status"], r["state"], r["sanity_delta"]), (0, state, delta)
                )
        for field, values in (
            (
                "state",
                ("-1", "256", "7.0", "0.5", "true", "'7'", "nil", "{}", "1/0", "0/0"),
            ),
            (
                "sanity_delta",
                ("-3", "3", "0.0", "0.5", "false", "'0'", "nil", "{}", "1/0", "0/0"),
            ),
        ):
            for value in values:
                source = curio(
                    apply='local t={text="Used.",state=7,sanity_delta=0};'
                    + f"t.{field}={value};return t"
                )
                self.reject(source, ("apply",))
        for result in (
            "nil",
            "false",
            "1",
            '"Used."',
            "function() end",
            "{}",
            "{state=0,sanity_delta=0}",
            '{text="X",state=0}',
            '{text="X",sanity_delta=0}',
            '{text="X",state=0,sanity_delta=0,charges=2}',
            '{text="X",state=0,sanity_delta=0,[1]=2}',
            '{text="X",state=0,sanity_delta=0,[false]=2}',
            r'{text="X",state=0,sanity_delta=0,["state\0x"]=2}',
        ):
            self.reject(curio(apply="return " + result), ("apply",))

    def test_exact_single_hook_return_and_inspect_has_no_intent(self):
        for inspect in (
            "return",
            'return "X", 2',
            'return {text="X",state=0,sanity_delta=0}',
        ):
            self.reject(curio(inspect=inspect), ("inspect",))
        for apply in ("return", 'return {text="X",state=0,sanity_delta=0}, 2'):
            self.reject(curio(apply=apply), ("apply",))

    def test_load_validates_without_executing_hooks(self):
        source = curio(inspect="while true do end", apply="while true do end")
        self.assertEqual(self.run_script(source, "load")["status"], 0)
        self.reject(source, ("inspect", "apply"))

    def test_no_standard_libraries_or_host_capabilities(self):
        names = (
            "_G",
            "io",
            "os",
            "package",
            "require",
            "load",
            "loadfile",
            "dofile",
            "debug",
            "coroutine",
            "math",
            "string",
            "table",
            "utf8",
            "collectgarbage",
            "pcall",
            "xpcall",
            "print",
            "next",
            "pairs",
            "getmetatable",
            "setmetatable",
            "rawget",
            "rawset",
            "tonumber",
            "tostring",
            "random",
            "host",
            "engine",
        )
        guard = (
            "if "
            + " or ".join(f"{name} ~= nil" for name in names)
            + " then return nil end;"
        )
        source = guard + curio(
            inspect=guard + 'return "Isolated."',
            apply=guard + 'return {text="Isolated.",state=0,sanity_delta=0}',
        )
        for operation in ("load", "inspect", "apply"):
            self.assertEqual(self.run_script(source, operation)["status"], 0)
        for expression in (
            'io.open("/etc/passwd")',
            'os.execute("true")',
            'load("return 1")()',
            "math.random()",
            "debug.getregistry()",
            "c.pointer()",
        ):
            self.reject(
                curio(inspect="return " + expression, apply="return " + expression),
                ("inspect", "apply"),
            )

    def test_instruction_exhaustion_in_source_and_hooks(self):
        self.reject("while true do end")
        self.reject("local function f() return f() end; f()")
        self.reject(
            curio(inspect="while true do end", apply="while true do end"),
            ("inspect", "apply"),
        )

    def test_allocation_exhaustion_in_source_and_hooks(self):
        for pressure in (
            'local s="xxxxxxxx"; for i=1,20 do s=s..s end;',
            "local t={}; for i=1,3000 do t[i]={i,i,i,i,i,i,i,i} end;",
        ):
            self.reject(pressure + curio())
            self.reject(
                curio(
                    inspect=pressure + 'return "X"',
                    apply=pressure + 'return {text="X",state=0,sanity_delta=0}',
                ),
                ("inspect", "apply"),
            )

    def test_memory_pressure_at_setup_and_extraction_never_panics(self):
        # Leave varying headroom for copied input and result validation, allocating
        # before/after root construction and inside hooks. Rejection is permitted,
        # but never a panic or partial output. Require crossing the cap, not merely
        # running a collection of scripts that all fail (or all succeed).
        outcomes = {op: set() for op in ("load", "inspect", "apply")}
        for count in range(700, 1501, 40):
            pressure = f"held={{}}; for i=1,{count} do held[i]={{1,2,3,4,5,6,7,8}} end;"
            for source in (
                pressure + curio(),
                curio().replace("return ", "local root=", 1)
                + ";"
                + pressure
                + "return root",
                curio(
                    inspect=pressure + 'return "Read."',
                    apply=pressure + 'return {text="Used.",state=7,sanity_delta=0}',
                ),
            ):
                for operation in outcomes:
                    result = self.run_script(source, operation)
                    outcomes[operation].add(result["status"] == 0)
            # Exercise validation error creation under retained memory pressure.
            self.reject(
                curio(
                    inspect=pressure + 'return ""',
                    apply=pressure + 'return {text="Used.",state=7,sanity_delta=false}',
                ),
                ("inspect", "apply"),
            )
        for operation, results in outcomes.items():
            self.assertEqual(results, {False, True}, operation)

    def test_fresh_source_globals_and_closure_on_repeated_calls(self):
        source = """
            hidden=(hidden or 0)+1; local calls=0
            return {
                name=hidden == 1 and "Fresh" or "Leaked",
                inspect=function(c)
                    calls=calls+1
                    if hidden ~= 1 or calls ~= 1 then return nil end
                    _ENV.leaked=c; c.state=99; return "Fresh"
                end,
                apply=function(c)
                    calls=calls+1
                    if hidden ~= 1 or calls ~= 1 or leaked ~= nil then return nil end
                    _ENV.leaked=c; return {text="Fresh",state=c.state,sanity_delta=0}
                end
            }
        """
        for operation in ("load", "inspect", "apply"):
            r = self.run_script(source, operation, "repeat")
            self.assertEqual((r["status"], r["text"]), (0, "Fresh"))
            if operation == "apply":
                self.assertEqual(r["state"], 7)


if __name__ == "__main__":
    unittest.main()
