"""Ordinary fixed-policy W effect, real save/restore and exact-input replay.

No wizard setup, ordinary_route, hidden-state input decisions or seed search.
The fixed clock/entropy shim is the same one as the original ordinary baseline;
this is not arbitrary saved-RNG replay. Observer output is read only after play.
"""

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import stat
import subprocess
import tempfile
import time
import unittest

from chaos.history import HistoryState, public_context
from chaos.history_choice import RandomHistoryBackend
from chaos.next_use_history import next_use_menu
from chaos.next_use_journal import read_journal
from gameplay_support import Game, ROOT
import test_next_use_native_playback as playback


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def write(path, value):
    path.write_text(json.dumps(value, indent=2))


def clock(path):
    subprocess.run(
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
            str(path),
        ],
        check=True,
        timeout=30,
    )


def normal_objects(directory):
    # Evaluate only the reviewed object assignments, not recipes/includes.
    # Even make -n on the complete makefile can regenerate dependency files.
    text = (ROOT / "GNUmakefile").read_text().replace("\\\n", " ")
    assignments = "\n".join(
        line
        for line in text.splitlines()
        if re.match(
            r"^(?:SRCOBJ|SYSUNIXOBJ|SYSSHAREOBJ|WINTTYOBJ|WINCURSESOBJ|[A-Z_]+_O)\s*\+?=",
            line,
        )
    )
    makefile = directory / "objects.mk"
    makefile.write_text(
        assignments
        + "\n.PHONY: inventory\ninventory:\n\t@printf '%s\\n' $(sort $(GAME_O))\n"
    )
    paths = subprocess.check_output(
        ["make", "-rR", "-s", "-f", str(makefile), "CHAOS=1", "inventory"],
        text=True,
        cwd=directory,
        timeout=10,
    ).splitlines()
    assert all(
        n in paths for n in ("src/rnd.o", "src/dogmove.o", "sys/unix/unixmain.o")
    )
    assert len(paths) == len(set(paths))
    return [ROOT / name for name in paths]


def private_copy(source, target):
    """Owned copies, never hardlinks or inherited checkpoint directory modes."""
    assert source.is_dir() and not source.is_symlink() and not target.is_symlink()
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    assert target.stat().st_uid == os.getuid()
    target.chmod(0o700)
    for path in source.iterdir():
        assert not path.is_symlink()
        destination = target / path.name
        if path.is_dir():
            private_copy(path, destination)
        else:
            assert stat.S_ISREG(path.stat().st_mode)
            with (
                path.open("rb") as inp,
                os.fdopen(
                    os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
                    "wb",
                ) as out,
            ):
                shutil.copyfileobj(inp, out)
            assert digest(path) == digest(destination)
            assert path.stat().st_ino != destination.stat().st_ino


def checkpoint(game, destination):
    game.save_artifacts()
    destination.mkdir()
    for source in (game.run, game.game / "save"):
        private_copy(source, destination / source.relative_to(game.root))
    for name in ("inputs.json", "terminal.raw", "manifest.json"):
        shutil.copy2(game.root / name, destination / name)


def effect_evidence(game):
    """Posthoc only: native result, public delivery and independent binding hashes."""
    observations = rows(game.game / "ordinary-observer.jsonl")
    assert all(o["wizard"] == o["discover"] == 0 for o in observations)
    assert all(
        o["snapshot_valid"] and o["spent"] == 1 and o["attempted"] == 1
        for o in observations
    )
    envelope = load(game.run / "next_use-envelope.json")
    for o in observations:
        s = o["snapshot"]
        assert (
            hashlib.sha256(bytes.fromhex(s["source_hex"])).hexdigest()
            == s["source_sha256"]
            == envelope["source_sha256"]
        )
        keys = "program_id source_sha256 admission_move program_expiry variant run_token level_token origin_w origin_w_deadline origin_f origin_f_deadline".split()
        binding = "next-use-bind-v1|" + "|".join(str(s[k]) for k in keys)
        assert hashlib.sha256(binding.encode()).hexdigest() == s["binding_sha256"]
    capture = {
        k: observations[-1][k]
        for k in (
            "sink_connected",
            "incomplete",
            "transaction_open",
            "acknowledged_cursor",
        )
    }
    decoded = read_journal(game.run / "next_use-journal.jsonl", capture_status=capture)
    assert decoded["status"] == "acknowledged_complete"
    transitions = [r for r in decoded["records"] if r["kind"] == "transition"]
    private = [
        v for r in decoded["records"] for v in r["data"].get("private_records", [])
    ]
    admitted = [r for r in private if r["kind"] == 2]
    assert len(admitted) == 1 and admitted[0]["data"]["cost"] == 1
    assert (
        base64.b64decode(admitted[0]["data"]["envelope_b64"])
        == (game.run / "next_use-envelope.json").read_bytes()
    )
    public = [
        r
        for r in game.events()
        if r.get("observation", {}).get("operation") == "whistle_attention"
    ]
    assert [r["observation"]["stage"] for r in public] == [
        "started",
        "notice",
        "completed",
    ], "ordinary completed W manifestation"
    witnesses = [
        r["data"]
        for r in transitions
        if r["data"]["operation"] == 5 and r["data"]["post"]["witnessed"] == 1
    ]
    assert len(witnesses) == 1
    w = witnesses[0]
    assert all(
        w[k] == 1
        for k in ("manifestation_delivered", "displaced", "published", "pre_public")
    )
    assert (w["manifest_root"], w["notice_seq"], w["end_seq"]) == tuple(
        r["seq"] for r in public
    )
    assert b"The whistle's echo sharpens your visible companion's attention." in bytes(
        game.raw
    )
    starts = [i for i, o in enumerate(observations) if o["hook"] == "start"]
    assert len(starts) == 2
    assert (
        observations[starts[1] - 1]["snapshot"] == observations[starts[1]]["snapshot"]
    )
    assert (
        observations[-1]["snapshot"]["phase"] == 4
        and observations[-1]["snapshot"]["witnessed"] == 1
    )
    return {
        "transitions": len(transitions),
        "capture": capture,
        "admissions": len(admitted),
        "completed_manifestations": 1,
        "save_restore_preserved": True,
        "witness_move": w["at_move"],
    }


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1",
    "opt-in actual game tests: NYARLATHACK_GAME_TESTS=1",
)
class OrdinaryNextUseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert (ROOT / ".chaos-build").read_text().strip() == "1"
        cls.artifacts = Path(tempfile.mkdtemp(prefix="nyarl-ordinary-next-use-"))
        print("ORDINARY_NEXT_USE_ARTIFACTS=" + str(cls.artifacts), flush=True)
        cls.so = cls.artifacts / "clock.so"
        clock(cls.so)
        objects = normal_objects(cls.artifacts)
        cls.protected = {str(p): digest(p) for p in objects}
        cls.exe = cls.artifacts / "observer-dnethack"
        command = [
            "cc",
            "-g",
            "-DCHAOS",
            "-DDLB",
            "-std=gnu17",
            "-I" + str(ROOT / "include"),
            str(ROOT / "tests/chaos/next_use_ordinary_observer.c"),
            *map(str, objects),
            "-Wl,--wrap=chaos_start",
            "-Wl,--wrap=chaos_observe",
            "-lncursesw",
            "-ltinfo",
            "-lm",
            "-llua5.4",
            "-o",
            str(cls.exe),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (cls.artifacts / "build.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stderr
        write(
            cls.artifacts / "build.json",
            {
                "command": command,
                "objects": cls.protected,
                "observer_source": digest(
                    ROOT / "tests/chaos/next_use_ordinary_observer.c"
                ),
                "test_source": digest(Path(__file__)),
                "executable": digest(cls.exe),
                "clock": digest(cls.so),
                "revision": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
            },
        )

    @classmethod
    def tearDownClass(cls):
        assert all(digest(Path(p)) == h for p, h in cls.protected.items())
        # Retain native saves, journals and sources. Only disposable case assets.
        for pattern in (
            "observer-dnethack",
            "clock.so",
            "*/game/dnethack",
            "*/game/nhdat",
        ):
            for path in cls.artifacts.glob(pattern):
                path.unlink()

    def game(self, name, fresh=False):
        game = Game(
            ROOT / "dnethackdir",
            self.so,
            observe=True,
            wizard=False,
            ordinary=True,
            launcher_fresh=fresh,
            launcher_options=["--ordinary", "--next-use", "--max-runtime", "90"],
            executable=self.exe,
            root=self.artifacts / name,
        )
        self.addCleanup(game.close)
        return game

    def restore(self, game):
        before = len(game.events())
        game.start()
        sessions = [e for e in game.events()[before:] if e.get("event") == "session"]
        self.assertTrue(sessions)
        self.assertTrue(all(e["detail"] == "restore" for e in sessions))

    def suffix(self, game, expected=None, pickup=True):
        tape = playback.InputTape(game, expected)
        self.restore(game)
        if pickup:
            text = game.more(game.send(":"))
            for _ in range(8):
                if b"(end)" not in text and not re.search(rb"\(\d+ of \d+\)", text):
                    break
                text = game.more(game.send(" "))
            else:
                self.fail("bounded public look paging")
            text = game.more(game.send(","))
            # This fixed recorded ordinary trajectory autoselects one item.
            # An unexpected menu is an unqualified run, never a rescue branch.
            self.assertNotIn(b"Pick up what?", text)
        for key in "ljhk" * 3 + "." * 18:
            offset = len(game.raw)
            game.more(game.send(key))
            if (
                b"The whistle's echo sharpens your visible companion's attention."
                in bytes(game.raw[offset:])
            ):
                self.pacing.append(
                    {
                        "stage": "delivered manifestation",
                        "case": game.root.name,
                        "seconds": time.monotonic() - self.began,
                        "input_chunks": len(game.inputs),
                    }
                )
        self.assertEqual(game.save(), 0)
        checkpoint(game, game.root / "terminal-save")
        self.restore(game)
        game.more(game.send("."))
        self.assertEqual(game.quit(), 0)
        if expected is not None:
            self.assertEqual(tape.cursor, len(expected))
            self.assertEqual(game.inputs, expected)
        game.save_artifacts()

    def test_director_failure_empty_and_invalid_candidate_keep_ordinary_play(self):
        controls = []
        for mode in ("no-candidate", "invalid-candidate"):
            with self.subTest(mode=mode):
                game = self.game(mode, fresh=True)
                game.start()
                # Only this test's supervised, forked, session-leading director.
                # The live launcher does not reap it until the native game exits;
                # the game is blocked at its input boundary here.
                parent = Path("/proc") / str(game.pid)
                children = [
                    int(x)
                    for x in (parent / "task" / str(game.pid) / "children")
                    .read_text()
                    .split()
                ]
                directors = [
                    pid
                    for pid in children
                    if os.getsid(pid) == pid
                    and (Path("/proc") / str(pid) / "exe").resolve()
                    == (parent / "exe").resolve()
                ]
                self.assertEqual(len(directors), 1)
                pid = directors[0]
                status_path = Path("/proc") / str(pid) / "stat"
                self.assertEqual(
                    int(status_path.read_text().rsplit(")", 1)[1].split()[1]), game.pid
                )
                os.kill(pid, signal.SIGTERM)
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    if status_path.read_text().rsplit(")", 1)[1].split()[0] == "Z":
                        break
                    time.sleep(0.01)
                else:
                    self.fail("owned director did not terminate")
                if mode == "invalid-candidate":
                    candidate = game.run / "next_use-envelope.json"
                    with os.fdopen(
                        os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
                        "wb",
                    ) as out:
                        out.write(b"invalid candidate\n")
                game.more(game.send("i"))
                game.send("\x1b")
                self.assertIn(b"high whistling sound", game.more(game.send("ag")))
                game.more(game.send("#pray\ny"))
                game.more(game.send("."))
                self.assertEqual(game.quit(), 0)
                game.save_artifacts()
                observations = rows(game.game / "ordinary-observer.jsonl")
                self.assertTrue(
                    all(
                        o["wizard"] == o["discover"] == o["spent"] == 0
                        for o in observations
                    )
                )
                self.assertFalse((game.run / "next_use-receipt.jsonl").exists())
                self.assertNotIn(
                    b"The next whistle may call unusual attention.", bytes(game.raw)
                )
                self.assertFalse(
                    any(
                        e.get("observation", {}).get("operation") == "whistle_attention"
                        for e in game.events()
                    )
                )
                controls.append(
                    {
                        "mode": mode,
                        "director_signal": int(signal.SIGTERM),
                        "native_exit": 0,
                        "spent": 0,
                        "admission": False,
                    }
                )
        write(self.artifacts / "ordinary-controls.json", controls)

    def test_starting_whistle_admits_once_through_the_launcher(self):
        began = self.began = time.monotonic()
        self.pacing = []
        write(
            self.artifacts / "policy.json",
            {
                "ordinary": True,
                "wizard": False,
                "public_prefix": [
                    "inventory",
                    "qualifying tin whistle",
                    "confirmed prayer",
                    "next whistle",
                    "save",
                ],
                "positive_suffix": "look, pickup, ljhk*3 + wait*18, save/restore, wait, quit",
                "negative_suffix": "omit look/pickup; same movement and ending",
                "pacing_seconds_origin": "start of positive test, including prefix and continuations",
                "seed_search": False,
                "private_decisions": False,
                "normal_rng_object": True,
            },
        )
        prefix = self.game("prefix", fresh=True)
        prefix.start()
        inventory = prefix.more(prefix.send("i"))
        letters = re.findall(
            rb"([A-Za-z]) - (?:a|an) (?:uncursed |blessed |cursed )?tin whistle\b",
            inventory,
        )
        self.assertEqual(len(letters), 1, "unqualified public inventory")
        prefix.send("\x1b")
        self.assertIn(
            b"high whistling sound", prefix.more(prefix.send(b"a" + letters[0]))
        )
        envelope = prefix.run / "next_use-envelope.json"
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and not envelope.exists():
            time.sleep(0.2)
        self.assertTrue(envelope.exists(), "host-built envelope was not published")
        self.pacing.append(
            {
                "stage": "qualifying history and publication",
                "seconds": time.monotonic() - began,
                "input_chunks": len(prefix.inputs),
            }
        )
        selection = self.artifacts / "selection-history"
        checkpoint(prefix, selection)
        prefix.more(prefix.send("#pray\ny"))
        prefix.more(prefix.send(b"a" + letters[0]))
        self.assertEqual(prefix.save(), 0)
        initial = self.artifacts / "armed-save"
        checkpoint(prefix, initial)
        prefix.close()
        initial_hashes = {
            str(p.relative_to(initial)): digest(p)
            for p in initial.rglob("*")
            if p.is_file()
        }
        record = self.game("record")
        replay = self.game("replay")
        negative = self.game("no-pickup")
        for game in (record, replay, negative):
            private_copy(initial / "run", game.run)
            private_copy(initial / "game/save", game.game / "save")
        self.suffix(record)
        self.suffix(replay, record.inputs)
        self.suffix(negative, pickup=False)
        # No private observer data was read until all public policies finished.
        prefix_observations = rows(prefix.game / "ordinary-observer.jsonl")
        self.assertTrue(
            all(o["wizard"] == o["discover"] == 0 for o in prefix_observations)
        )
        spends = [
            (a["spent"], b["spent"])
            for a, b in zip(prefix_observations, prefix_observations[1:])
            if a["spent"] != b["spent"]
        ]
        self.assertEqual(spends, [(0, 1)])
        evidence = effect_evidence(record)
        self.assertEqual(effect_evidence(replay), evidence)
        with self.assertRaisesRegex(
            AssertionError, "ordinary completed W manifestation"
        ):
            effect_evidence(negative)
        exact = (
            "inputs.json",
            "run/events.jsonl",
            "run/next_use-journal.jsonl",
            "run/next_use-envelope.json",
            "run/next_use-owner",
            "run/next_use-receipt.jsonl",
            "run/next_use-schedule.jsonl",
            "game/ordinary-observer.jsonl",
            "game/xlogfile",
        )
        for name in exact:
            self.assertEqual(
                (record.root / name).read_bytes(),
                (replay.root / name).read_bytes(),
                name,
            )
        # Document rather than claim raw terminal equality across different paths.
        a, b = bytes(record.raw), bytes(replay.raw)
        first = (
            'chaos: run directory "' + str(record.run) + '" (preserved on exit)\r\n'
        ).encode()
        second = (
            'chaos: run directory "' + str(replay.run) + '" (preserved on exit)\r\n'
        ).encode()
        self.assertEqual(a.count(first), 2)
        self.assertEqual(b.count(second), 2)
        self.assertEqual(a.split(first), b.split(second))
        self.assertIn(
            b"The next whistle may call unusual attention.", bytes(prefix.raw)
        )
        self.assertEqual(
            len((record.run / "next_use-receipt.jsonl").read_text().splitlines()), 1
        )
        self.assertTrue(
            all(digest(initial / name) == h for name, h in initial_hashes.items())
        )
        history_rows = rows(selection / "run/events.jsonl")
        changed = [
            dict(r)
            for r in history_rows
            if r.get("observation", {}).get("operation") != "whistling"
        ]
        for index, row in enumerate(changed, 1):
            row["seq"] = index
        histories = [
            HistoryState(("".join(json.dumps(r) + "\n" for r in data)).encode())
            for data in (history_rows, changed)
        ]
        contexts = [public_context(h) for h in histories]
        self.assertEqual(
            contexts[0]["summary"]["observed"], contexts[1]["summary"]["observed"]
        )
        menus = [next_use_menu(h) for h in histories]
        self.assertEqual([r["op"] for r in menus[0]], ["quiet", "whistle_attention"])
        self.assertEqual(menus[1], [])
        choices = [
            RandomHistoryBackend(seed=0).choose_next_use(c, m)
            for c, m in zip(contexts, menus)
        ]
        self.assertEqual(choices[0]["family"], "W")
        self.assertIsNone(choices[1])
        write(
            self.artifacts / "synthetic-history-removal.json",
            {
                "scope": "posthoc synthetic copied-history counterfactual, never sent to game",
                "director_seed": 0,
                "observed": contexts[0]["summary"]["observed"],
                "menus": menus,
                "choices": choices,
            },
        )
        log_prefix = (initial / "run/director.log").read_bytes()
        for game in (record, replay):
            full = (game.run / "director.log").read_bytes()
            self.assertTrue(full.startswith(log_prefix))
            self.assertEqual(
                full[len(log_prefix) :].splitlines(),
                [b"chaos: next-use: already_published"] * 2,
            )
        evidence.update(
            pacing=self.pacing,
            input_chunks=len(record.inputs),
            elapsed_seconds=time.monotonic() - began,
            native_exits=[0, 0],
            normal_initial_save_exit=0,
            initial_save_unchanged=True,
            no_pickup_control="positive witness oracle rejected",
            terminal_raw_equal=a == b,
            terminal_scope="only two owned-directory launcher banners differ",
            exact_files={name: digest(record.root / name) for name in exact},
            scope="current-build ordinary fixed-policy W; controlled clock/entropy; not general saved-RNG or human learning",
        )
        write(self.artifacts / "ordinary-result.json", evidence)
