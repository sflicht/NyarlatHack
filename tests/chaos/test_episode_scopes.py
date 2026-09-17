"""ENGINE-UNIT: freshly compile real engine, IO and protocol with native headers.

Host globals/stubs are not a linked game. Delivery commands only simulate scope
flags, not actual pline/map delivery, action purity, RNG or gameplay acceptance.
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from chaos.episodes import project_episodes

ROOT = Path(__file__).resolve().parents[2]


class EpisodeScopesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="nyarl-obs5b-build-")
        cls.addClassCleanup(cls.build.cleanup)
        cls.binary = Path(cls.build.name) / "scopes"
        cls.logs = Path(tempfile.mkdtemp(prefix="nyarl-obs5b-evidence-"))
        command = [
            "/usr/bin/gcc",
            "-DCHAOS",
            "-ffunction-sections",
            "-fdata-sections",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-isystem",
            str(ROOT / "include"),
            str(ROOT / "tests/chaos/episode_scopes.c"),
            *(
                str(ROOT / "src" / f)
                for f in ("chaos_engine.c", "chaos_io.c", "chaos_protocol.c")
            ),
            "-Wl,--gc-sections",
            "-Wl,--wrap=write",
            "-Wl,--wrap=fsync",
            "-o",
            str(cls.binary),
        ]
        result = subprocess.run(command, capture_output=True, timeout=30)
        (cls.logs / "compile.json").write_text(
            json.dumps(
                {
                    "command": command,
                    "returncode": result.returncode,
                    "stdout": result.stdout.decode(),
                    "stderr": result.stderr.decode(),
                    "sources": {
                        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in [
                            ROOT / "tests/chaos/episode_scopes.c",
                            ROOT / "include/chaos.h",
                            *[
                                ROOT / "src" / f
                                for f in (
                                    "chaos_engine.c",
                                    "chaos_io.c",
                                    "chaos_protocol.c",
                                )
                            ],
                        ]
                    },
                },
                indent=2,
            )
        )
        if result.returncode:
            raise RuntimeError(result.stderr.decode())
        print(f"ENGINE-UNIT evidence: {cls.logs}")

    def run_scope(self, commands, flag="1", directory=True):
        with tempfile.TemporaryDirectory(prefix="nyarl-obs5b-run-") as tmp:
            env = {
                k: v for k, v in os.environ.items() if not k.startswith("NYARLATHACK_")
            }
            if directory:
                env["NYARLATHACK_RUN_DIR"] = tmp
            if flag is not None:
                env["NYARLATHACK_OBSERVATIONS"] = flag
            result = subprocess.run(
                [str(self.binary)],
                input=commands.encode(),
                capture_output=True,
                env=env,
                timeout=10,
            )
            path = Path(tmp) / "events.jsonl"
            raw = path.read_bytes() if path.exists() else b""
            index = len(list(self.logs.glob("run-*.json")))
            (self.logs / f"run-{index}.json").write_text(
                json.dumps(
                    {
                        "commands": commands,
                        "flag": flag,
                        "directory": directory,
                        "stdout": result.stdout.decode(),
                        "stderr": result.stderr.decode(),
                        "returncode": result.returncode,
                        "events": raw.decode(),
                        "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
                    },
                    indent=2,
                )
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stderr, b"")
            return (
                raw,
                [json.loads(line) for line in raw.splitlines()],
                result.stdout.decode(),
            )

    def test_opt_in_marker_before_legacy_session(self):
        _, rows, _ = self.run_scope("start")
        self.assertEqual(
            [r["event"] for r in rows],
            ["observation", "session", "level_enter", "safe_point"],
        )
        self.assertEqual(
            rows[0]["observation"],
            dict(operation="none", stage="enabled", root_seq=0, fact="none"),
        )
        self.assertEqual([r["seq"] for r in rows], [1, 2, 3, 4])

    def test_off_legacy_independent_byte_golden(self):
        expected = b""
        for seq, name, detail, safe in [
            (1, "session", "new", 0),
            (2, "level_enter", "", 0),
            (3, "safe_point", "level_enter", 1),
        ]:
            row = dict(
                v=1,
                seq=seq,
                turn=1,
                safe=safe,
                event=name,
                phase="result",
                detail=detail,
                sanity=60,
                insight=4,
                budget=6,
                spent=0,
                reserved=0,
                last_id=0,
                vitals=dict(hp=7, hp_max=20, power=2, power_max=10),
            )
            expected += json.dumps(row, separators=(",", ":")).encode() + b"\n"
        for flag in [None, "0", "true", "01", ""]:
            with self.subTest(flag=flag):
                raw, _, output = self.run_scope(
                    "start begin 1 arm 1 1 take deliver block map end", flag
                )
                self.assertEqual(raw, expected)
                self.assertIn("end 0 3 1 0 0 0 0", output)

    def test_owned_root_interleaved_legacy_and_duplicate_end(self):
        raw, rows, output = self.run_scope("start begin 1 event apply end end")
        self.assertEqual(
            [r["event"] for r in rows[4:]], ["observation", "apply", "observation"]
        )
        self.assertEqual(rows[4]["observation"]["stage"], "started")
        self.assertEqual(rows[6]["observation"]["root_seq"], rows[4]["seq"])
        self.assertIn("begin 5 5 1 0 0 0 0", output)
        self.assertEqual(
            project_episodes(raw)["coverage"]["completed_without_notice"]["count"], 1
        )

    def test_new_begin_owns_end(self):
        _, rows, _ = self.run_scope("start begin 1 begin 2 oldend end")
        self.assertEqual(
            [r["observation"]["stage"] for r in rows[4:]],
            ["started", "started", "completed"],
        )
        self.assertEqual(rows[-1]["observation"]["root_seq"], 6)

    def test_boundaries_and_turn_clear_scope(self):
        for boundary in [
            "turn",
            "event session",
            "event level_enter",
            "event level_leave",
            "event death",
            "shadow event level_enter shadow",
        ]:
            with self.subTest(boundary=boundary):
                _, rows, _ = self.run_scope(f"start begin 1 {boundary} end")
                self.assertEqual(
                    [r["observation"]["stage"] for r in rows[4:] if r["v"] == 2],
                    ["started"],
                )

    def test_one_delivered_message_each_closed_fact(self):
        for operation, facts in [(1, range(1, 6)), (2, range(6, 9))]:
            for fact in facts:
                with self.subTest(operation=operation, fact=fact):
                    raw, rows, _ = self.run_scope(
                        f"start begin {operation} arm {operation} {fact} take "
                        "deliver deliver arm 1 1 take deliver end"
                    )
                    self.assertEqual(
                        [r["observation"]["stage"] for r in rows[4:]],
                        ["started", "notice", "blocked" if fact == 8 else "completed"],
                    )
                    projected = project_episodes(raw)
                    if fact != 8:
                        self.assertEqual(projected["episodes"][0]["count"], 1)

    def test_map_and_message_channels(self):
        raw, rows, out = self.run_scope(
            "start begin 2 arm 2 9 take deliver take_map map map end"
        )
        self.assertIn("take 5 5 1 0 0 0 0", out)
        self.assertEqual(rows[-2]["observation"]["fact"], "detection_presented")
        self.assertEqual(project_episodes(raw)["episodes"][0]["count"], 1)

    def test_unarmed_invalid_disarmed_and_wrong_channel_delivery(self):
        for commands in [
            "fake 1",
            "arm 1 1 deliver",
            "arm 1 1 map",
            "arm 1 1 take disarm deliver",
            "arm 2 6 take deliver",
            "arm 1 9 take deliver map",
            "arm 1 0 take deliver",
            "arm 1 99 take deliver",
            "arm 1 1 take take deliver",
        ]:
            with self.subTest(commands=commands):
                _, rows, _ = self.run_scope(f"start begin 1 {commands} end")
                self.assertEqual(
                    [r["observation"]["stage"] for r in rows[4:]],
                    ["started", "completed"],
                )

    def test_blocked_with_and_without_notice(self):
        for notice in ["", "arm 2 8 take deliver"]:
            raw, rows, _ = self.run_scope(f"start begin 2 block {notice} end")
            self.assertEqual(rows[-1]["observation"]["stage"], "blocked")
            self.assertEqual(project_episodes(raw)["coverage"]["blocked"]["count"], 1)
        _, rows, _ = self.run_scope("start begin 1 block end")
        self.assertEqual(rows[-1]["observation"]["stage"], "completed")

    def test_start_sampling_restore_and_absent_directory(self):
        _, rows, _ = self.run_scope("restore start env 0 start begin 1 end")
        self.assertEqual([r["seq"] for r in rows], [21, 22, 23, 24])
        self.assertEqual(rows[1]["detail"], "restore")
        for row in rows:
            self.assertEqual((row["safe"], row["spent"], row["last_id"]), (7, 1, 3))
        _, rows, _ = self.run_scope("start env 1 start begin 1 end", "0")
        self.assertEqual(len(rows), 3)
        raw, _, _ = self.run_scope(
            "start begin 1 arm 1 1 take deliver end", directory=False
        )
        self.assertEqual(raw, b"")

    def test_suppressed_contexts_and_invalid_operations(self):
        for prefix in ["", "shadow start", "dead start"]:
            _, rows, _ = self.run_scope(
                prefix + " begin 1 arm 1 1 take deliver map block end"
            )
            self.assertFalse(any(r["v"] == 2 for r in rows))
        for guard in ["shadow", "dead"]:
            _, rows, _ = self.run_scope(
                f"start begin 1 arm 1 1 take {guard} deliver end"
            )
            self.assertEqual(len(rows), 5)
        for operation in [-1, 0, 3, 999]:
            _, rows, _ = self.run_scope(f"start begin {operation} end")
            self.assertEqual(len(rows), 4)

    def test_context_uses_existing_vitals_and_no_game_state_mutation(self):
        for setup, hp, maximum in [
            ("", 7, 20),
            ("multi", 7, 20),
            ("nonfood", 7, 20),
            ("poly", 0, 30),
        ]:
            raw, rows, _ = self.run_scope(
                f"{setup} start begin 1 arm 1 1 take deliver end"
            )
            self.assertEqual(
                rows[-1]["vitals"], dict(hp=hp, hp_max=maximum, power=2, power_max=10)
            )
            self.assertEqual(project_episodes(raw)["episodes"][0]["count"], 1)

    def test_stale_tokens_and_nested_take_cannot_invent_notice(self):
        for middle in [
            "begin 1",
            "turn",
            "event level_leave",
            "disarm",
            "arm 1 2",
            "arm 2 6",
            "begin 2 arm 2 6",
        ]:
            _, rows, _ = self.run_scope(
                f"start begin 1 arm 1 1 take {middle} deliver end"
            )
            self.assertFalse(
                any(r.get("observation", {}).get("stage") == "notice" for r in rows)
            )
        # Nested vpline sees zero, while the outer caller retains its local token.
        _, rows, out = self.run_scope("start begin 1 arm 1 1 take take fake 1 end")
        self.assertIn("take 5 5 1 0 0 0 0", out)
        self.assertEqual(rows[-2]["observation"]["fact"], "sound_high")

    def test_write_and_fsync_failures_at_every_record(self):
        cases = [
            ("fault {w} {s} start", 0),
            ("start fault {w} {s} begin 1", 4),
            ("start begin 1 arm 1 1 take fault {w} {s} deliver", 5),
            ("start begin 1 fault {w} {s} end", 5),
        ]
        for template, successful in cases:
            for w, s in [(1, 0), (0, 1)]:
                with self.subTest(template=template, w=w, s=s):
                    commands = template.format(w=w, s=s)
                    _, rows, out = self.run_scope(
                        commands + " end end begin 2 arm 2 6 take deliver end"
                    )
                    # A failed fsync can leave bytes, but must NOT own their seq.
                    self.assertEqual(len(rows), successful + s)
                    self.assertEqual(int(out.splitlines()[-1].split()[2]), successful)
                    self.assertEqual(int(out.splitlines()[-1].split()[1]), 0)

    def test_failed_new_begin_clears_old_owner_and_overflow(self):
        for fault in ["fault 1 0", "fault 0 1", "overflow"]:
            _, rows, out = self.run_scope(
                f"start begin 1 arm 1 1 take {fault} begin 2 oldend deliver end"
            )
            self.assertNotIn('"stage": "notice"', json.dumps(rows))
            self.assertIn("begin 0 ", out)

    def test_identical_fact_message_reentry_rejects_old_token(self):
        self.check_identical_fact_reentry(1, 1, "take", "deliver")

    def test_identical_fact_map_reentry_rejects_old_token(self):
        self.check_identical_fact_reentry(2, 9, "take_map", "map")

    def check_identical_fact_reentry(self, operation, fact, take, deliver):
        _, rows, output = self.run_scope(
            f"start begin {operation} arm {operation} {fact} {take} save_token "
            f"begin {operation} arm {operation} {fact} {take} swap_token "
            f"{deliver} swap_token {deliver} end"
        )
        deliveries = [
            line.split()
            for line in output.splitlines()
            if line.startswith(deliver + " ")
        ]
        self.assertEqual([int(line[2]) for line in deliveries], [6, 7])
        notices = [r for r in rows if r.get("observation", {}).get("stage") == "notice"]
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0]["observation"]["root_seq"], 6)

    def test_map_requires_taken_token(self):
        for delivery in ["map", "token 5 9 map"]:
            with self.subTest(delivery=delivery):
                _, rows, _ = self.run_scope(f"start begin 2 arm 2 9 {delivery} end")
                self.assertEqual(
                    [r["observation"]["stage"] for r in rows[4:]],
                    ["started", "completed"],
                )

    def test_forged_root_or_fact_preserves_taken_pending(self):
        for operation, fact, take, deliver in [
            (1, 1, "take", "deliver"),
            (2, 9, "take_map", "map"),
        ]:
            invalid = [(root, fact) for root in [0, -1, 4, 6]]
            invalid += [(5, wrong) for wrong in [-1, 0, 2, 6, 8, 99]]
            invalid += [(5, 9 if fact == 1 else 1)]
            for root, wrong in invalid:
                with self.subTest(operation=operation, root=root, fact=wrong):
                    _, rows, out = self.run_scope(
                        f"start begin {operation} arm {operation} {fact} {take} "
                        f"save_token token {root} {wrong} {deliver} swap_token "
                        f"{deliver} {deliver} end"
                    )
                    self.assertEqual(
                        [
                            int(line.split()[2])
                            for line in out.splitlines()
                            if line.startswith(deliver + " ")
                        ],
                        [5, 6, 6],
                    )
                    self.assertEqual(
                        [r["observation"]["stage"] for r in rows[4:]],
                        ["started", "notice", "completed"],
                    )

    def test_nested_and_wrong_channel_takes_do_not_steal_token(self):
        for operation, fact, take, other, deliver, wrong in [
            (1, 1, "take", "take_map", "deliver", "map"),
            (2, 9, "take_map", "take", "map", "deliver"),
        ]:
            with self.subTest(operation=operation):
                _, rows, out = self.run_scope(
                    f"start begin {operation} arm {operation} {fact} "
                    f"{other} empty_token {take} save_token {take} empty_token "
                    f"{other} empty_token swap_token {wrong} {deliver} {deliver} end"
                )
                self.assertEqual(
                    [r["observation"]["stage"] for r in rows[4:]],
                    ["started", "notice", "completed"],
                )
                self.assertIn(f"{wrong} 5 5 1 0 0 0 {fact}", out)

    def test_boundary_reentry_old_tokens_do_not_consume_new_pending(self):
        for operation, fact, take, deliver in [
            (1, 1, "take", "deliver"),
            (2, 9, "take_map", "map"),
        ]:
            for boundary in [
                "turn",
                "event session",
                "event level_enter",
                "event level_leave",
                "event death",
                "shadow event level_enter shadow",
            ]:
                with self.subTest(operation=operation, boundary=boundary):
                    _, rows, out = self.run_scope(
                        f"start begin {operation} arm {operation} {fact} {take} "
                        f"save_token {boundary} begin {operation} "
                        f"arm {operation} {fact} {take} swap_token {deliver} "
                        f"swap_token {deliver} end"
                    )
                    roots = [
                        r["seq"]
                        for r in rows
                        if r.get("observation", {}).get("stage") == "started"
                    ]
                    self.assertEqual(
                        [
                            int(line.split()[2])
                            for line in out.splitlines()
                            if line.startswith(deliver + " ")
                        ],
                        [roots[-1], roots[-1] + 1],
                    )
                    notices = [
                        r
                        for r in rows
                        if r.get("observation", {}).get("stage") == "notice"
                    ]
                    self.assertEqual(len(notices), 1)
                    self.assertEqual(notices[0]["observation"]["root_seq"], roots[-1])

    def test_both_channels_reject_invalidated_delivery_and_take(self):
        for operation, fact, take, deliver in [
            (1, 1, "take", "deliver"),
            (2, 9, "take_map", "map"),
        ]:
            for guard in [
                "disarm",
                "end",
                "turn",
                "dead",
                "shadow",
                "event level_leave",
                "begin 2",
            ]:
                for taken in [True, False]:
                    with self.subTest(operation=operation, guard=guard, taken=taken):
                        commands = f"start begin {operation} arm {operation} {fact} "
                        commands += (
                            f"{take} {guard}"
                            if taken
                            else f"{guard} {take} empty_token"
                        )
                        _, rows, _ = self.run_scope(f"{commands} {deliver} end")
                        self.assertFalse(
                            any(
                                r.get("observation", {}).get("stage") == "notice"
                                for r in rows
                            )
                        )

    def test_tokens_from_different_channel_do_not_consume_new_pending(self):
        for old_fact, fact, take, old_take, deliver in [
            (6, 9, "take_map", "take", "map"),
            (9, 6, "take", "take_map", "deliver"),
        ]:
            with self.subTest(fact=fact):
                _, rows, out = self.run_scope(
                    f"start begin 2 arm 2 {old_fact} {old_take} save_token "
                    f"begin 2 arm 2 {fact} {take} swap_token {deliver} "
                    f"swap_token {deliver} end"
                )
                self.assertEqual(
                    [
                        int(line.split()[2])
                        for line in out.splitlines()
                        if line.startswith(deliver + " ")
                    ],
                    [6, 7],
                )
                self.assertEqual(rows[-2]["observation"]["root_seq"], 6)

    def test_chaos_off_real_header_macros(self):
        source = Path(self.build.name) / "off.c"
        source.write_text("""#include "chaos.h"
int main(void) {
    int touched = 0;
    long root = chaos_observation_begin(++touched);
    chaos_observation_end(++touched);
    chaos_observation_arm(++touched, ++touched);
    chaos_observation_disarm();
    chaos_observation_delivered(((struct chaos_observation_token){++touched, ++touched}));
    chaos_observation_map_delivered(((struct chaos_observation_token){++touched, ++touched}));
    chaos_observation_blocked();
    struct chaos_observation_token message = chaos_observation_take_message();
    struct chaos_observation_token map = chaos_observation_take_map();
    return touched || root || message.root || message.fact || map.root || map.fact
        || CHAOS_OBS_OP_WHISTLING != 1;
}
""")
        binary = source.with_suffix("")
        command = [
            "/usr/bin/gcc",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-isystem",
            str(ROOT / "include"),
            str(source),
            "-o",
            str(binary),
        ]
        result = subprocess.run(command, capture_output=True, timeout=30)
        (self.logs / "off-compile.json").write_text(
            json.dumps(
                {
                    "command": command,
                    "stdout": result.stdout.decode(),
                    "stderr": result.stderr.decode(),
                    "returncode": result.returncode,
                }
            )
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        result = subprocess.run([str(binary)], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
