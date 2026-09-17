"""Independent production registration pins; ENGINE-UNIT, not action physics."""

import itertools
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from chaos.episodes import parse_episode_event
from scripts.generate_protocol_contract import generate

from chaos import _protocol_contract as contract
import test_episode_io as io_tests
import test_episode_scopes as scope_tests

ROOT = Path(__file__).resolve().parents[2]
FACTS = "sound_high sound_shrill sound_normal sound_strange sound_humming water_refreshed water_foul cannot_reach detection_presented".split()


class RegistrationTests(unittest.TestCase):
    def test_invalid_registration(self):
        from copy import deepcopy
        from scripts.generate_protocol_contract import render

        source = json.loads((ROOT / "chaos/protocol_contract.json").read_text())
        changes = [
            (("format",), True),
            (("wire_version",), True),
            (("families", 0, "id"), True),
            (("families", 1, "name"), "whistling"),
            (("families", 1, "symbol"), "CHAOS_OBS_OP_WHISTLING"),
            (("families", 0, "allow_blocked"), 1),
            (("families", 0, "projection"), "hidden"),
            (("families", 0, "hook_refs"), []),
            (("facts", 0, "operation"), 0),
            (("facts", 0, "operation"), True),
            (("facts", 0, "channel"), "hidden"),
            (("facts", 0, "implies_blocked"), True),
            (("facts", 0, "name"), "x" * 32),
            (("facts", 0, "name"), "non_ascii_é"),
            (("facts", 0, "unknown"), 1),
            (("stages", 0, "role"), "unknown"),
            (("projection", "count_cap"), True),
        ]
        for keys, value in changes:
            with self.subTest(keys=keys):
                data = deepcopy(source)
                obj = data["observations"]
                for key in keys[:-1]:
                    obj = obj[key]
                obj[keys[-1]] = value
                with self.assertRaises(ValueError):
                    render(data)

    def invalid_audit_sources(self):
        from copy import deepcopy

        source = json.loads((ROOT / "chaos/protocol_contract.json").read_text())
        swapped = deepcopy(source)
        stages = swapped["observations"]["stages"]
        stages[3]["symbol"], stages[4]["symbol"] = (
            stages[4]["symbol"],
            stages[3]["symbol"],
        )
        yield "swapped stage symbols", swapped
        unknown = deepcopy(source)
        unknown["observations"]["stages"][3]["symbol"] = "CHAOS_OBS_STAGE_UNKNOWN"
        yield "unknown stage symbol", unknown
        for registry in ("families", "facts"):
            for row in (None, 7, "row", [], {}, True, {"id": 1}):
                malformed = deepcopy(source)
                malformed["observations"][registry][0] = row
                yield f"{registry}: {row!r}", malformed

    def test_audited_rows_raise_contextual_value_error(self):
        from scripts.generate_protocol_contract import render

        for label, source in self.invalid_audit_sources():
            with self.subTest(source=label):
                with self.assertRaisesRegex(ValueError, "observations:"):
                    render(source)

    def test_audited_cli_rejects_before_either_output_changes(self):
        with tempfile.TemporaryDirectory(prefix="nyarl-invalid-contract-") as tmp:
            root = Path(tmp)
            paths = ("include/chaos_protocol.h", "chaos/_protocol_contract.py")
            for name in (*paths, "scripts/generate_protocol_contract.py"):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            before = {name: (root / name).read_bytes() for name in paths}
            for label, source in self.invalid_audit_sources():
                with self.subTest(source=label):
                    for name, content in before.items():
                        (root / name).write_bytes(content)
                    (root / "chaos/protocol_contract.json").write_text(
                        json.dumps(source)
                    )
                    result = subprocess.run(
                        [
                            "/usr/bin/python3",
                            "-I",
                            "-B",
                            str(root / "scripts/generate_protocol_contract.py"),
                            "--root",
                            str(root),
                        ],
                        capture_output=True,
                        timeout=10,
                    )
                    self.assertNotEqual(result.returncode, 0, label)
                    self.assertIn(b"observations:", result.stderr)
                    self.assertEqual(
                        before, {name: (root / name).read_bytes() for name in paths}
                    )

    def test_production_registration(self):
        # Literal independent review pin: never copied/rendered from registry data.
        expected = dict(
            format=1,
            wire_version=2,
            operation_none=dict(symbol="CHAOS_OBS_OP_NONE", id=0, name="none"),
            fact_none=dict(symbol="CHAOS_OBS_FACT_NONE", id=0, name="none"),
            stages=[
                dict(symbol=symbol, id=id_, name=name, phase=phase, role=role)
                for symbol, id_, name, phase, role in [
                    ("CHAOS_OBS_STAGE_ENABLED", 0, "enabled", "result", "enable"),
                    ("CHAOS_OBS_STAGE_STARTED", 1, "started", "attempt", "start"),
                    ("CHAOS_OBS_STAGE_NOTICE", 2, "notice", "result", "notice"),
                    ("CHAOS_OBS_STAGE_COMPLETED", 3, "completed", "result", "complete"),
                    ("CHAOS_OBS_STAGE_BLOCKED", 4, "blocked", "result", "block"),
                ]
            ],
            channels=[
                dict(name="message", witness="native_tty_rendered"),
                dict(name="map", witness="native_tty_blocking_map_presented"),
            ],
            families=[
                dict(
                    symbol=symbol,
                    id=id_,
                    name=name,
                    allow_blocked=blocked,
                    projection="completed_notice_by_operation",
                    hook_refs=[
                        dict(file=file, symbol=hook, role=role)
                        for file, hook, role in hooks
                    ],
                )
                for symbol, id_, name, blocked, hooks in [
                    (
                        "CHAOS_OBS_OP_WHISTLING",
                        1,
                        "whistling",
                        False,
                        [
                            ("src/apply.c", "doapply", "scope"),
                            ("src/apply.c", "use_whistle", "arm"),
                            ("src/pline.c", "vpline", "message_take_deliver"),
                            ("src/apply.c", "use_magic_whistle", "arm"),
                        ],
                    ),
                    (
                        "CHAOS_OBS_OP_FOUNTAIN_DRINK",
                        2,
                        "fountain_drink",
                        True,
                        [
                            ("src/potion.c", "dodrink", "scope"),
                            ("src/fountain.c", "drinkfountain", "arm"),
                            ("src/pline.c", "vpline", "message_take_deliver"),
                            ("src/detect.c", "monster_detect", "map_take_deliver"),
                        ],
                    ),
                ]
            ],
            facts=[
                dict(
                    symbol=symbol,
                    id=id_,
                    name=name,
                    operation=operation,
                    channel=channel,
                    implies_blocked=blocked,
                )
                for symbol, id_, name, operation, channel, blocked in [
                    ("CHAOS_OBS_FACT_SOUND_HIGH", 1, "sound_high", 1, "message", False),
                    (
                        "CHAOS_OBS_FACT_SOUND_SHRILL",
                        2,
                        "sound_shrill",
                        1,
                        "message",
                        False,
                    ),
                    (
                        "CHAOS_OBS_FACT_SOUND_NORMAL",
                        3,
                        "sound_normal",
                        1,
                        "message",
                        False,
                    ),
                    (
                        "CHAOS_OBS_FACT_SOUND_STRANGE",
                        4,
                        "sound_strange",
                        1,
                        "message",
                        False,
                    ),
                    (
                        "CHAOS_OBS_FACT_SOUND_HUMMING",
                        5,
                        "sound_humming",
                        1,
                        "message",
                        False,
                    ),
                    (
                        "CHAOS_OBS_FACT_WATER_REFRESHED",
                        6,
                        "water_refreshed",
                        2,
                        "message",
                        False,
                    ),
                    ("CHAOS_OBS_FACT_WATER_FOUL", 7, "water_foul", 2, "message", False),
                    (
                        "CHAOS_OBS_FACT_CANNOT_REACH",
                        8,
                        "cannot_reach",
                        2,
                        "message",
                        True,
                    ),
                    (
                        "CHAOS_OBS_FACT_DETECTION_PRESENTED",
                        9,
                        "detection_presented",
                        2,
                        "map",
                        False,
                    ),
                ]
            ],
            projection=dict(
                context_version=1,
                scope="selected_whistle_fountain",
                lookback_roots=32,
                count_cap=3,
                evidence="first_two_latest",
                summary_bytes=4096,
            ),
        )
        source = json.loads((ROOT / "chaos/protocol_contract.json").read_text())
        self.assertEqual(expected["wire_version"], 2)  # Historical registration pin.
        expected = dict(expected, wire_version=4)
        self.assertEqual(source["observations"], expected)
        self.assertEqual(contract.OBSERVATIONS, expected)


class WireTests(unittest.TestCase):
    # Reuse fixture operations, not an entire TestCase's inherited test suite.
    setUpClass = classmethod(io_tests.EpisodeIOTests.setUpClass.__func__)
    logged = classmethod(io_tests.EpisodeIOTests.logged.__func__)
    run_rows = io_tests.EpisodeIOTests.run_rows

    def test_literal_v2_bytes(self):
        states, raw = self.run_rows([(0, 0, 0, 0, 0)])
        self.assertEqual(states[0][0], 1)
        # SOURCE: a1daf52e833ebf79b0625f8f342c852743e972fc, real
        # episode_io.c + chaos_io.c + chaos_protocol.c, enabled input 0 0 0 0 0.
        self.assertEqual(parse_episode_event(V2_GOLDEN)["v"], 2)
        self.assertEqual(raw, V4_GOLDEN)

    def test_exhaustive_shared_integer_domain(self):
        # Independent frozen vocabulary and grammar, never registry-derived.
        ops = {0: "none", 1: "whistling", 2: "fountain_drink", 3: "stub"}
        stages = dict(
            enumerate("enabled started notice completed blocked unknown".split())
        )
        facts = dict(enumerate(["none", *FACTS, "stub_message"]))
        cases = list(
            itertools.product(
                ops, stages, (-1, 0, 1, 10, 11, 2147483647, 2147483648), facts
            )
        )
        states, raw = self.run_rows(
            [(10, op, stage, root, fact) for op, stage, root, fact in cases]
        )
        emitted = iter(raw.splitlines())
        accepted = 0
        for case, state in zip(cases, states, strict=True):
            op, stage, root, fact = case
            legal = (
                (stage == 0 and op == 0 and root == 0 and fact == 0)
                or (stage == 1 and op in (1, 2) and root == 0 and fact == 0)
                or (
                    0 < root < 11
                    and (
                        (
                            stage == 2
                            and (
                                (op == 1 and 1 <= fact <= 5)
                                or (op == 2 and 6 <= fact <= 9)
                            )
                        )
                        or (stage == 3 and op in (1, 2) and fact == 0)
                        or (stage == 4 and op == 2 and fact == 0)
                    )
                )
            )
            with self.subTest(case=case):
                self.assertEqual(state[0], int(legal))
                # Candidate invalid rows are schema probes, NOT claimed C output.
                row = json.loads(V4_GOLDEN)
                row.update(seq=11, phase="attempt" if stage == 1 else "result")
                row["observation"] = dict(
                    operation=ops[op],
                    stage=stages[stage],
                    root_seq=root,
                    fact=facts[fact],
                )
                candidate = json.dumps(row)
                if legal:
                    actual = parse_episode_event(next(emitted))
                    self.assertEqual(actual, parse_episode_event(candidate))
                    accepted += 1
                else:
                    with self.assertRaises(ValueError):
                        parse_episode_event(candidate)
        self.assertEqual(list(emitted), [])
        self.assertEqual(len(states), len(cases))
        self.assertGreater(accepted, 0)
        print(f"shared-domain cases={len(cases)} accepted={accepted}")
        # Python's strict JSON types are outside C's native integer domain.
        for key, value in [("seq", True), ("seq", 11.0), ("seq", "11")]:
            row = json.loads(V4_GOLDEN)
            row[key] = value
            with self.assertRaises(ValueError):
                parse_episode_event(json.dumps(row))


V2_GOLDEN = (
    b'{"v":2,"seq":1,"turn":10,"safe":0,"event":"observation",'
    b'"phase":"result","detail":"","sanity":0,"insight":0,"budget":12,'
    b'"spent":0,"reserved":0,"last_id":0,"vitals":{"hp":7,"hp_max":20,'
    b'"power":-2,"power_max":10},"observation":{"operation":"none",'
    b'"stage":"enabled","root_seq":0,"fact":"none"}}\n'
)


# Independent current full-wire literal, not generated from the old golden.
V4_GOLDEN = (
    b'{"v":4,"seq":1,"turn":10,"safe":0,"event":"observation",'
    b'"phase":"result","detail":"","sanity":0,"insight":0,"budget":12,'
    b'"spent":0,"reserved":0,"last_id":0,"vitals":{"hp":7,"hp_max":20,'
    b'"power":-2,"power_max":10},"cosmetic":{"seen":0,"last_turn":0},'
    b'"observation":{"operation":"none","stage":"enabled","root_seq":0,"fact":"none"}}\n'
)


class IsolatedFamilyTests(unittest.TestCase):
    run_scope = scope_tests.EpisodeScopesTests.run_scope
    check_identical_fact_reentry = (
        scope_tests.EpisodeScopesTests.check_identical_fact_reentry
    )

    def compile_scope(self):
        command = [
            "/usr/bin/gcc",
            "-DCHAOS",
            "-ffunction-sections",
            "-fdata-sections",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-isystem",
            str(self.root / "include"),
            str(self.root / "tests/chaos/episode_scopes.c"),
            *(
                str(self.root / "src" / f)
                for f in ("chaos_engine.c", "chaos_io.c", "chaos_protocol.c")
            ),
            "-Wl,--gc-sections",
            "-Wl,--wrap=write",
            "-Wl,--wrap=fsync",
            "-o",
            str(self.binary),
        ]
        result = subprocess.run(command, capture_output=True, timeout=30)
        (
            self.logs / f"compile-{len(list(self.logs.glob('compile-*.json')))}.json"
        ).write_text(
            json.dumps(
                dict(
                    command=command,
                    returncode=result.returncode,
                    stdout=result.stdout.decode(),
                    stderr=result.stderr.decode(),
                )
            )
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stderr, b"")

    def project_isolated(self, raw, reject_blocking=False):
        result = subprocess.run(
            [
                "/usr/bin/python3",
                "-I",
                "-B",
                "-c",
                """
import json, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
from chaos import episodes, _protocol_contract
assert pathlib.Path(episodes.__file__).resolve() == root / "chaos/episodes.py"
assert pathlib.Path(_protocol_contract.__file__).resolve() == root / "chaos/_protocol_contract.py"
raw = sys.stdin.buffer.read()
if sys.argv[2] == "reject-blocking":
    # Row grammar remains valid; only whole-history chronology is corrupted.
    for line in raw.splitlines():
        episodes.parse_episode_event(line)
    try:
        episodes.project_episodes(raw)
    except ValueError as exc:
        print(json.dumps({"rejected": str(exc)}))
    else:
        print(json.dumps({"rejected": None}))
else:
    print(json.dumps(episodes.project_episodes(raw)))
""",
                str(self.root),
                "reject-blocking" if reject_blocking else "project",
            ],
            input=raw,
            capture_output=True,
            timeout=10,
        )
        (
            self.logs / f"python-{len(list(self.logs.glob('python-*.json')))}.json"
        ).write_text(
            json.dumps(
                dict(
                    command=result.args,
                    input=raw.decode(),
                    input_kind="synthetic terminal corruption of actual C history"
                    if reject_blocking
                    else "actual C history",
                    returncode=result.returncode,
                    stdout=result.stdout.decode(),
                    stderr=result.stderr.decode(),
                )
            )
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        projected = json.loads(result.stdout)
        if reject_blocking:
            self.assertEqual(
                projected,
                {"rejected": "cannot_reach requires blocked terminal"},
                "registered_blocking_chronology",
            )
        return projected

    def check_blocking_chronology(self, raw):
        # Preserve every byte except the real blocked terminal's stage value.
        self.assertEqual(raw.count(b'"stage":"blocked"'), 1)
        corrupted = raw.replace(b'"stage":"blocked"', b'"stage":"completed"')
        self.project_isolated(corrupted, reject_blocking=True)

    def test_registration_only_third_family_lifecycle(self):
        with tempfile.TemporaryDirectory(prefix="nyarl-third-family-") as tmp:
            self.root = Path(tmp)
            self.binary = self.root / "scopes"
            self.logs = self.root / "logs"
            self.logs.mkdir()
            # Private repo-shaped source copy: includes resolve only here.
            for directory in ("include", "chaos"):
                shutil.copytree(
                    ROOT / directory,
                    self.root / directory,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
            for name in (
                "src/chaos_engine.c",
                "src/chaos_io.c",
                "src/chaos_protocol.c",
                "tests/chaos/episode_scopes.c",
                "tests/chaos/episode_io.c",
            ):
                target = self.root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            unchanged = [
                p
                for p in self.root.rglob("*")
                if p.is_file()
                and p.relative_to(self.root).as_posix()
                not in (
                    "chaos/protocol_contract.json",
                    "chaos/_protocol_contract.py",
                    "include/chaos_protocol.h",
                )
            ]
            before = {p: p.read_bytes() for p in unchanged}
            from scripts.generate_protocol_contract import BEGIN, END

            def handwritten_header():
                header = (self.root / "include/chaos_protocol.h").read_text()
                return header.split(BEGIN)[0], header.split(END)[1]

            header_before = handwritten_header()
            production = {
                ROOT / p.relative_to(self.root): p.read_bytes() for p in unchanged
            }
            production.update(
                {
                    p: p.read_bytes()
                    for p in (
                        ROOT / "chaos/protocol_contract.json",
                        ROOT / "include/chaos_protocol.h",
                        ROOT / "chaos/_protocol_contract.py",
                    )
                }
            )
            self.compile_scope()
            self.assert_rejected()
            source_path = self.root / "chaos/protocol_contract.json"
            original = source_path.read_text()
            source = json.loads(original)
            obs = source["observations"]
            obs["families"].append(
                dict(
                    symbol="CHAOS_OBS_OP_STUB",
                    id=3,
                    name="stub",
                    allow_blocked=True,
                    projection="completed_notice_by_operation",
                    hook_refs=[
                        dict(
                            file="tests/chaos/episode_scopes.c",
                            symbol="main",
                            role=role,
                        )
                        for role in (
                            "scope",
                            "arm",
                            "message_take_deliver",
                            "map_take_deliver",
                        )
                    ],
                )
            )
            for id_, name, channel, blocked in [
                (10, "stub_message", "message", False),
                (11, "stub_map", "map", False),
                (12, "stub_blocking", "message", True),
            ]:
                obs["facts"].append(
                    dict(
                        symbol="CHAOS_OBS_FACT_" + name.upper(),
                        id=id_,
                        name=name,
                        operation=3,
                        channel=channel,
                        implies_blocked=blocked,
                    )
                )
            obs["projection"]["scope"] = "isolated_stub_fixture"
            source_path.write_text(json.dumps(source))
            self.assertEqual(generate(self.root, False), 0)
            self.assertEqual(generate(self.root, True), 0)
            self.assertEqual(before, {p: p.read_bytes() for p in unchanged})
            self.assertEqual(header_before, handwritten_header())
            self.compile_scope()
            for fact, take, deliver, terminal in [
                (10, "take", "deliver", "completed"),
                (11, "take_map", "map", "completed"),
                (12, "take", "deliver", "blocked"),
            ]:
                with self.subTest(fact=fact):
                    raw, rows, _ = self.run_scope(
                        f"start begin 3 arm 3 {fact} {take} {deliver} {deliver} end end"
                    )
                    self.assertEqual(
                        [r["observation"]["stage"] for r in rows[4:]],
                        ["started", "notice", terminal],
                    )
                    public = self.project_isolated(raw)
                    self.assertEqual(
                        set(public),
                        {
                            "episode_context_v",
                            "scope",
                            "lookback_roots",
                            "episodes",
                            "coverage",
                        },
                    )
                    self.assertEqual(public["scope"], "isolated_stub_fixture")
                    self.assertEqual(public["episode_context_v"], 1)
                    self.assertEqual(public["lookback_roots"], 32)
                    if terminal == "completed":
                        self.assertEqual(
                            public["episodes"],
                            [
                                dict(
                                    operation="stub",
                                    count=1,
                                    saturated=False,
                                    evidence=[
                                        dict(
                                            root_seq=5,
                                            notice_seq=6,
                                            end_seq=7,
                                            fact="stub_message"
                                            if fact == 10
                                            else "stub_map",
                                        )
                                    ],
                                )
                            ],
                        )
                    else:
                        self.assertEqual(public["episodes"], [])
                        self.assertEqual(
                            public["coverage"]["blocked"],
                            dict(count=1, saturated=False),
                        )
                        self.check_blocking_chronology(raw)
                    # Production parser must not adopt sandbox names.
                    with self.assertRaises(ValueError):
                        parse_episode_event(json.dumps(rows[4]))
            for commands, terminal, coverage in [
                ("", "completed", "completed_without_notice"),
                ("block", "blocked", "blocked"),
            ]:
                raw, rows, _ = self.run_scope(f"start begin 3 {commands} end")
                self.assertEqual(rows[-1]["observation"]["stage"], terminal)
                public = self.project_isolated(raw)
                self.assertEqual(public["episodes"], [])
                self.assertEqual(
                    public["coverage"][coverage], dict(count=1, saturated=False)
                )
            for fact, take, deliver, wrong in [
                (10, "take", "deliver", "map"),
                (11, "take_map", "map", "deliver"),
            ]:
                self.check_identical_fact_reentry(3, fact, take, deliver)
                _, rows, _ = self.run_scope(
                    f"start begin 3 arm 3 {fact} {take} {wrong} {deliver} end"
                )
                self.assertEqual(
                    [r["observation"]["stage"] for r in rows[4:]],
                    ["started", "notice", "completed"],
                )
                for boundary in (
                    "turn",
                    "event session",
                    "event level_enter",
                    "event level_leave",
                    "event death",
                    "shadow event level_enter shadow",
                    "disarm",
                ):
                    _, rows, _ = self.run_scope(
                        f"start begin 3 arm 3 {fact} {take} {boundary} {deliver} end"
                    )
                    self.assertFalse(
                        any(
                            r.get("observation", {}).get("stage") == "notice"
                            for r in rows
                        )
                    )
                for w, s in [(1, 0), (0, 1)]:
                    for prefix, successful in [
                        ("fault {w} {s} start", 0),
                        ("start fault {w} {s} begin 3", 4),
                        (
                            f"start begin 3 arm 3 {fact} {take} fault {{w}} {{s}} {deliver}",
                            5,
                        ),
                        ("start begin 3 fault {w} {s} end", 5),
                    ]:
                        _, rows, out = self.run_scope(
                            prefix.format(w=w, s=s)
                            + f" {deliver} end end begin 3 arm 3 {fact} {take} {deliver} end"
                        )
                        self.assertEqual(len(rows), successful + s)
                        self.assertEqual(
                            int(out.splitlines()[-1].split()[2]), successful
                        )
                        self.assertEqual(int(out.splitlines()[-1].split()[1]), 0)
            raw, _, _ = self.run_scope(
                "start " + "begin 3 arm 3 10 take deliver end " * 5
            )
            public = self.project_isolated(raw)
            self.assertEqual(
                public["episodes"],
                [
                    dict(
                        operation="stub",
                        count=3,
                        saturated=True,
                        evidence=[
                            dict(
                                root_seq=root,
                                notice_seq=root + 1,
                                end_seq=root + 2,
                                fact="stub_message",
                            )
                            for root in (5, 8, 17)
                        ],
                    )
                ],
            )
            for bad in (
                "arm 1 1 take deliver",
                "arm 3 9 take_map map",
                "fake 10",
                "arm 3 10 deliver",
                "arm 3 11 map",
            ):
                _, rows, _ = self.run_scope(f"start begin 3 {bad} end")
                self.assertEqual(
                    [r["observation"]["stage"] for r in rows[4:]],
                    ["started", "completed"],
                )
            for fault in ("fault 1 0", "fault 0 1", "overflow"):
                _, rows, out = self.run_scope(
                    f"start begin 3 arm 3 10 take {fault} begin 3 oldend deliver end"
                )
                self.assertFalse(
                    any(r.get("observation", {}).get("stage") == "notice" for r in rows)
                )
                self.assertIn("begin 0 ", out)
            self.check_consumer_bypasses()
            source_path.write_text(original)
            self.assertEqual(generate(self.root, False), 0)
            self.assertEqual(generate(self.root, True), 0)
            self.assertEqual(before, {p: p.read_bytes() for p in unchanged})
            self.assertEqual(header_before, handwritten_header())
            self.compile_scope()
            self.assert_rejected()
            self.assertEqual(production, {p: p.read_bytes() for p in production})
            print(
                f"third-family real-C runs={len(list(self.logs.glob('run-*.json')))}; baseline/extension/removal compiled"
            )

    def check_consumer_bypasses(self):
        """Fresh valid metadata; mutate only handwritten consumers, one at a time."""
        import hashlib

        frozen = {
            name: (self.root / name).read_bytes()
            for name in (
                "chaos/protocol_contract.json",
                "chaos/_protocol_contract.py",
                "include/chaos_protocol.h",
            )
        }
        receipts = []

        def stages(commands):
            _, rows, _ = self.run_scope(commands)
            return [r["observation"]["stage"] for r in rows[4:]]

        def family_check():
            self.assertEqual(
                stages("start begin 3 arm 3 10 take deliver end"),
                ["started", "notice", "completed"],
                "family_registration",
            )

        def channel_check():
            self.assertEqual(
                stages("start begin 3 arm 3 10 take_map take deliver end"),
                ["started", "notice", "completed"],
                "channel_preserves_token",
            )

        def owner_check():
            self.assertEqual(
                stages("start begin 1 arm 1 6 take deliver end"),
                ["started", "completed"],
                "fact_owner_rejection",
            )

        raw, _, _ = self.run_scope("start begin 3 arm 3 10 take deliver end")
        blocking_raw, _, _ = self.run_scope("start begin 3 arm 3 12 take deliver end")

        def blocking_check():
            self.check_blocking_chronology(blocking_raw)

        def grouping_check():
            self.assertEqual(
                [g["operation"] for g in self.project_isolated(raw)["episodes"]],
                ["stub"],
                "registered_family_projection",
            )

        def compile_io():
            self.exe = self.root / "episode-io"
            command = [
                "/usr/bin/gcc",
                "-std=c99",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I" + str(self.root / "include"),
                *(
                    str(self.root / name)
                    for name in (
                        "src/chaos_protocol.c",
                        "src/chaos_io.c",
                        "tests/chaos/episode_io.c",
                    )
                ),
                "-Wl,--wrap=write",
                "-Wl,--wrap=fsync",
                "-o",
                str(self.exe),
            ]
            self.logged(
                command,
                f"bypass-io-{len(list(self.logs.glob('bypass-io-*.log')))}",
                timeout=30,
            )

        def writer_check():
            states, emitted = self.run_rows([(10, 1, 2, 1, 1), (10, 1, 2, 1, 6)])
            # Valid rows must still work; rejecting everything cannot satisfy this.
            self.assertEqual(states[0][0], 1, "writer_valid_control")
            for line in emitted.splitlines()[1:]:
                with self.assertRaises(ValueError):
                    parse_episode_event(
                        line
                    )  # Actual illegal C output, not a fabricated row.
            self.assertEqual(states[1][0], 0, "writer_owner_rejection")
            self.assertEqual(len(emitted.splitlines()), 1)

        mutants = [
            (
                "family_registration",
                "src/chaos_engine.c",
                "if (!chaos_obs_family(operation)) return 0;",
                "if (operation != 1 && operation != 2) return 0;",
                self.compile_scope,
                family_check,
            ),
            (
                "channel_preserves_token",
                "src/chaos_engine.c",
                "if (!fact || fact->channel != channel) return token;",
                "if (!fact || channel < 0) return token;",
                self.compile_scope,
                channel_check,
            ),
            (
                "fact_owner_rejection",
                "src/chaos_protocol.c",
                "obs_facts[i].id == fact && obs_facts[i].operation == op",
                "obs_facts[i].id == fact && op > 0",
                self.compile_scope,
                owner_check,
            ),
            (
                "writer_owner_rejection",
                "src/chaos_io.c",
                "!chaos_obs_row_valid(operation, stage, s->seq + 1, root_seq, fact)",
                "(!chaos_obs_row_valid(operation, stage, s->seq + 1, root_seq, fact) && !(operation == 1 && stage == 2 && fact == 6))",
                compile_io,
                writer_check,
            ),
            (
                "registered_family_projection",
                "chaos/episodes.py",
                "for operation in sorted(_FAMILIES):",
                'for operation in ("fountain_drink", "whistling"):',
                None,
                grouping_check,
            ),
            (
                "registered_blocking_chronology",
                "chaos/episodes.py",
                '_FACT_INFO.get(active["fact"], {}).get(\n'
                '                        "implies_blocked", False\n'
                "                    )",
                'active["fact"] == "cannot_reach"',
                None,
                blocking_check,
            ),
        ]
        for name, relative, old, new, build, check in mutants:
            path = self.root / relative
            original = path.read_text()
            self.assertEqual(original.count(old), 1, name)
            if build:
                build()
            check()  # Same assertion passes against a freshly built original.
            changed = original.replace(old, new)
            receipt = dict(
                assertion=name,
                source=relative,
                old=old,
                new=new,
                original_sha256=hashlib.sha256(original.encode()).hexdigest(),
                mutant_sha256=hashlib.sha256(changed.encode()).hexdigest(),
            )
            try:
                path.write_text(changed)
                if build:
                    build()  # Compile/import failure is NOT a killed mutant.
                with self.assertRaisesRegex(AssertionError, name) as rejected:
                    check()
                receipt["behavioral_failure"] = str(rejected.exception)
                receipts.append(receipt)
            finally:
                path.write_text(original)
            self.assertEqual(frozen, {p: (self.root / p).read_bytes() for p in frozen})
        (self.logs / "consumer-bypasses.json").write_text(
            json.dumps(receipts, indent=2)
        )
        self.assertEqual(len(receipts), 6)
        print(
            "consumer bypasses rejected: " + ", ".join(r["assertion"] for r in receipts)
        )

    logged = io_tests.EpisodeIOTests.logged.__func__
    run_rows = io_tests.EpisodeIOTests.run_rows

    def assert_rejected(self):
        _, rows, output = self.run_scope("start begin 3 arm 3 10 take deliver end")
        self.assertEqual(
            [r["observation"]["stage"] for r in rows if r["v"] == 4], ["enabled"]
        )
        self.assertIn("begin 0 ", output)


if __name__ == "__main__":
    unittest.main()
