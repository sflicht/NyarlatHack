"""Post-mortem reveal (#163): engine records only, refusals never narrated.

The run directories are written by the real chaos_io.c transport
(tests/chaos/io_harness.c) where possible. Rows the unit transport cannot
produce (expiry, curio, haunting) use the engine's exact event format.
"""

import json
import os
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CC = ["cc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-pedantic"]
REQUEST = dict(v=1, id=1, mutation="ambient", value=1, duration=0, telegraph=1, at=1)
WARD = dict(REQUEST, mutation="ward_efficacy", value=50, duration=5, telegraph=2)
HUNGER = dict(REQUEST, mutation="hunger_rate", value=2, duration=5, telegraph=3)


def event_row(seq, turn, event, detail):
    """Same field order as CHAOS_EVENT_FORMAT, as emitted by chaos_io.c."""
    return (
        f'{{"v":3,"seq":{seq},"turn":{turn},"safe":1,"event":"{event}",'
        f'"phase":"result","detail":"{detail}","sanity":80,"insight":0,'
        '"budget":2,"spent":0,"reserved":0,"last_id":0,'
        '"vitals":{"hp":10,"hp_max":10,"power":2,"power_max":2},'
        '"cosmetic":{"seen":0,"last_turn":0}}\n'
    )


class RevealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="chaos-reveal-bin-")
        out = pathlib.Path(cls.tmp.name)
        cls.io = out / "io"
        cls.reveal = out / "reveal"
        include = "-I" + str(ROOT / "include")
        subprocess.run(
            CC
            + [
                include,
                str(ROOT / "src/chaos_protocol.c"),
                str(ROOT / "src/chaos_io.c"),
                str(ROOT / "tests/chaos/io_harness.c"),
                "-o",
                str(cls.io),
            ],
            check=True,
            timeout=60,
        )
        subprocess.run(
            CC
            + [
                include,
                str(ROOT / "src/chaos_protocol.c"),
                str(ROOT / "src/chaos_reveal.c"),
                str(ROOT / "tests/chaos/reveal_harness.c"),
                "-o",
                str(cls.reveal),
            ],
            check=True,
            timeout=60,
        )

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.run_dir = tempfile.TemporaryDirectory(prefix="chaos-reveal-")
        self.path = pathlib.Path(self.run_dir.name)
        self.path.chmod(0o700)

    def tearDown(self):
        self.run_dir.cleanup()

    def transport(self, request, mode="normal"):
        """Real engine mailbox, admission and journal/ack writer."""
        if request is not None:
            p = self.path / "whisper.json"
            p.write_text(json.dumps(request))
            p.chmod(0o600)
        subprocess.run(
            [str(self.io), str(self.path), mode],
            check=True,
            capture_output=True,
            timeout=10,
        )

    def append(self, text):
        with (self.path / "events.jsonl").open("a") as stream:
            stream.write(text)

    def reveal_of(self, *host, path=None):
        p = subprocess.run(
            [str(self.reveal), str(path or self.path), *host],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        text = p.stdout
        match = re.search(r"^XLOG\[(.*)\]$", text, re.M)
        self.assertIsNotNone(match, text)
        xlog = match.group(1)
        section = text[: text.index("XLOG[")]
        return section, xlog

    def entries(self, section):
        return re.findall(r"^  Turn .*admitted\.$", section, re.M)

    # --- stock equality: nothing admitted means no bytes at all -------------
    def test_missing_and_empty_run_dirs_render_nothing(self):
        self.assertEqual(self.reveal_of(path=self.path / "absent"), ("", ""))
        self.assertEqual(self.reveal_of(), ("", ""))
        self.transport(None)  # empty mailbox through the real transport
        self.assertTrue((self.path / "events.jsonl").read_text())
        self.assertEqual(self.reveal_of(), ("", ""))

    # --- refusals are a count, never a narrated entry ----------------------
    def test_rejected_only_game_has_no_section_or_xlog(self):
        self.transport(WARD, "poor")  # real budget refusal
        acks = [
            json.loads(x)
            for x in (self.path / "events.jsonl").read_text().splitlines()
            if '"event":"ack"' in x
        ]
        self.assertEqual([a["status"] for a in acks], ["rejected", "rejected"])
        self.assertEqual(self.reveal_of(), ("", ""))

    def test_journaled_but_refused_telegraph_is_not_admitted(self):
        # The engine journals before the telegraph; a failed telegraph is
        # acknowledged as rejected. The journal row alone is not admission.
        self.transport(WARD, "fail_ui")
        self.assertIn('"status":"admitted"', (self.path / "whispers.jsonl").read_text())
        self.assertEqual(self.reveal_of(), ("", ""))
        # A later genuinely admitted whisper is listed; the refused one is not.
        self.transport(HUNGER, "normal")
        section, _ = self.reveal_of()
        self.assertEqual(len(self.entries(section)), 1, section)
        self.assertIn("(hunger_rate) was admitted.", section)
        self.assertNotIn("ward_efficacy", section)

    def test_accepted_ack_without_journal_row_is_refused(self):
        self.transport(WARD)
        forged = json.loads(
            [
                x
                for x in (self.path / "events.jsonl").read_text().splitlines()
                if '"event":"ack"' in x and '"accepted"' in x
            ][0]
        )
        forged.update(id=7, seq=99, mutation="hunger_rate", telegraph=3)
        self.append(json.dumps(forged, separators=(",", ":")) + "\n")
        section, xlog = self.reveal_of()
        self.assertEqual(len(self.entries(section)), 1, section)
        self.assertNotIn("hunger_rate", section)
        self.assertNotIn("whisper 7", section)
        self.assertIn("other candidates were refused; none took effect.", section)
        self.assertEqual(xlog, ":chaos_admitted=1:chaos_delivered=0:chaos_spent=3")

    def test_rejected_curio_and_haunting_are_counted_not_narrated(self):
        self.transport(REQUEST)
        self.append(
            event_row(90, 20, "curio", "rejected")
            + event_row(91, 21, "curio", "pre_admitted")
            + event_row(92, 22, "haunting", "pre_admitted")
            + event_row(93, 22, "haunting", "spawn_failed")
            + event_row(94, 23, "haunting", "rejected")
            + event_row(95, 24, "curio", "expired")
        )
        section, _ = self.reveal_of()
        self.assertEqual(len(self.entries(section)), 1, section)
        self.assertNotIn("curio", section)
        self.assertNotIn("haunting", section)
        # curio rejected, haunting spawn_failed and rejected, plus the
        # transport's own duplicate acknowledgement at its second safe point.
        self.assertIn("  4 other candidates were refused; none took effect.", section)

    # --- delivered is distinct from admitted -------------------------------
    def test_admitted_rule_change_is_never_delivered(self):
        self.transport(WARD, "expire")
        self.append(event_row(9, 15, "expiry", "ward_efficacy"))
        section, xlog = self.reveal_of()
        self.assertIn("whisper 1 (ward_efficacy) was admitted.", section)
        self.assertIn('Telegraph: "The lines of your wards seem thin and uncertain."', section)
        self.assertIn("Delivered: no;", section)
        self.assertNotIn("Delivered: yes", section)
        self.assertIn("Ended: expired on turn 15.", section)
        self.assertIn("chaos_delivered=0", xlog)

    def test_ambient_is_delivered_with_its_telegraph(self):
        self.transport(REQUEST)
        section, xlog = self.reveal_of()
        self.assertIn('Delivered: yes, "The shadows lean closer." was shown', section)
        self.assertEqual(xlog, ":chaos_admitted=1:chaos_delivered=1:chaos_spent=3")

    def test_haunt_curio_and_next_use_undelivered_without_engine_records(self):
        self.append(
            event_row(1, 5, "session", "new")
            + event_row(2, 20, "curio", "admitted")
            + event_row(3, 30, "haunting", "accepted")
        )
        section, xlog = self.reveal_of("next_use_undelivered", "haunt_active")
        self.assertEqual(len(self.entries(section)), 3, section)
        self.assertNotIn("Delivered: yes", section)
        self.assertEqual(section.count("Delivered: no"), 3, section)
        self.assertIn("Ended: still hunting when the game ended.", section)
        self.assertEqual(xlog, ":chaos_admitted=3:chaos_delivered=0:chaos_spent=3")

    def test_engine_delivery_records_mark_delivery(self):
        self.append(
            event_row(1, 5, "session", "new")
            + event_row(2, 20, "curio", "admitted")
            + event_row(3, 25, "curio", "placed")
            + event_row(4, 26, "curio", "applied requested=-3 actual=-2")
            + event_row(5, 30, "haunting", "accepted")
            + event_row(6, 31, "haunt_step", "")
        )
        section, xlog = self.reveal_of("next_use_delivered", "curio_placed")
        self.assertNotIn("Delivered: no", section)
        self.assertIn("you applied it 1 time (Sanity -2 in total)", section)
        self.assertIn("you saw it follow your trail 1 time.", section)
        self.assertIn("Ended: 2 uses left when the game ended.", section)
        self.assertEqual(xlog, ":chaos_admitted=3:chaos_delivered=3:chaos_spent=3")
        turns = [int(t) for t in re.findall(r"^  Turn (\d+)", section, re.M)]
        self.assertEqual(turns, sorted(turns))

    def test_curio_application_before_placement_is_ignored(self):
        self.append(
            event_row(1, 20, "curio", "admitted")
            + event_row(2, 26, "curio", "applied requested=-3 actual=-2")
        )
        section, _ = self.reveal_of()
        self.assertIn("Delivered: no; you never applied it.", section)

    # --- record ownership and game boundaries ------------------------------
    def test_new_session_discards_earlier_games_rows(self):
        self.transport(REQUEST)
        self.append(event_row(50, 1, "session", "new"))
        self.assertEqual(self.reveal_of(), ("", ""))

    def test_symlinked_records_are_not_followed(self):
        self.transport(REQUEST)
        other = pathlib.Path(self.run_dir.name + "-real")
        (self.path / "events.jsonl").rename(other)
        try:
            os.symlink(other, self.path / "events.jsonl")
            section, xlog = self.reveal_of()
            self.assertEqual((section, xlog), ("", ""))
        finally:
            other.unlink()

    def test_oversized_lines_are_skipped(self):
        self.transport(REQUEST)
        self.append('{"event":"ack","junk":"' + "x" * 9000 + '"}\n')
        section, _ = self.reveal_of()
        self.assertEqual(len(self.entries(section)), 1, section)

    # --- no RNG, no game-state writes ---------------------------------------
    def test_reveal_sources_draw_no_rng(self):
        for name in ("src/chaos_reveal.c", "src/chaos_reveal_game.c"):
            text = (ROOT / name).read_text()
            self.assertIsNone(
                re.search(r"\b(rn\w*|rnd|d)\(", text), name
            )


if __name__ == "__main__":
    unittest.main()
