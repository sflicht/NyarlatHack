"""Independent Task8e2: native fresh bundle launcher and matching reuse.

Handwritten fixed visible-derived route, not a general navigator or model output.
No imports of held gameplay modules, standalone installer, injected game state,
network, engine rebuild, schedule retiming or transport-off claim. Only the
existing clock and read-only layout reporter are compiled, into private artifacts.
"""

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from gameplay_support import ANSI, ROOT, Game
from native_fixture_selection import SOURCE_DRIVER_HASH, prepare
from chaos import curio_continuity as continuity
from chaos.curio_store import store_candidate
from chaos.director import Mailbox


def sha(data):
    return hashlib.sha256(data).hexdigest()


# Explicit keys retain the historical pin and fail closed on unknown modes.
def expected_driver_hash(mode):
    return {
        "archived": "9d341b28a4ab3f4453b09e4f49a2e8701a7c78345184f487e2f0b32d70db7270",
        "source-build": SOURCE_DRIVER_HASH,
    }[mode]


def metadata(path):
    s = path.stat()
    return dict(
        sha256=sha(path.read_bytes()),
        inode=s.st_ino,
        mode=s.st_mode & 0o777,
        uid=s.st_uid,
        nlink=s.st_nlink,
        size=s.st_size,
        mtime_ns=s.st_mtime_ns,
        ctime_ns=s.st_ctime_ns,
    )


def literals():
    # Read-only AST literal extraction; never import/execute the held module.
    tree = ast.parse((ROOT / "tests/chaos/test_curio_gameplay.py").read_text())
    return {
        n.targets[0].id: ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id in {"SOURCE", "NOTE", "DISCOVERY"}
    }


def decode_save(
    test, data, schema, source, charges, state, sanity, *, policy, cosmetic=None
):
    """Bounded source-anchored player record, not a physical-object snapshot."""

    def integer(blob, field, signed=False):
        start, size = field["offset"], field["size"]
        test.assertGreaterEqual(start, 0)
        value = blob[start : start + size]
        test.assertEqual(len(value), size)
        return int.from_bytes(value, schema["byteorder"], signed=signed)

    test.assertFalse(schema["external_compression"])
    test.assertFalse(schema["internal_compression"])
    for name, value in schema["save_header_values"].items():
        test.assertEqual(integer(data, schema["save_header"][name]), value)
    test.assertEqual(data.count(source), 1)
    start = data.index(source) - schema["record"]["source"]["offset"]
    test.assertGreaterEqual(start, schema["save_header_size"])
    record = data[start : start + schema["record_size"]]
    test.assertEqual(len(record), schema["record_size"])
    fields: dict = {
        k: integer(record, schema["record"][k], k in ("charges", "state", "disabled"))
        for k in (
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
    test.assertEqual(fields["source_len"], len(source))
    test.assertGreater(fields["owner"], 0)
    test.assertEqual(
        (fields["charges"], fields["state"], fields["disabled"]), (charges, state, 0)
    )
    for name, value in (("source", source), ("name", b"Offline counter")):
        f = schema["record"][name]
        test.assertEqual(
            record[f["offset"] : f["offset"] + f["size"]], value.ljust(f["size"], b"\0")
        )
    player_start = start - schema["you"]["curio"]["offset"]
    test.assertGreaterEqual(player_start, schema["save_header_size"])
    player = data[player_start : player_start + schema["you_size"]]
    test.assertEqual(len(player), schema["you_size"])
    fields["sanity"] = integer(player, schema["you"]["usanity"], True)
    fields["spent"] = integer(
        player,
        {
            "offset": schema["you"]["chaos"]["offset"] + schema["spent_offset"],
            "size": schema["spent_size"],
        },
        True,
    )
    test.assertEqual(fields["sanity"], sanity)
    if policy == "historical":
        test.assertEqual(fields["spent"], 2)  # archived ambient1 + curio1
    elif policy == "current":
        test.assertEqual(fields["spent"], 1)  # current ambient0 + curio1
        test.assertEqual(schema["chaos_state_version"], 2)
        test.assertEqual(schema["chaos_size"], schema["you"]["chaos"]["size"])
        base = schema["you"]["chaos"]["offset"]
        test.assertLessEqual(base + schema["chaos_size"], len(player))
        native = {}
        for name in ("version", "cosmetic_seen", "cosmetic_last_turn"):
            field = schema["chaos_fields"][name]
            test.assertGreaterEqual(field["offset"], 0)
            test.assertGreater(field["size"], 0)
            test.assertLessEqual(field["offset"] + field["size"], schema["chaos_size"])
            native[name] = integer(
                player, dict(offset=base + field["offset"], size=field["size"]), True
            )
        test.assertEqual(native["version"], 2)
        fields["cosmetic"] = dict(
            seen=native["cosmetic_seen"], last_turn=native["cosmetic_last_turn"]
        )
        test.assertIsNotNone(cosmetic)
        test.assertEqual(fields["cosmetic"], cosmetic)
    else:
        raise ValueError("explicit historical/current save policy required")
    fields.update(save_sha256=sha(data), record_sha256=sha(record), record_offset=start)
    return record, fields


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class CurioLauncherGameplayTests(unittest.TestCase):
    def test_fresh_bundle_save_and_explicit_matching_launcher_restore(self):
        selection = prepare(ROOT)
        policy = {"archived": "historical", "source-build": "current"}[selection.mode]
        ambient_spent = 1 if policy == "historical" else 0
        self.assertEqual((ROOT / ".chaos-build").read_text().strip(), "1")
        self.assertEqual(
            sha((ROOT / "tests/chaos/gameplay_support.py").read_bytes()),
            expected_driver_hash(selection.mode),
        )
        root = Path(tempfile.mkdtemp(prefix="curio8e2-native-"))
        print("CURIO8E2_ARTIFACTS=" + str(root), flush=True)

        def dump(name, value):
            (root / name).write_text(json.dumps(value, indent=2))

        fixture = literals()
        source, note, route = (fixture[k] for k in ("SOURCE", "NOTE", "DISCOVERY"))
        dump(
            "fixture.json",
            dict(
                authorship=note,
                route=route,
                route_origin="fixed previously visible-derived fixture; AST only",
            ),
        )
        protected = [
            ROOT / "tests/chaos" / n
            for n in (
                "gameplay_support.py",
                "replay_clock.c",
                "curio_save_layout.c",
                "native_fixture_selection.py",
                "native_build_identity.py",
                "native_build_calibration.py",
                "test_curio_restart_gameplay.py",
                "test_curio_gameplay.py",
            )
        ]
        protected += list((ROOT / "include").glob("*.h"))
        protected += [
            ROOT / "src" / n
            for n in (
                "save.c",
                "restore.c",
                "chaos_curio.c",
                "chaos_engine.c",
                "chaos_io.c",
                "chaos_protocol.c",
            )
        ]
        protected += [
            ROOT / "chaos" / n
            for n in (
                "launcher.py",
                "curio_store.py",
                "curio_continuity.py",
                "director.py",
            )
        ]
        protected += [
            ROOT / "dnethackdir" / n for n in ("dnethack", "nhdat", "license")
        ]
        before = {str(p): sha(p.read_bytes()) for p in protected}
        dump("protected-before.json", before)

        def verify_protected():
            after = {str(p): sha(p.read_bytes()) for p in protected}
            dump("protected-after.json", after)
            self.assertEqual(after, before)

        self.addCleanup(verify_protected)
        for name in ("gameplay_support.py", "replay_clock.c", "curio_save_layout.c"):
            shutil.copy2(ROOT / "tests/chaos" / name, root / name)
        shutil.copy2(__file__, root / Path(__file__).name)
        # Explicit historical pins OR verified source inputs; never fallback.
        installed = selection.artifact_hashes
        for name, digest in installed.items():
            self.assertEqual(sha((ROOT / "dnethackdir" / name).read_bytes()), digest)
        dump(
            "installed-identity.json",
            {
                n: metadata(ROOT / "dnethackdir" / n)
                for n in ("dnethack", "nhdat", "license")
            },
        )
        dump("helper-source-identity.json", selection.verify_helper_copy(root))
        clock, layout = root / "clock.so", root / "layout"
        commands = [
            [
                selection.compiler,
                "-shared",
                "-fPIC",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(root / "replay_clock.c"),
                "-ldl",
                "-o",
                str(clock),
            ],
            [
                selection.compiler,
                "-std=gnu17",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-DCHAOS",
                "-DDLB",
                "-isystem" + str(ROOT / "include"),
                str(root / "curio_save_layout.c"),
                "-o",
                str(layout),
            ],
        ]
        dump("build-commands.json", commands)
        for command in commands:
            result = subprocess.run(
                command, capture_output=True, timeout=30, env=selection.environment
            )
            with (root / "build.log").open("ab") as log:
                log.write(result.stdout + result.stderr)
            self.assertEqual(result.returncode, 0, result.stderr)
        output = subprocess.check_output(
            [str(layout)], timeout=5, env=selection.environment
        )
        (root / "layout.json").write_bytes(output)
        schema = json.loads(output)
        selection.validate_schema(schema)  # actual ELF vs source-matched reporter
        dump("native-selection.json", selection.record())
        dump(
            "helper-identity.json",
            {str(p): metadata(p) for p in (clock, layout)},
        )
        bundles, journal = root / "bundles", root / "journal"
        bundles.mkdir(mode=0o700)
        journal.mkdir(mode=0o700)
        candidate = store_candidate(
            bundles, json.dumps(dict(lua_source=source.decode(), continuity_note=note))
        )
        continuity.create_journal(journal)
        continuity.register(journal, bundles, candidate.candidate_id)
        self.assertEqual(candidate.candidate_id, sha(source))
        mail = root / "private-mail"
        mail.write_bytes(b"")
        mail.chmod(0o600)
        mail_before = metadata(mail)
        dump("mail-before.json", mail_before)
        env = patch.dict(os.environ, {"MAIL": str(mail)})
        env.start()
        self.addCleanup(env.stop)
        options = [
            "--curio-bundle-root",
            str(bundles),
            "--curio-candidate-id",
            candidate.candidate_id,
        ]
        g = Game(
            selection.tuple_dir,
            clock,
            wizard=False,
            root=root / "session",
            launcher_options=options,
            launcher_fresh=True,
        )
        self.addCleanup(g.close)  # before native start, including failed startup
        self.assertFalse(os.path.lexists(g.run))
        dump(
            "fresh-before.json",
            dict(
                run=str(g.run),
                exists=False,
                launcher_options=options,
                launcher_fresh=True,
            ),
        )
        processes, actions, records = [], {}, []

        def process_evidence(label):
            found, pending = [], [g.pid]
            while pending:
                pid = pending.pop()
                p = Path(f"/proc/{pid}")
                children = [
                    int(x) for x in (p / f"task/{pid}/children").read_text().split()
                ]
                pending.extend(children)
                argv = [
                    a.decode() for a in (p / "cmdline").read_bytes().split(b"\0") if a
                ]
                proc_state = (p / "stat").read_text().rsplit(")", 1)[1].split()[0]
                try:
                    exe = os.readlink(p / "exe")
                    native = (p / "exe").samefile(g.game / "dnethack")
                except FileNotFoundError:
                    # Schedule-complete director can be an unreaped zombie:
                    # launcher retains it until native exit (_stop_director).
                    proc_state = (p / "stat").read_text().rsplit(")", 1)[1].split()[0]
                    self.assertEqual(proc_state, "Z")
                    self.assertNotEqual(pid, g.pid)
                    exe, native = None, False
                item: dict = dict(
                    pid=pid,
                    children=children,
                    argv=argv,
                    exe=exe,
                    state=proc_state,
                    role="native"
                    if native
                    else "supervisor"
                    if pid == g.pid
                    else "director",
                )
                if native:
                    allowed = {
                        b"MAIL",
                        b"LD_PRELOAD",
                        b"NETHACKOPTIONS",
                        b"TZ",
                        b"NYARLATHACK_RUN_DIR",
                    }
                    selected = {
                        k.decode(): v.decode()
                        for entry in (p / "environ").read_bytes().split(b"\0")
                        if b"=" in entry
                        for k, v in [entry.split(b"=", 1)]
                        if k in allowed
                    }
                    item["environment"] = selected
                    item["exe_sha256"] = sha((p / "exe").read_bytes())
                    self.assertEqual(argv, [str(g.game / "dnethack")])
                    self.assertEqual(selected["MAIL"], str(mail))
                    self.assertEqual(selected["NYARLATHACK_RUN_DIR"], str(g.run))
                    self.assertEqual(
                        item["exe_sha256"], before[str(ROOT / "dnethackdir/dnethack")]
                    )
                found.append(item)
            self.assertEqual(sum(p["role"] == "native" for p in found), 1)
            processes.append(dict(label=label, processes=found))
            dump("processes.json", processes)
            with self.assertRaisesRegex(ValueError, "another director holds"):
                with Mailbox(g.run):
                    self.fail("competing lock acquired")
            return [p["pid"] for p in found]

        def response(label, command):
            start = len(g.raw)
            g.more(g.send(command))
            raw = bytes(g.raw[start:])
            (root / (label + ".raw")).write_bytes(raw)
            return ANSI.sub(b"", raw)

        def turn(label):
            output = response(label, b"\x12")
            values = re.findall(rb"T:(\d+)", output)
            self.assertTrue(values, output)
            return int(values[-1])

        def inspect(label):
            before_turn = turn(label + "-before")
            start = len(g.raw)
            g.send("i")
            self.assertIn(b"s - an Offline counter", g.send(" "))
            menu = g.send("s")
            self.assertIn(b"I - Describe this item", menu)
            self.assertIn(b"a - Apply", menu)
            self.assertIn(b"A plain counter with three stages.", g.send("I"))
            g.more(g.send(" "))
            raw = bytes(g.raw[start:])
            (root / (label + ".raw")).write_bytes(raw)
            self.assertNotIn(b"whistle", raw.lower())
            self.assertEqual(turn(label + "-after"), before_turn)

        def apply(label, stage, delta):
            before_turn = turn(label + "-before")
            output = re.sub(rb"\s+", b" ", response(label, "as"))
            warning = f"The curio requests a Sanity change of {delta:+d}; native limits may reduce it.".encode()
            for expected in (warning, b"This spends one use.", stage):
                self.assertEqual(output.count(expected), 1, output)
                self.assertLessEqual(output.index(expected), output.index(stage))
            self.assertEqual(turn(label + "-after"), before_turn + 1)
            actions[label] = dict(turn=before_turn, delta=delta)
            dump("actions.json", actions)

        def snapshot(label, pids, charges, state, sanity):
            saved_turn = turn(label + "-save-boundary")
            self.assertEqual(g.save(), 0)
            alive = [pid for pid in pids if Path(f"/proc/{pid}").exists()]
            dump(
                label + "-wait.json",
                dict(pids=pids, still_existing=alive, supervisor_exit=g.exitcode),
            )
            self.assertEqual(alive, [])
            self.assertIn(b"chaos: director stopped; run data retained", g.raw)
            with Mailbox(g.run):
                pass
            self.assertEqual((g.run / "director.log").read_bytes(), b"")
            dest = root / label
            dest.mkdir()
            saves = list((g.game / "save").iterdir())
            self.assertEqual(len(saves), 1)
            data = saves[0].read_bytes()
            (dest / "native.savefile").write_bytes(data)
            for name in ("terminal.raw", "inputs.json", "manifest.json"):
                shutil.copy2(g.root / name, dest / name)
            shutil.copytree(g.run, dest / "run")
            record, fields = decode_save(
                self,
                data,
                schema,
                source,
                charges,
                state,
                sanity,
                policy=policy,
                cosmetic=g.events()[-1].get("cosmetic"),
            )
            if records:
                self.assertEqual(fields["owner"], records[0][1]["owner"])
                expected = bytearray(records[0][0])
                for name, value in (("charges", charges), ("state", state)):
                    f = schema["record"][name]
                    expected[f["offset"] : f["offset"] + f["size"]] = value.to_bytes(
                        f["size"], schema["byteorder"], signed=True
                    )
                self.assertEqual(bytes(expected), record)
            records.append((record, fields))
            (dest / "record.bin").write_bytes(record)
            (dest / "fields.json").write_text(json.dumps(fields, indent=2))
            return saved_turn

        dump("fresh-copy-identity.json", selection.verify_copy(g.game))
        g.start()
        pids = process_evidence("fresh")
        receipt = json.loads((g.run / "curio-install.json").read_text())
        self.assertEqual(
            receipt,
            dict(
                version=1,
                status="candidate_installed_not_admitted",
                source_sha256=sha(source),
                provenance="supplied_raw_envelope",
            ),
        )
        curio = [e for e in g.events() if e["event"] == "curio"]
        self.assertEqual([e["detail"] for e in curio], ["pre_admitted", "admitted"])
        self.assertEqual([e["sanity"] for e in curio], [100, 100])
        self.assertEqual(
            [e["spent"] for e in curio], [ambient_spent, ambient_spent + 1]
        )
        if policy == "current":
            self.assertTrue(all(e["v"] == 3 for e in curio))
            self.assertTrue(
                all(e["cosmetic"] == {"seen": 1, "last_turn": 1} for e in curio)
            )
        for key in route:
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
        self.assertIn(b"s - an Offline counter", response("movement-autopickup", "y"))
        inspect("fresh-inspect")
        apply("first-apply", b"First stage.", -2)
        saved_turn = snapshot("first", pids, 2, 1, 98)
        evidence = {
            n: metadata(g.run / n)
            for n in ("curio.lua", "curio-used.lua", "curio-install.json")
        }
        dump("transport-before-restore.json", evidence)
        for n in ("curio.lua", "curio-used.lua"):
            self.assertEqual((g.run / n).read_bytes(), source)
        native_before = (g.run / "events.jsonl").read_bytes()
        continuity.bind_run(journal, candidate.candidate_id, g.run)
        notes = [
            dict(
                candidate_id=candidate.candidate_id,
                status="placed",
                continuity_note=note,
            )
        ]
        self.assertEqual(continuity.prior_notes(journal), notes)
        dump("notes-first.json", notes)
        self.assertEqual((g.run / "events.jsonl").read_bytes(), native_before)
        g.launcher_fresh = False
        restore_start = len(g.raw)
        dump("restore-copy-identity.json", selection.verify_copy(g.game))
        g.start()
        pids = process_evidence("restore")
        self.assertNotIn(b"An uncanny curio may appear", bytes(g.raw[restore_start:]))
        self.assertFalse(list((g.game / "save").iterdir()))
        self.assertEqual(turn("restored-turn"), saved_turn)
        inspect("restored-inspect")
        apply("second-apply", b"Second stage.", 1)
        snapshot("second", pids, 1, 2, 99)
        self.assertEqual({n: metadata(g.run / n) for n in evidence}, evidence)
        events = g.events()
        self.assertEqual(
            [e["detail"] for e in events if e["event"] == "curio"],
            [
                "pre_admitted",
                "admitted",
                "placed",
                "applied requested=-2 actual=-2",
                "applied requested=1 actual=1",
            ],
        )
        self.assertEqual(
            [e["detail"] for e in events if e["event"] == "session"], ["new", "restore"]
        )
        acks = [e for e in events if e["event"] == "ack"]
        accepted = [e for e in acks if e["status"] == "accepted"]
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["mutation"], "ambient")
        self.assertEqual(accepted[0]["spent"], ambient_spent)
        if policy == "current":
            self.assertEqual(
                (accepted[0]["cost"], accepted[0]["cosmetic_cost"]), (0, 1)
            )
            self.assertEqual(accepted[0]["cosmetic"], {"seen": 1, "last_turn": 1})
            self.assertTrue(
                all(
                    e["cosmetic"] == accepted[0]["cosmetic"]
                    for e in events
                    if e["event"] == "session" and e["detail"] == "restore"
                )
            )
        # chaos_io_safe reads (does not remove) whisper.json at later safe
        # points. chaos_admit rejects its already consumed ID without spending.
        for e in acks:
            if e["status"] != "accepted":
                self.assertEqual(
                    (e["status"], e["detail"], e["spent"]),
                    ("rejected", "duplicate", ambient_spent + 1),
                )
        whispers = [
            json.loads(line)
            for line in (g.run / "whispers.jsonl").read_text().splitlines()
        ]
        self.assertEqual(len(whispers), 1)
        self.assertEqual(whispers[0]["status"], "admitted")
        request = json.loads((g.run / "whisper.json").read_text())
        for key in ("id", "mutation", "value", "duration", "telegraph", "at"):
            self.assertEqual(whispers[0][key], request[key])
            self.assertTrue(all(e[key] == request[key] for e in acks))
        native_after = (g.run / "events.jsonl").read_bytes()
        continuity.observe(journal, candidate.candidate_id)
        self.assertEqual(continuity.prior_notes(journal), notes)
        self.assertEqual((g.run / "events.jsonl").read_bytes(), native_after)
        dump("notes-second.json", notes)
        self.assertEqual(metadata(mail), mail_before)
        sent = b"".join(bytes.fromhex(x) for x in g.inputs)
        for forbidden in (b"setsanity", b"levelport", b"\x16"):
            self.assertNotIn(forbidden, sent)
        dump(
            "evidence.json",
            dict(
                candidate_id=candidate.candidate_id,
                receipt=receipt,
                sessions=len(g.sessions),
                records=[r[1] for r in records],
                notes=notes,
                ack=acks,
                native_events_sha256=sha(native_after),
                limitations=[
                    "one fixed route/clock",
                    "player record not full object snapshot",
                    "no transport-off, runtime-failure, depletion or direct-inspection claim",
                ],
            ),
        )
