"""Task 8b: ordinary discovery, real saved bytes, transport-off fresh execs.

Handwritten Task 8a SOURCE/NOTE/DISCOVERY, not model output. No game wrappers,
state injection, seed search, launcher, director or hidden-map navigation. The
standalone C helper reports the compiled headers' layout only; native save.c
serializes u, and these tests read its actual preserved file after process exit.
Player-record bytes are NOT snapshots of every physical object field. Successful
native inspect/apply plus conserved owner ID support the binding inference.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from gameplay_support import ANSI, ROOT, Game
from test_curio_gameplay import DISCOVERY, NOTE, SOURCE
from chaos import curio_continuity as continuity
from chaos.curio_store import install_saved_source, store_candidate


def sha(data):
    return hashlib.sha256(data).hexdigest()


def integer(data, field, schema, signed=False):
    start, size = field["offset"], field["size"]
    assert len(data[start : start + size]) == size, "truncated integer"
    return int.from_bytes(
        data[start : start + size], schema["byteorder"], signed=signed
    )


def saved_record(test, data, schema, charges, state, owner=None):
    """Fail closed: verified native header, unique exact source, bounded u image."""
    test.assertFalse(schema["external_compression"])
    test.assertFalse(schema["internal_compression"])
    test.assertGreaterEqual(len(data), schema["save_header_size"])
    for name, value in schema["save_header_values"].items():
        test.assertEqual(
            integer(data, schema["save_header"][name], schema), value, name
        )
    test.assertEqual(data.count(SOURCE), 1, "exact source must occur uniquely")
    start = data.index(SOURCE) - schema["record"]["source"]["offset"]
    test.assertGreaterEqual(start, schema["save_header_size"])
    record = data[start : start + schema["record_size"]]
    test.assertEqual(len(record), schema["record_size"])
    fields: dict = {
        name: integer(
            record,
            schema["record"][name],
            schema,
            name in ("charges", "state", "disabled"),
        )
        for name in (
            "version",
            "phase",
            "source_len",
            "owner",
            "charges",
            "state",
            "disabled",
        )
    }
    test.assertEqual(fields["version"], schema["version"])
    test.assertEqual(fields["phase"], schema["placed"])
    test.assertEqual(fields["source_len"], len(SOURCE))
    test.assertGreater(fields["owner"], 0)
    if owner is not None:
        test.assertEqual(fields["owner"], owner, "owner changed")
    test.assertEqual(
        (fields["charges"], fields["state"], fields["disabled"]), (charges, state, 0)
    )
    for name, expected in (("name", b"Offline counter"), ("source", SOURCE)):
        f = schema["record"][name]
        test.assertEqual(
            record[f["offset"] : f["offset"] + f["size"]],
            expected.ljust(f["size"], b"\0"),
            name,
        )
    you_start = start - schema["you"]["curio"]["offset"]
    test.assertGreaterEqual(you_start, schema["save_header_size"])
    player = data[you_start : you_start + schema["you_size"]]
    test.assertEqual(len(player), schema["you_size"])
    fields["sanity"] = integer(player, schema["you"]["usanity"], schema, True)
    fields["insight"] = integer(player, schema["you"]["uinsight"], schema, True)
    fields["spent"] = integer(
        player,
        {
            "offset": schema["you"]["chaos"]["offset"] + schema["spent_offset"],
            "size": schema["spent_size"],
        },
        schema,
        True,
    )
    test.assertEqual(fields["spent"], 1)
    fields.update(
        record_offset=start,
        player_offset=you_start,
        record_sha256=sha(record),
        save_sha256=sha(data),
    )
    return record, fields


def assert_record_delta(test, before, after, schema, charges, state):
    """Whole-byte oracle: only the two explicitly expected integer edits."""
    expected = bytearray(before)
    for name, value in (("charges", charges), ("state", state)):
        f = schema["record"][name]
        expected[f["offset"] : f["offset"] + f["size"]] = value.to_bytes(
            f["size"], schema["byteorder"], signed=True
        )
    test.assertEqual(bytes(expected), after, "unexpected owned-record byte change")


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class CurioRestartGameplayTests(unittest.TestCase):
    def test_ordinary_saved_owner_uses_without_event_transport(self):
        self.assertEqual((ROOT / ".chaos-build").read_text().strip(), "1")
        root = Path(tempfile.mkdtemp(prefix="curio8b-green-"))
        print("CURIO8B_ARTIFACTS=" + str(root), flush=True)
        inputs = [
            Path(__file__),
            ROOT / "tests/chaos/curio_save_layout.c",
            ROOT / "tests/chaos/test_curio_gameplay.py",
            ROOT / "tests/chaos/gameplay_support.py",
            ROOT / "tests/chaos/replay_clock.c",
        ]
        protected = (
            inputs
            + sorted((ROOT / "include").glob("*.h"))
            + [
                ROOT / "src" / name
                for name in (
                    "save.c",
                    "restore.c",
                    "chaos_curio.c",
                    "chaos_engine.c",
                    "chaos_io.c",
                )
            ]
            + [ROOT / "dnethackdir" / name for name in ("dnethack", "nhdat", "license")]
        )
        hashes = {str(p): sha(p.read_bytes()) for p in protected}
        (root / "protected-before.json").write_text(json.dumps(hashes, indent=2))
        for p in inputs:
            shutil.copy2(p, root / p.name)
        clock, layout = root / "clock.so", root / "layout"
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
                str(clock),
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
        (root / "build-commands.json").write_text(json.dumps(commands, indent=2))
        for command in commands:
            result = subprocess.run(command, capture_output=True, timeout=30)
            with (root / "build.log").open("ab") as f:
                f.write(result.stdout + result.stderr)
            self.assertEqual(result.returncode, 0, result.stderr)
        output = subprocess.check_output([str(layout)], timeout=5)
        (root / "layout.json").write_bytes(output)
        schema = json.loads(output)
        g = Game(ROOT / "dnethackdir", clock, wizard=False, root=root / "session")
        self.addCleanup(g.close)
        bundles, journal = root / "bundles", root / "journal"
        bundles.mkdir(mode=0o700)
        journal.mkdir(mode=0o700)
        continuity.create_journal(journal)
        candidate = store_candidate(
            bundles,
            json.dumps({"lua_source": SOURCE.decode(), "continuity_note": NOTE}),
        )
        self.assertEqual(candidate.candidate_id, sha(SOURCE))
        continuity.register(journal, bundles, candidate.candidate_id)
        receipt = install_saved_source(
            g.run, bundle_root=bundles, candidate_id=candidate.candidate_id
        )
        continuity.bind_run(journal, candidate.candidate_id, g.run)
        self.assertEqual(
            install_saved_source(
                g.run,
                bundle_root=bundles,
                candidate_id=candidate.candidate_id,
                mode="verify",
            ),
            receipt,
        )
        self.assertFalse((g.run / "events.jsonl").exists())
        snapshots, actions, environments = {}, {}, []

        def native_environment():
            self.assertIsNotNone(g.pid)
            env = dict(
                part.split(b"=", 1)
                for part in Path(f"/proc/{g.pid}/environ").read_bytes().split(b"\0")
                if b"=" in part
            )
            # Do not preserve unrelated inherited environment (may contain keys).
            selected: dict = {
                key: env.get(key.encode(), b"").decode()
                for key in ("NYARLATHACK_RUN_DIR", "LD_PRELOAD", "NETHACKOPTIONS", "TZ")
            }
            selected["run_dir_present"] = b"NYARLATHACK_RUN_DIR" in env
            selected["argv"] = [
                arg.decode()
                for arg in Path(f"/proc/{g.pid}/cmdline").read_bytes().split(b"\0")
                if arg
            ]
            self.assertEqual(selected["argv"], ["./dnethack"])
            self.assertEqual(selected["run_dir_present"], g.observe)
            selected["pid"] = g.pid
            selected["exe_sha256"] = sha(Path(f"/proc/{g.pid}/exe").read_bytes())
            self.assertEqual(
                selected["exe_sha256"], hashes[str(ROOT / "dnethackdir/dnethack")]
            )
            self.assertEqual(
                selected["NYARLATHACK_RUN_DIR"], str(g.run) if g.observe else ""
            )
            environments.append(selected)
            (root / "session-env.json").write_text(json.dumps(environments, indent=2))

        def response(name, command):
            start = len(g.raw)
            g.more(g.send(command))
            raw = bytes(g.raw[start:])
            (root / (name + ".raw")).write_bytes(raw)
            return ANSI.sub(b"", raw)

        def turn(name):
            output = response(name, b"\x12")
            values = re.findall(rb"T:(\d+)", output)
            self.assertTrue(values, output)
            return int(values[-1])

        def inspect(name):
            before = turn(name + "-before")
            start = len(g.raw)
            g.send("i")
            self.assertIn(b"s - an Offline counter", g.send(" "))
            menu = g.send("s")
            self.assertIn(b"I - Describe this item", menu)
            self.assertIn(b"a - Apply", menu)
            self.assertIn(b"A plain counter with three stages.", g.send("I"))
            g.more(g.send(" "))
            raw = bytes(g.raw[start:])
            (root / (name + ".raw")).write_bytes(raw)
            self.assertNotIn(b"whistle", raw.lower())
            self.assertNotIn(b"This spends one use.", raw)
            self.assertEqual(turn(name + "-after"), before)
            actions[name] = {"before": before, "after": before}

        def apply(name, stage, delta):
            before = turn(name + "-before")
            # TTY wraps the fixed warning at column 80. Preserve raw pages,
            # normalize only whitespace for the prose presence/order oracle.
            output = re.sub(rb"\s+", b" ", response(name, "as"))
            warning = f"The curio requests a Sanity change of {delta:+d}; native limits may reduce it.".encode()
            self.assertEqual(output.count(warning), 1, output)
            self.assertEqual(output.count(b"This spends one use."), 1, output)
            self.assertEqual(output.count(stage), 1, output)
            self.assertLess(output.index(warning), output.index(stage))
            self.assertLess(output.index(b"This spends one use."), output.index(stage))
            self.assertNotIn(b"inert", output)
            after = turn(name + "-after")
            self.assertEqual(after, before + 1)
            actions[name] = {"before": before, "after": after, "delta": delta}

        def snapshot(name, charges, state, sanity, previous=None):
            saved_turn = turn(name + "-save-boundary")
            self.assertEqual(g.save(), 0)
            self.assertIsNone(g.pid)
            self.assertIsNone(g.fd)
            dest = root / name
            dest.mkdir()
            saves = [p for p in (g.game / "save").iterdir() if p.is_file()]
            self.assertEqual(len(saves), 1, saves)
            # Preserve the actual native save BEFORE restore consumes it.
            data = saves[0].read_bytes()
            (dest / "native.savefile").write_bytes(data)
            for filename in ("terminal.raw", "inputs.json", "manifest.json"):
                shutil.copy2(g.root / filename, dest / filename)
            shutil.copytree(g.run, dest / "run")
            owner = snapshots["first"]["fields"]["owner"] if snapshots else None
            record, fields = saved_record(self, data, schema, charges, state, owner)
            self.assertEqual(fields["sanity"], sanity)
            (dest / "record.bin").write_bytes(record)
            (dest / "fields.json").write_text(json.dumps(fields, indent=2))
            if previous:
                assert_record_delta(
                    self, snapshots[previous]["record"], record, schema, charges, state
                )
            snapshots[name] = {
                "record": record,
                "fields": fields,
                "saved_turn": saved_turn,
            }
            return data

        def restart(name):
            self.assertFalse(g.observe)
            start = len(g.raw)
            g.start()
            native_environment()
            output = ANSI.sub(b"", bytes(g.raw[start:]))
            (root / (name + "-startup.raw")).write_bytes(bytes(g.raw[start:]))
            self.assertNotIn(b"Configuration incompatibility", output)
            self.assertNotIn(b"An uncanny curio may appear", output)
            self.assertFalse(
                list((g.game / "save").iterdir()), "restore did not consume native save"
            )
            self.assertEqual((g.run / "events.jsonl").read_bytes(), native_events)
            restored_turn = turn(name + "-redraw")
            saved_turn = list(snapshots.values())[-1]["saved_turn"]
            self.assertEqual(
                restored_turn, saved_turn, "save/restart changed native turn"
            )
            actions[name] = {"saved_turn": saved_turn, "restore_turn": restored_turn}

        g.start()
        native_environment()
        events = g.events()
        self.assertEqual(events[0]["detail"], "new")
        admitted = [e for e in events if e["event"] == "curio"]
        self.assertEqual([e["detail"] for e in admitted], ["pre_admitted", "admitted"])
        self.assertEqual([e["sanity"] for e in admitted], [100, 100])
        self.assertEqual([e["spent"] for e in admitted], [0, 1])
        self.assertIn(b"An uncanny curio may appear on a later floor.", g.raw)
        for key in DISCOVERY:
            g.send(key)
        self.assertIn(b"Dlvl:2", response("stairs", ">"))
        self.assertEqual(
            [e["detail"] for e in g.events() if e["event"] == "curio"],
            ["pre_admitted", "admitted", "placed"],
        )
        g.more(g.send("y"))
        g.send(",")
        g.send("i")
        self.assertIn(b"q - a chest", g.send(" "))
        g.send(b"\x1b")
        self.assertIn(b"You drop a chest", g.send("dq"))
        self.assertIn(b"s - an Offline counter", g.more(g.send("y")))
        g.send(",")
        inspect("initial-inspect")
        apply("first-apply", b"First stage.", -2)
        first_save = snapshot("first", 2, 1, 98)
        applied = [
            e
            for e in g.events()
            if e["event"] == "curio" and e["detail"].startswith("applied ")
        ]
        self.assertEqual(
            [e["detail"] for e in applied], ["applied requested=-2 actual=-2"]
        )
        self.assertEqual(applied[0]["sanity"], 98)
        self.assertEqual(applied[0]["spent"], 1)
        self.assertEqual(applied[0]["turn"], actions["first-apply"]["before"])
        native_events = (g.run / "events.jsonl").read_bytes()
        continuity.observe(journal, candidate.candidate_id)
        notes = continuity.prior_notes(journal)
        self.assertEqual(
            notes,
            [
                {
                    "candidate_id": candidate.candidate_id,
                    "status": "placed",
                    "continuity_note": NOTE,
                }
            ],
        )
        frozen_run = {
            p.name: sha(p.read_bytes()) for p in g.run.iterdir() if p.is_file()
        }
        frozen_journal = {
            str(p.relative_to(journal)): sha(p.read_bytes())
            for p in journal.rglob("*")
            if p.is_file()
        }
        # No transport in every fresh restored process; source is NOT installed
        # into the game directory. We retain original run evidence untouched.
        g.observe = False
        self.assertFalse(list(g.game.rglob("*.lua")))
        restart("restore-first")
        inspect("restored-inspect")
        snapshot("inspected", 2, 1, 98, "first")
        self.assertEqual(snapshots["inspected"]["record"], snapshots["first"]["record"])
        restart("restore-second")
        apply("second-apply", b"Second stage.", 1)
        snapshot("second", 1, 2, 99, "first")
        restart("restore-third")
        apply("third-apply", b"Third stage.", 0)
        snapshot("third", 0, 3, 99, "second")
        restart("restore-inert")
        before = turn("inert-before")
        output = response("inert", "as")
        self.assertIn(b"This curio is inert.", output)
        for forbidden in (
            b"The curio requests",
            b"This spends one use.",
            b"First stage.",
            b"Second stage.",
            b"Third stage.",
        ):
            self.assertNotIn(forbidden, output)
        self.assertEqual(turn("inert-after"), before)
        actions["inert"] = {"before": before, "after": before}
        snapshot("inert", 0, 3, 99, "third")
        self.assertEqual(snapshots["inert"]["record"], snapshots["third"]["record"])
        self.assertEqual((g.run / "events.jsonl").read_bytes(), native_events)
        self.assertEqual(
            {p.name: sha(p.read_bytes()) for p in g.run.iterdir() if p.is_file()},
            frozen_run,
        )
        self.assertEqual(
            {
                str(p.relative_to(journal)): sha(p.read_bytes())
                for p in journal.rglob("*")
                if p.is_file()
            },
            frozen_journal,
        )
        for name in ("curio.lua", "curio-used.lua"):
            self.assertEqual((g.run / name).read_bytes(), SOURCE)
        self.assertFalse(list(g.game.rglob("*.lua")))
        self.assertEqual(
            [s["observe"] for s in g.sessions], [True, False, False, False, False]
        )
        self.assertTrue(all(not s["wizard"] for s in g.sessions))
        inputs_sent = b"".join(bytes.fromhex(s) for s in g.inputs)
        for forbidden in (b"setsanity", b"levelport", b"\x16"):
            self.assertNotIn(forbidden, inputs_sent)
        # Negative controls corrupt in-memory oracle copies ONLY, never a save
        # handed to the native game. Catch format/source/charge/owner mismatch.
        offsets = {
            "format": schema["save_header"]["feature_set"]["offset"],
            "source": first_save.index(SOURCE),
            **{
                name: snapshots["first"]["fields"]["record_offset"]
                + schema["record"][name]["offset"]
                for name in ("charges", "owner")
            },
        }
        for name, offset in offsets.items():
            changed = bytearray(first_save)
            changed[offset] ^= 1
            with self.subTest(negative=name), self.assertRaises(AssertionError):
                saved_record(
                    self,
                    bytes(changed),
                    schema,
                    2,
                    1,
                    snapshots["first"]["fields"]["owner"],
                )
        changed = bytearray(snapshots["second"]["record"])
        changed[-1] ^= 1
        with self.assertRaisesRegex(
            AssertionError, "unexpected owned-record byte change"
        ):
            assert_record_delta(
                self, snapshots["first"]["record"], bytes(changed), schema, 1, 2
            )
        after = {str(p): sha(p.read_bytes()) for p in protected}
        (root / "protected-after.json").write_text(json.dumps(after, indent=2))
        self.assertEqual(after, hashes)
        (root / "evidence.json").write_text(
            json.dumps(
                {
                    "candidate_id": candidate.candidate_id,
                    "authorship": NOTE,
                    "path": "standalone bundle install/verify + unmodified direct native exec",
                    "snapshots": {
                        name: value["fields"] for name, value in snapshots.items()
                    },
                    "actions": actions,
                    "native_events_sha256": sha(native_events),
                    "notes": notes,
                    "negative_controls": [*offsets, "unexpected_record_byte"],
                    "limits": [
                        "player record not full physical object snapshot",
                        "placed continuity is historical; no invented offline events",
                        "transport disabled by actual fresh-process environment; not syscall tracing or unavailable files",
                        "save/restart checkpoints between remaining uses; no same-session third-use claim",
                        "inspection purity is saved player-record equality across save/restart, not all RNG or physical state",
                        "launcher, direct UI, invalid/runtime failure, both builds and full reviews remain",
                    ],
                },
                indent=2,
            )
        )
