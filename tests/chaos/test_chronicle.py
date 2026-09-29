"""`chaos chronicle RUN_DIR` (#188): presentation only, engine facts only.

Records are produced by the real reveal core (src/chaos_reveal.c through
tests/chaos/reveal_harness.c) over run directories written by the real
chaos_io.c transport, so the page is tested against engine output, not a
hand-written imitation of it.
"""

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from chaos import chronicle  # noqa: E402

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_reveal import HUNGER, REQUEST, WARD, event_row  # noqa: E402

CC = ["cc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-pedantic"]
HOSTILE = "<script>alert(1)</script>&\"'*_[x](javascript:y)"


class ChronicleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="chaos-chronicle-bin-")
        out = pathlib.Path(cls.tmp.name)
        cls.io, cls.reveal = out / "io", out / "reveal"
        include = "-I" + str(ROOT / "include")
        for exe, parts in (
            (
                cls.io,
                ["src/chaos_protocol.c", "src/chaos_io.c", "tests/chaos/io_harness.c"],
            ),
            (
                cls.reveal,
                [
                    "src/chaos_protocol.c",
                    "src/chaos_reveal.c",
                    "tests/chaos/reveal_harness.c",
                ],
            ),
        ):
            subprocess.run(
                CC + [include, *(str(ROOT / p) for p in parts), "-o", str(exe)],
                check=True,
                timeout=60,
            )

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(prefix="chaos-chronicle-")
        self.run_dir = pathlib.Path(self.dir.name) / "run"
        self.run_dir.mkdir(mode=0o700)
        self.out = pathlib.Path(self.dir.name) / "out"
        self.out.mkdir()

    def tearDown(self):
        self.dir.cleanup()

    # --- fixtures: engine-produced records ----------------------------------
    def transport(self, request, mode="normal"):
        p = self.run_dir / "whisper.json"
        p.write_text(json.dumps(request))
        p.chmod(0o600)
        subprocess.run(
            [str(self.io), str(self.run_dir), mode],
            check=True,
            capture_output=True,
            timeout=10,
        )

    def append(self, text):
        with (self.run_dir / "events.jsonl").open("a") as s:
            s.write(text)

    def engine_record(self, *host):
        """Run the reveal core; write its record as the game does. Returns
        the dumplog section text the same core rendered."""
        text = subprocess.run(
            [str(self.reveal), str(self.run_dir), *host],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
        section = text[: text.index("XLOG[")]
        record = re.search(r"^JSON\[(.*)\]$", text, re.M).group(1)
        if record:
            (self.run_dir / "reveal.json").write_text(record + "\n")
        return section

    def chronicle(self, fmt="html", intent=None):
        out = self.out / f"page.{fmt}"
        args = SimpleNamespace(run_dir=self.run_dir, format=fmt, out=out, intent=intent)
        self.assertEqual(chronicle.run(args), 0)
        return out.read_text()

    def snapshot(self):
        return {
            p.name: (p.read_bytes(), p.stat().st_mtime_ns)
            for p in self.run_dir.iterdir()
        }

    # --- facts match the dumplog section -------------------------------------
    def test_facts_are_the_dumplog_lines(self):
        self.transport(REQUEST)
        self.append(
            event_row(10, 30, "haunting", "accepted")
            + event_row(11, 31, "haunt_step", "")
        )
        section = self.engine_record()
        c = chronicle.load(self.run_dir)
        lines = [x.strip() for x in section.splitlines()[1:] if x.strip()]
        rendered = (
            [x for e in c.entries for x in [e.heading, *e.details]] + c.notes + c.tally
        )
        self.assertEqual(sorted(rendered), sorted(lines))
        self.assertEqual(len(c.entries), 2)
        page = self.chronicle("md")
        for line in lines:
            self.assertIn(chronicle._md_text(line), page)

    # --- refused, unqualified and undelivered never become admitted ---------
    def test_refused_only_game_has_no_record_and_no_page(self):
        self.transport(WARD, "poor")
        self.assertEqual(self.engine_record(), "")
        self.assertFalse((self.run_dir / "reveal.json").exists())
        err = self.out / "err"
        args = SimpleNamespace(
            run_dir=self.run_dir, format="html", out=err, intent=None
        )
        self.assertEqual(chronicle.run(args), 1)
        self.assertFalse(err.exists())

    def test_refused_candidates_are_a_count_only(self):
        self.transport(REQUEST)
        self.append(
            event_row(20, 40, "curio", "rejected")
            + event_row(21, 41, "haunting", "rejected")
        )
        self.engine_record()
        c = chronicle.load(self.run_dir)
        self.assertEqual(len(c.entries), 1)
        self.assertEqual(c.rejected, 2)
        page = self.chronicle()
        self.assertIn("2 other candidates were refused; none took effect.", page)
        self.assertNotIn("curio", page.lower())
        self.assertNotIn("haunting was admitted", page)

    def test_undelivered_stays_undelivered(self):
        self.transport(HUNGER)
        self.append(event_row(10, 30, "haunting", "accepted"))
        self.engine_record("haunt_active")
        page = self.chronicle("md")
        self.assertIn(chronicle._md_text("Delivered: no"), page)
        self.assertNotIn("Delivered: yes", page)

    # --- intent: always labelled, never for something that did not happen --
    def test_intent_always_carries_the_label(self):
        self.transport(REQUEST)
        self.engine_record()
        intent = self.out / "intent.json"
        intent.write_text(json.dumps({"1": "Make the omen feel personal."}))
        for fmt in ("html", "md"):
            page = self.chronicle(fmt, intent)
            self.assertEqual(page.count(chronicle.INTENT_LABEL), 1, fmt)
            before = page.index(chronicle.INTENT_LABEL)
            self.assertLess(before, page.index("Make the omen feel personal"))

    def test_intent_for_an_unadmitted_entry_is_refused(self):
        self.transport(REQUEST)
        self.append(event_row(20, 40, "haunting", "rejected"))
        self.engine_record()
        intent = self.out / "intent.json"
        intent.write_text(json.dumps({"2": "The hound will hunt them."}))
        args = SimpleNamespace(
            run_dir=self.run_dir, format="html", out=self.out / "p", intent=intent
        )
        self.assertEqual(chronicle.run(args), 1)
        self.assertFalse((self.out / "p").exists())

    def test_director_files_are_never_read_as_intent(self):
        (self.run_dir / "next_use-schedule.jsonl").write_text(
            '{"rationale":"betray them"}\n'
        )
        self.transport(REQUEST)
        self.engine_record()
        self.assertNotIn("betray", self.chronicle())

    # --- escaping ------------------------------------------------------------
    def test_hostile_strings_are_escaped(self):
        record = {
            "reveal_v": 1,
            "final_turn": 9,
            "admitted": 1,
            "delivered": 0,
            "spent": 1,
            "rejected": 0,
            "lines": [
                "The Crawling Chaos remembers.",
                f"  Turn 3: {HOSTILE} was admitted.",
                f'    Telegraph: "{HOSTILE}"',
                "  Admitted 1, delivered 0; cruelty spent 1.",
                "",
            ],
        }
        (self.run_dir / "reveal.json").write_text(json.dumps(record))
        intent = self.out / "intent.json"
        intent.write_text(json.dumps({"1": HOSTILE}))
        page = self.chronicle("html", intent)
        self.assertNotIn("<script", page)
        self.assertIsNone(re.search(r"<a\b|href\s*=", page))
        self.assertEqual(page.count("&lt;script&gt;"), 3)
        md = self.chronicle("md", intent)
        self.assertNotIn("<script", md)
        self.assertNotIn("](", md)

    def test_html_is_self_contained(self):
        self.transport(REQUEST)
        self.engine_record()
        page = self.chronicle()
        self.assertIsNone(re.search(r"(src|href)\s*=|https?://|@import|url\(", page))
        self.assertIn("default-src 'none'", page)

    # --- read-only, bounded, fail closed -------------------------------------
    def test_run_dir_is_never_written(self):
        self.transport(REQUEST)
        self.engine_record()
        before = self.snapshot()
        self.chronicle()
        self.chronicle("md")
        inside = SimpleNamespace(
            run_dir=self.run_dir, format="md", out=self.run_dir / "page.md", intent=None
        )
        self.assertEqual(chronicle.run(inside), 1)
        self.assertEqual(self.snapshot(), before)

    def test_bad_records_fail_closed(self):
        good = {
            "reveal_v": 1,
            "final_turn": 9,
            "admitted": 1,
            "delivered": 0,
            "spent": 0,
            "rejected": 0,
            "lines": [
                "The Crawling Chaos remembers.",
                "  Turn 1: x was admitted.",
                "  Admitted 1, delivered 0; cruelty spent 0.",
                "",
            ],
        }
        chronicle.load(self._write(good))
        for bad in (
            dict(good, reveal_v=2),
            dict(good, admitted=0),
            dict(good, admitted=True),
            dict(good, admitted=2),
            dict(good, lines=good["lines"][1:]),
            dict(good, lines=["The Crawling Chaos remembers.", "    orphan detail"]),
            dict(good, lines=[*good["lines"][:2], "free text", *good["lines"][2:]]),
        ):
            with self.assertRaises(chronicle.ChronicleError, msg=bad):
                chronicle.load(self._write(bad))
        (self.run_dir / "reveal.json").unlink()
        (self.run_dir / "reveal.json").symlink_to(self.out / "elsewhere.json")
        (self.out / "elsewhere.json").write_text(json.dumps(good))
        with self.assertRaises(chronicle.ChronicleError):
            chronicle.load(self.run_dir)

    def _write(self, record):
        p = self.run_dir / "reveal.json"
        if p.is_symlink():
            p.unlink()
        p.write_text(json.dumps(record))
        return self.run_dir

    def test_command_line_offline(self):
        self.transport(REQUEST)
        self.engine_record()
        env = {
            k: v for k, v in os.environ.items() if "KEY" not in k and "TOKEN" not in k
        }
        env.update(http_proxy="http://127.0.0.1:9", https_proxy="http://127.0.0.1:9")
        p = subprocess.run(
            [
                sys.executable,
                "-m",
                "chaos",
                "chronicle",
                str(self.run_dir),
                "--format",
                "md",
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("# What watched you", p.stdout)


if __name__ == "__main__":
    unittest.main()
