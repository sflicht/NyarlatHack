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


# enum chaos_next_use_slot_w / _f values (mirrored in include/chaos_reveal.h).
W_PENDING, W_ARMED, W_EXPIRED = 1, 2, 7
F_PENDING, F_APPLIED, F_NATIVE = 1, 2, 3


def nu(w, f, witnessed, terminated, move, origin_w=0, origin_f=0, depth=0):
    """Host fact: the engine's runtime snapshot values, as the game copies them."""
    return f"nu={w},{f},{witnessed},{terminated},{move},{origin_w},{origin_f},{depth}"


def observation_row(seq, turn, operation, stage="started"):
    """A chaos_io_observation row (CHAOS_OBSERVATION_VERSION 3 fields)."""
    return (
        f'{{"v":3,"seq":{seq},"turn":{turn},"safe":1,"event":"observation",'
        f'"phase":"result","detail":"","sanity":80,"insight":0,'
        '"budget":2,"spent":0,"reserved":0,"last_id":0,'
        '"vitals":{"hp":10,"hp_max":10,"power":2,"power_max":2},'
        '"cosmetic":{"seen":0,"last_turn":0},'
        f'"observation":{{"operation":"{operation}","stage":"{stage}",'
        '"root_seq":0,"fact":"none"}}\n'
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
        # #188: the reveal record chronicle reads is the same lines, byte for
        # byte, and exists exactly when the section does.
        record = re.search(r"^JSON\[(.*)\]$", text, re.M)
        self.assertIsNotNone(record, text)
        if section:
            doc = json.loads(record.group(1))
            self.assertEqual(doc["reveal_v"], 1)
            self.assertEqual(doc["lines"], section.split("\n")[:-1])
            self.assertEqual(
                xlog,
                f":chaos_admitted={doc['admitted']}:chaos_delivered={doc['delivered']}"
                f":chaos_spent={doc['spent']}",
            )
        else:
            self.assertEqual(record.group(1), "")
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
        # Only the forged row: the duplicate ack of whisper 1 is not a candidate.
        self.assertIn("  1 other candidate was refused; none took effect.", section)
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
        # curio rejected, haunting spawn_failed and rejected. The transport's
        # duplicate acknowledgement of admitted whisper 1 at its second safe
        # point is the same whisper, not another candidate.
        self.assertIn('"detail":"duplicate"', (self.path / "events.jsonl").read_text())
        self.assertIn("  3 other candidates were refused; none took effect.", section)

    # --- delivered is distinct from admitted -------------------------------
    def test_admitted_rule_change_is_never_delivered(self):
        self.transport(WARD, "expire")
        self.append(event_row(9, 15, "expiry", "ward_efficacy"))
        section, xlog = self.reveal_of()
        self.assertIn("whisper 1 (ward_efficacy) was admitted.", section)
        self.assertIn(
            'Telegraph: "The lines of your wards seem thin and uncertain."', section
        )
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
        section, xlog = self.reveal_of(nu(W_ARMED, 0, 0, 1, 40), "haunt_active")
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
        section, xlog = self.reveal_of(nu(W_ARMED, 0, 1, 1, 40), "curio_placed")
        self.assertNotIn("Delivered: no", section)
        self.assertIn("you applied it 1 time (Sanity -2 in total)", section)
        self.assertIn("you saw it follow your trail 1 time.", section)
        self.assertIn("Ended: 2 uses left when the game ended.", section)
        self.assertEqual(xlog, ":chaos_admitted=3:chaos_delivered=3:chaos_spent=3")
        turns = [int(t) for t in re.findall(r"^  Turn (\d+)", section, re.M)]
        self.assertEqual(turns, sorted(turns))

    # --- the curio by the name the player saw --------------------------------
    def placed_curio(self):
        self.append(
            event_row(1, 5, "session", "new")
            + event_row(2, 356, "curio", "admitted")
            + event_row(3, 707, "curio", "placed")
        )

    def test_placed_curio_is_named_as_the_player_saw_it(self):
        self.placed_curio()
        section, xlog = self.reveal_of("curio_placed", "curio_name=glass reed locket")
        self.assertIn(
            '    Effect: "glass reed locket" was placed on a new level on turn 707.\n',
            section,
        )
        self.assertNotIn("curio whistle", section)
        self.assertEqual(xlog, ":chaos_admitted=1:chaos_delivered=0:chaos_spent=3")

    def test_any_printable_name_survives_line_json_and_xlog(self):
        # Every character the validator admits (32..126), quotes, backslash,
        # colon and percent included: reveal_of() checks the JSON record
        # carries the rendered lines byte for byte.
        printable = "".join(chr(c) for c in range(33, 127))
        names = [
            'the "unclosed" square',
            "50% of a \\ key: maybe",
            " x ",
            "A" * 48,
            *(printable[i : i + 48] for i in range(0, len(printable), 48)),
        ]
        for name in names:
            with self.subTest(name=name):
                self.path.joinpath("events.jsonl").unlink(missing_ok=True)
                self.placed_curio()
                section, xlog = self.reveal_of("curio_placed", "curio_name=" + name)
                self.assertIn(f'    Effect: "{name}" was placed', section)
                self.assertEqual(
                    xlog, ":chaos_admitted=1:chaos_delivered=0:chaos_spent=3"
                )

    def test_without_an_engine_name_the_old_wording_stays(self):
        for host in (
            ("curio_placed",),  # an older save: no name reached the reveal
            ("curio_placed", "curio_name=" + "A" * 49),  # over 48: refused
            ("curio_placed", "curio_name=   "),  # blank: refused
            ("curio_placed", "curio_name=bad\ttab"),  # not printable: refused
        ):
            with self.subTest(host=host):
                self.path.joinpath("events.jsonl").unlink(missing_ok=True)
                self.placed_curio()
                section, _ = self.reveal_of(*host)
                self.assertIn(
                    "    Effect: a curio whistle was placed on a new level on turn 707.",
                    section,
                )

    # --- #165: FCFS budget refusal and haunt lifecycle end -----------------
    def test_haunting_budget_refusal_is_counted_never_narrated(self):
        # Only a budget refusal: no admission, so no section and no xlog.
        self.append(
            event_row(1, 5, "session", "new") + event_row(2, 20, "haunting", "budget")
        )
        self.assertEqual(self.reveal_of(), ("", ""))
        # With an admitted whisper the refusal joins the count line only.
        self.transport(REQUEST)
        section, xlog = self.reveal_of()
        self.assertEqual(len(self.entries(section)), 1, section)
        self.assertNotIn("haunting", section)
        self.assertNotIn("hound", section)
        self.assertNotIn("budget", section)
        self.assertEqual(
            [x for x in section.splitlines() if "refused" in x],
            ["  1 other candidate was refused; none took effect."],
        )
        self.assertEqual(xlog, ":chaos_admitted=1:chaos_delivered=1:chaos_spent=3")

    def test_haunting_budget_relogged_after_restore_counts_once(self):
        # chaos_haunt.c's budget_logged guard is a process static, not saved:
        # a restored game can log the same refusal again. One candidate.
        self.append(
            event_row(1, 5, "session", "new")
            + event_row(2, 20, "haunting", "budget")
            + event_row(3, 21, "session", "restore")
            + event_row(4, 22, "haunting", "budget")
        )
        self.transport(REQUEST)
        section, _ = self.reveal_of()
        self.assertEqual(
            [x for x in section.splitlines() if "refused" in x],
            ["  1 other candidate was refused; none took effect."],
        )
        # A new game is a new candidate.
        self.append(
            event_row(5, 1, "session", "new") + event_row(6, 20, "haunting", "budget")
        )
        self.transport(REQUEST)
        section, _ = self.reveal_of()
        self.assertIn("  1 other candidate was refused; none took effect.", section)

    def test_haunting_budget_then_admitted_is_not_refused(self):
        # Budget refusals consume nothing; if Sanity loss later grows the
        # budget and the same candidate is admitted, it was not refused.
        self.append(
            event_row(1, 5, "session", "new")
            + event_row(2, 20, "haunting", "budget")
            + event_row(3, 40, "haunting", "pre_admitted")
            + event_row(4, 40, "haunting", "accepted")
            + event_row(5, 41, "haunting", "budget")
        )
        section, xlog = self.reveal_of()
        self.assertEqual(len(self.entries(section)), 1, section)
        self.assertIn(
            "  Turn 40, after you doubled back: a haunting was admitted.", section
        )
        self.assertNotIn("refused", section)
        self.assertEqual(xlog, ":chaos_admitted=1:chaos_delivered=0:chaos_spent=3")

    def test_haunt_expired_row_ends_the_haunt_entry_at_its_turn(self):
        self.append(
            event_row(1, 5, "session", "new")
            + event_row(2, 30, "haunting", "pre_admitted")
            + event_row(3, 30, "haunting", "accepted")
            + event_row(4, 31, "haunt_step", "")
            + event_row(5, 90, "haunting", "expired")
        )
        # The host still reports the haunt active: the engine row wins.
        section, xlog = self.reveal_of("haunt_active")
        self.assertEqual(len(self.entries(section)), 1, section)
        self.assertIn("a haunting was admitted.", section)
        self.assertIn("    Ended: its hunt ended on turn 90.", section)
        self.assertNotIn("still hunting", section)
        self.assertNotIn("refused", section)
        self.assertEqual(xlog, ":chaos_admitted=1:chaos_delivered=1:chaos_spent=3")

    def test_haunt_expired_without_admission_is_ignored(self):
        # An expired row with no admitted haunt narrates and counts nothing.
        self.append(
            event_row(1, 5, "session", "new") + event_row(2, 90, "haunting", "expired")
        )
        self.assertEqual(self.reveal_of(), ("", ""))
        self.transport(REQUEST)
        section, _ = self.reveal_of()
        self.assertEqual(len(self.entries(section)), 1, section)
        self.assertNotIn("haunting", section)
        self.assertNotIn("refused", section)

    def test_haunt_without_expired_row_keeps_host_ending(self):
        self.append(
            event_row(1, 5, "session", "new") + event_row(2, 30, "haunting", "accepted")
        )
        section, _ = self.reveal_of("haunt_active")
        self.assertIn("Ended: still hunting when the game ended.", section)
        self.assertNotIn("its hunt ended on turn", section)

    def test_curio_application_before_placement_is_ignored(self):
        self.append(
            event_row(1, 20, "curio", "admitted")
            + event_row(2, 26, "curio", "applied requested=-3 actual=-2")
        )
        section, _ = self.reveal_of()
        self.assertIn("Delivered: no; you never applied it.", section)

    # --- next-use W/F: engine snapshot, observation roots and receipt -------
    def receipt(self, *rows):
        with (self.path / "next_use-receipt.jsonl").open("a") as stream:
            for row in rows:
                stream.write(json.dumps(row, separators=(",", ":")) + "\n")

    def test_next_use_w_delivered_names_its_origin(self):
        self.append(
            event_row(1, 5, "session", "new")
            + observation_row(12, 30, "whistling")
            + observation_row(13, 30, "whistling", "completed")
        )
        self.receipt({"next_use_private_v": 1, "kind": 1, "seq": 1})
        self.receipt({"next_use_private_v": 1, "kind": 2, "seq": 2})
        section, xlog = self.reveal_of(nu(W_ARMED, 0, 1, 1, 41, 12, 0, 3))
        self.assertIn("  Turn 41: a next-use program was admitted.", section)
        self.assertIn("    Origin: you whistled on DL3 on turn 30.", section)
        self.assertIn(
            'Telegraph: "The next whistle may call unusual attention."', section
        )
        self.assertIn("Effect: your next whistle armed it.", section)
        self.assertIn(
            "Delivered: yes, you saw your companion answer the whistle.", section
        )
        self.assertNotIn("Rebound", section)
        self.assertEqual(xlog, ":chaos_admitted=1:chaos_delivered=1:chaos_spent=3")

    def test_next_use_w_armed_but_unwitnessed_is_not_delivered(self):
        # Consumed and armed, but the engine never published a witness.
        self.append(observation_row(12, 30, "whistling"))
        section, xlog = self.reveal_of(nu(W_ARMED, 0, 0, 1, 41, 12))
        self.assertIn("Effect: your next whistle armed it.", section)
        self.assertIn("Delivered: no; no manifestation reached you.", section)
        self.assertNotIn("Delivered: yes", section)
        self.assertEqual(xlog, ":chaos_admitted=1:chaos_delivered=0:chaos_spent=3")

    def test_next_use_rebind_shows_published_and_bound_origins(self):
        # #177 receipt row: published origin 12, bound to the newer origin 20.
        self.append(
            observation_row(12, 30, "whistling") + observation_row(20, 55, "whistling")
        )
        self.receipt(
            {
                "next_use_private_v": 2,
                "kind": 2,
                "seq": 2,
                "origins": [{"family": "W", "published": 12, "bound": 20}],
            }
        )
        section, _ = self.reveal_of(nu(W_PENDING, 0, 0, 0, 60, 20, 0, 2))
        self.assertIn("    Origin: you whistled on DL2 on turn 55.", section)
        self.assertIn(
            "    Rebound: first written about an earlier one (turn 30).", section
        )
        self.assertTrue(all(len(x) <= 79 for x in section.splitlines()), section)
        self.assertIn("still waiting for your next whistle", section)
        self.assertIn("Ended: still pending when the game ended.", section)

    def test_next_use_f_applied_is_delivered_and_native_course_is_not(self):
        self.append(observation_row(7, 18, "fountain_drink"))
        section, xlog = self.reveal_of(nu(0, F_APPLIED, 0, 1, 25, 0, 7, 1))
        self.assertIn(
            "    Origin: you drank from a fountain on DL1 on turn 18.", section
        )
        self.assertIn(
            'Telegraph: "The next fountain drink may take a different course."', section
        )
        self.assertIn("Delivered: yes, you drank the changed water.", section)
        self.assertEqual(xlog, ":chaos_admitted=1:chaos_delivered=1:chaos_spent=3")
        section, xlog = self.reveal_of(nu(0, F_NATIVE, 0, 1, 25, 0, 7, 1))
        self.assertIn("your next fountain drink took its native course", section)
        self.assertIn("Delivered: no;", section)
        self.assertEqual(xlog, ":chaos_admitted=1:chaos_delivered=0:chaos_spent=3")

    def test_broad_whistle_program_counts_its_deliveries(self):
        # C: a broad program's slot keeps only its last use; delivery is the
        # engine's delivered count, not the last witness.
        self.append(observation_row(12, 30, "whistling"))
        section, xlog = self.reveal_of(nu(W_ARMED, 0, 0, 1, 41, 12, 0, 3), "broad=2,2")
        self.assertIn(
            '"For a while, your whistles may carry farther than they should."',
            section,
        )
        self.assertIn("any whistle could answer it, at most 2 times.", section)
        self.assertIn("Delivered: yes, 2 times; you saw your companion", section)
        self.assertIn("its uses ran out or it expired", section)
        self.assertNotIn("The next whistle", section)
        self.assertTrue(all(len(x) <= 79 for x in section.splitlines()), section)
        self.assertEqual(xlog, ":chaos_admitted=1:chaos_delivered=1:chaos_spent=3")

    def test_broad_fountain_program_undelivered_is_still_listening(self):
        self.append(observation_row(7, 18, "fountain_drink"))
        section, xlog = self.reveal_of(nu(0, F_NATIVE, 0, 0, 25, 0, 7, 1), "broad=2,0")
        self.assertIn(
            '"For a while, fountain water you drink may not run true."', section
        )
        self.assertIn("any fountain drink could answer it", section)
        self.assertIn("Delivered: no; no manifestation reached you.", section)
        self.assertIn("Ended: still listening when the game ended.", section)
        self.assertTrue(all(len(x) <= 79 for x in section.splitlines()), section)
        self.assertEqual(xlog, ":chaos_admitted=1:chaos_delivered=0:chaos_spent=3")

    def test_next_use_wf_pending_program(self):
        self.append(
            observation_row(7, 18, "fountain_drink")
            + observation_row(9, 22, "whistling")
        )
        section, _ = self.reveal_of(nu(W_PENDING, F_PENDING, 0, 0, 25, 9, 7))
        self.assertIn(
            'Telegraph: "The next whistle or fountain drink may not behave as usual."',
            section,
        )
        self.assertIn("    Origin: you whistled on turn 22.", section)
        self.assertIn("    Origin: you drank from a fountain on turn 18.", section)
        self.assertIn("Delivered: no;", section)

    # --- Arc 1: programs of one game, grouped by motif ----------------------
    def prior(self, *args):
        return "prior" + nu(*args)[2:]

    def test_single_program_render_is_unchanged_by_grouping(self):
        # Legacy shape: no Motif header, no program number, no Recurrence.
        self.append(observation_row(12, 30, "whistling"))
        section, _ = self.reveal_of(nu(W_ARMED, 0, 1, 1, 41, 12, 0, 3))
        self.assertIn("  Turn 41: a next-use program was admitted.", section)
        self.assertNotIn("Motif:", section)
        self.assertNotIn("program 1", section)
        self.assertNotIn("Recurrence", section)

    def test_two_whistle_programs_group_under_one_motif_with_recurrence(self):
        self.append(
            observation_row(12, 30, "whistling") + observation_row(40, 90, "whistling")
        )
        self.receipt(
            {
                "next_use_private_v": 2,
                "kind": 2,
                "seq": 2,
                "program_ordinal": 1,
                "origins": [{"family": "W", "published": 12, "bound": 12}],
            },
            {
                "next_use_private_v": 2,
                "kind": 2,
                "seq": 2,
                "program_ordinal": 2,
                "origins": [{"family": "W", "published": 40, "bound": 40}],
            },
        )
        section, xlog = self.reveal_of(
            self.prior(W_ARMED, 0, 1, 1, 41, 12, 0, 1),
            nu(W_ARMED, 0, 0, 1, 95, 40, 0, 1),
        )
        lines = section.splitlines()
        motif = lines.index("  Motif: the whistle, 2 programs, felt 1 time.")
        first = lines.index("  Turn 41: next-use program 1 was admitted.")
        second = lines.index("  Turn 95: next-use program 2 was admitted.")
        self.assertLess(motif, first)
        self.assertLess(first, second)
        # Recurrence only on program 2, and only because program 1 was felt.
        recurrence = (
            '    Recurrence: "Again, the whistle carries farther than it should."'
        )
        self.assertEqual(lines.count(recurrence), 1)
        self.assertGreater(lines.index(recurrence), second)
        self.assertEqual(len(self.entries(section)), 2)
        self.assertNotIn("Rebound", section)
        self.assertTrue(all(len(x) <= 79 for x in lines), section)
        self.assertEqual(xlog, ":chaos_admitted=2:chaos_delivered=1:chaos_spent=3")

    def test_unfelt_first_program_gives_no_recurrence(self):
        self.append(
            observation_row(12, 30, "whistling") + observation_row(40, 90, "whistling")
        )
        section, xlog = self.reveal_of(
            self.prior(W_ARMED, 0, 0, 1, 41, 12, 0, 1),
            nu(W_ARMED, 0, 1, 1, 95, 40, 0, 1),
        )
        self.assertIn("  Motif: the whistle, 2 programs, felt 1 time.", section)
        self.assertNotIn("Recurrence", section)
        self.assertEqual(xlog, ":chaos_admitted=2:chaos_delivered=1:chaos_spent=3")

    def test_mixed_families_form_two_motifs_in_first_seen_order(self):
        self.append(
            observation_row(7, 18, "fountain_drink")
            + observation_row(12, 30, "whistling")
            + observation_row(30, 70, "fountain_drink")
        )
        section, _ = self.reveal_of(
            self.prior(0, F_APPLIED, 0, 1, 25, 0, 7, 1),
            self.prior(W_ARMED, 0, 0, 1, 41, 12, 0, 1),
            nu(0, F_NATIVE, 0, 1, 80, 0, 30, 2),
        )
        lines = section.splitlines()
        fountain = lines.index("  Motif: the fountain, 2 programs, felt 1 time.")
        whistle = lines.index("  Motif: the whistle, 1 program, felt 0 times.")
        self.assertLess(fountain, whistle)
        order = [x for x in lines if x.startswith("  Turn ")]
        self.assertEqual(
            order,
            [
                "  Turn 25: next-use program 1 was admitted.",
                "  Turn 80: next-use program 3 was admitted.",
                "  Turn 41: next-use program 2 was admitted.",
            ],
        )
        self.assertEqual(
            lines.count(
                '    Recurrence: "Again, the fountain\'s water may not run true."'
            ),
            1,
        )
        self.assertNotIn("Again, the whistle", section)

    def test_rejected_next_use_candidate_is_one_count_line(self):
        # A refused next-use candidate is never an entry: no admission in the
        # snapshot, only the engine's recorded decision rows.
        self.append(observation_row(12, 30, "whistling"))
        self.receipt(
            {
                "next_use_decision_v": 1,
                "decision": "rejected",
                "at": 2,
                "safe": 2,
                "move": 50,
                "reasons": ["origin_superseded"],
            }
        )
        self.assertEqual(self.reveal_of("next_use_rejected"), ("", ""))
        self.transport(REQUEST)
        section, _ = self.reveal_of("next_use_rejected")
        self.assertEqual(len(self.entries(section)), 1, section)
        self.assertNotIn("next-use", section)
        self.assertNotIn("origin_superseded", section)
        self.assertEqual(
            [x for x in section.splitlines() if "refused" in x],
            ["  1 other candidate was refused; none took effect."],
        )

    def test_unqualified_origin_without_admission_is_not_narrated(self):
        # Origins alone (a whistle the Chaos watched) never become entries.
        self.append(
            observation_row(12, 30, "whistling")
            + observation_row(14, 31, "fountain_drink")
        )
        self.receipt({"next_use_private_v": 2, "kind": 1, "seq": 1})
        self.assertEqual(self.reveal_of(), ("", ""))

    def test_model_rationale_is_never_rendered(self):
        # Director-side files are not engine records; nothing from them shows.
        (self.path / "next_use-schedule.jsonl").write_text(
            '{"rationale":"I will make the dog betray them"}\n'
        )
        (self.path / "next_use-envelope.json").write_text('{"note":"intent"}')
        self.transport(REQUEST)
        section, _ = self.reveal_of()
        self.assertNotIn("betray", section)
        self.assertNotIn("intent", section)

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
            self.assertIsNone(re.search(r"\b(rn\w*|rnd|d)\(", text), name)


if __name__ == "__main__":
    unittest.main()
