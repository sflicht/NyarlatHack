"""Read-only lexical mutants; these do not replace linked physics tests."""

import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "hooks", ROOT / "scripts/check_upstream_hooks.py"
)
assert SPEC is not None and SPEC.loader is not None
hooks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hooks)


class HookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = json.loads(
            (ROOT / "docs/upstream-chaos-hooks.json").read_text()
        )
        cls.tracked = hooks.git_paths(ROOT)
        cls.baseline = hooks.git_paths(ROOT, True)

    def check(self, **kwargs):
        return hooks.check(ROOT, tracked=self.tracked, baseline=self.baseline, **kwargs)

    def test_file_scope_guards(self):
        rows = self.inventory["hooks"]
        leading = next(
            r
            for r in rows
            if r["file"] == "src/bones.c" and r["signature"] == ["#", "ifdef", "CHAOS"]
        )
        self.assertEqual(leading["symbol"], "<file>")
        self.assertFalse(
            any(
                r["symbol"] in {"remember_topl", "tty_display_nhwindow", "tty_putstr"}
                and r["kind"] == "directive"
                for r in rows
            )
        )

    def test_baseline(self):
        self.assertEqual(self.check(), [])

    def test_lexer(self):
        tokens = hooks.lex(
            '/* chaos_fake */ "chaos_fake\\""; // chaos_fake\nchaos_\\\nevent("pray", \'x\');'
        )
        self.assertEqual([t[0] for t in tokens if t[1] == "id"], ["chaos_event"])
        for text in ["/* unfinished", '"unfinished', "#else\n", "#ifdef CHAOS\n"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                hooks.discover("src/test.c", text)

    def test_cpp_macro_both_branches(self):
        rows, _, _ = hooks.discover(
            "x.c",
            '#if X\n#define CALL chaos_event("a", "b", "")\n#else\nchaos_safe("x");\n#endif\n',
        )
        self.assertTrue(any("chaos_event" in r["signature"] for r in rows))
        self.assertTrue(
            any(
                "chaos_safe" in r["signature"] and "| else" in r["guards"][0]
                for r in rows
            )
        )

    def test_mutants(self):
        cases = [
            (
                "src/save.c",
                "/* NetHack",
                'chaos_event("apply", "attempt", "");\n/* NetHack',
                "EXTRA",
            ),
            (
                "src/apply.c",
                'chaos_event("apply", "attempt", "");',
                'chaos_event("apply", "attempt", ""); chaos_event("apply", "attempt", "");',
                "EXTRA",
            ),
            ("src/pray.c", 'chaos_safe("pray");', "", "MISSING"),
            (
                "src/monmove.c",
                "chaos_ward_count(num_wards_at(x,y))",
                "num_wards_at(x,y)",
                "MISSING",
            ),
            ("src/pray.c", '"cancelled"', '"changed"', "MISSING"),
            (
                "src/apply.c",
                "CHAOS_OBS_OP_WHISTLING",
                "CHAOS_OBS_OP_FOUNTAIN_DRINK",
                "MISSING",
            ),
            ("src/pray.c", '#include "chaos.h"', "", "MISSING"),
            ("util/makedefs.c", "| (1L << 26)", "", "MISSING"),
            ("include/you.h", "#ifdef CHAOS", "#ifdef OTHER", "MISSING"),
            (
                "src/detect.c",
                "tty_display_map_presented",
                "different_adapter",
                "MISSING",
            ),
        ]
        for path, old, new, diagnostic in cases:
            with self.subTest(path=path, old=old):
                text = (ROOT / path).read_text()
                self.assertIn(old, text, "mutant must actually change source")
                result = self.check(overrides={path: text.replace(old, new, 1)})
                self.assertTrue(any(diagnostic in e for e in result), result)

    def test_whitespace_and_false_positives(self):
        text = (ROOT / "src/pray.c").read_text()
        text = text.replace('chaos_safe("pray")', 'chaos_safe /* note */ ( "pray" )')
        text += '\n/* chaos_event("bad") */\nconst char *fake = "chaos_fake";\n'
        self.assertEqual(self.check(overrides={"src/pray.c": text}), [])

    def test_cli_defect(self):
        import contextlib
        import io
        from unittest.mock import patch

        data = copy.deepcopy(self.inventory)
        data["hooks"][0]["count"] += 1
        real_check = hooks.check
        output = io.StringIO()
        with (
            patch.object(
                hooks,
                "check",
                lambda root: real_check(
                    root, inventory=data, tracked=self.tracked, baseline=self.baseline
                ),
            ),
            contextlib.redirect_stderr(output),
        ):
            self.assertEqual(hooks.main(["--root", str(ROOT)]), 1)
        self.assertIn("MISSING", output.getvalue())

    def test_strict_schema(self):
        for field, value in [
            ("version", True),
            ("windows", {"../escape.c": []}),
            ("windows", {"src/apply.c": [{"symbol": "bad", "start": [], "end": []}]}),
        ]:
            data = copy.deepcopy(self.inventory)
            data[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.check(inventory=data)

    def test_symlink_rejected(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "outside.c").symlink_to(ROOT / "src/pray.c")
            data = dict(
                version=1,
                baseline=hooks.BASELINE,
                hooks=[],
                windows={},
                inherited={},
                build_blocks=[],
            )
            with self.assertRaisesRegex(ValueError, "symlink"):
                hooks.check(
                    root, inventory=data, tracked={"outside.c"}, baseline={"outside.c"}
                )

    def test_new_native_scope(self):
        result = hooks.check(
            ROOT,
            tracked=self.tracked | {"src/new.c"},
            baseline=self.baseline,
            overrides={
                "src/new.c": 'void new_hook(void) { chaos_event("new", "attempt", ""); }'
            },
        )
        self.assertTrue(any("UNCLASSIFIED" in e for e in result), result)
        self.assertTrue(any("EXTRA src/new.c" in e for e in result), result)
        paths, unclassified = hooks.scope_paths(
            self.tracked | {"src/new.c"}, self.baseline
        )
        self.assertIn("src/new.c", paths)
        self.assertEqual(unclassified, ["src/new.c"])
        paths, _ = hooks.scope_paths({"src/chaos_old.c"}, {"src/chaos_old.c"})
        self.assertEqual(paths, ["src/chaos_old.c"])

    def test_invalid_metadata(self):
        for field, value in [
            ("count", True),
            ("file", "../src/pray.c"),
            ("purpose", ""),
        ]:
            data = copy.deepcopy(self.inventory)
            data["hooks"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check(inventory=data)
        data = copy.deepcopy(self.inventory)
        data["hooks"].append(data["hooks"][0])
        with self.assertRaises(ValueError):
            self.check(inventory=data)


if __name__ == "__main__":
    unittest.main()
