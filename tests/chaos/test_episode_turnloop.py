#!/usr/bin/env python3
"""Real main/moveloop selected commands, with native wizard wish preparation.

No engine link or state injection. replay_clock controls only clock/initial
entropy. Distinct upstream-stock acceptance is NOT implied by reviewed CHAOS=0.
Run through native_driver_supervision.run_driver (see --help).
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import unittest

from gameplay_support import Game
from test_episode_platforms import Cancellation, bounded, owned_game_type
from test_episode_turnloop_oracle import (
    compare_runs,
    legacy_projection,
    validate_native,
)

MATRIX_INPUTS = [
    "n",
    " ",
    " ",
    "#wish\n",
    "uncursed tin whistle\n",
    "a",
    "n",
    "#wish\n",
    "uncursed magic whistle\n",
    "a",
    "o",
    "#wish\n",
    "uncursed potion of water\n",
    "#wish\n",
    "fountain\n",
    "q",
    "n",
    "p",
    "q",
    "y",
    ".",
    " ",
    ".",
    " ",
    "#quit\n",
    "y",
    "n",
    "n",
    "n",
    "n",
    " ",
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def verify_tuple(directory, manifest):
    for name in ("dnethack", "nhdat", "license"):
        path = directory / name
        assert not path.is_symlink()
        assert digest(path) == manifest["pairs"][name]["sha256"], name
        assert path.stat().st_size == manifest["pairs"][name]["size"]


def wish(game, value):
    text = game.send("#wish\n")
    assert b"For what do you wish?" in text, text
    text = game.more(game.send(value + "\n"))
    return text


def select_wish(game, value):
    text = wish(game, value)
    match = re.search(rb"([a-zA-Z]) - ", text)
    assert match, text
    return match.group(1)


def actions(game, matrix):
    witnesses = {}
    whistle = select_wish(game, "uncursed tin whistle")
    text = game.send("a")
    assert b"apply" in text, text
    text = game.more(game.send(whistle))
    assert b"You produce a high whistling sound." in text, text
    witnesses["ordinary_whistle"] = text.decode("ascii", "backslashreplace")
    if matrix:
        magic = select_wish(game, "uncursed magic whistle")
        text = game.send("a")
        assert b"apply" in text, text
        text = game.more(game.send(magic))
        assert b"You produce a strange whistling sound." in text, text
        witnesses["magic_whistle"] = text.decode("ascii", "backslashreplace")
        potion = select_wish(game, "uncursed potion of water")
        text = wish(game, "fountain")
        assert b"A fountain." in text, text
        before_excluded = game.events()
        text = game.send("q")
        assert b"Drink from the fountain?" in text, text
        text = game.send("n")
        assert b"drink" in text, text
        text = game.more(game.send(potion))
        assert b"tastes like water" in text, text
        assert game.events() == before_excluded, "excluded drink emitted events"
        witnesses["decline_then_potion"] = text.decode("ascii", "backslashreplace")
        text = game.send("q")
        assert b"Drink from the fountain?" in text, text
        text = game.more(game.send("y"))
        assert b"An endless stream of snakes pours forth!" in text, text
        witnesses["confirmed_fountain"] = text.decode("ascii", "backslashreplace")
    game.wait_turns(2)
    return witnesses


def main(argv=None):
    # Acceptance relies on assertions; check before even parsing --help.
    # sys.flags reflects -O/-OO and startup PYTHONOPTIMIZE, not mutable env.
    if sys.flags.optimize:
        raise SystemExit(
            "optimized Python is unsupported; run without -O/-OO or PYTHONOPTIMIZE"
        )
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "receipt", "revision", "off-tuple", "artifacts"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--matrix", action="store_true")
    parser.add_argument("--stock-tuple")
    parser.add_argument("--stock-receipt")
    parser.add_argument("--stock-revision")
    args = parser.parse_args(argv)
    assert re.fullmatch("[0-9a-f]{40}", args.revision)
    root, receipt, off, out = map(
        Path, (args.root, args.receipt, args.off_tuple, args.artifacts)
    )
    for path in (root, receipt, off, out):
        assert path.is_absolute() and path.resolve() == path
    assert out.is_relative_to(Path("/tmp")) and not out.is_relative_to(root)
    os.umask(0o077)
    out.mkdir(mode=0o700)
    manifests = [
        json.loads((receipt / f"{mode}-manifest.json").read_text()) for mode in (0, 1)
    ]
    for mode, manifest in enumerate(manifests):
        assert manifest["revision"] == args.revision and manifest["mode"] == mode
        assert manifest["commands"] == json.loads(
            (receipt / f"{mode}-commands.json").read_text()
        )
        assert all(
            c["exit_code"] == 0 and f"CHAOS={mode}" in c["argv"]
            for c in manifest["commands"]
        )
    current = root / "dnethackdir"
    verify_tuple(off, manifests[0])
    verify_tuple(current, manifests[1])
    stock = None
    stock_identity = None
    if args.stock_tuple:
        assert args.stock_receipt and args.stock_revision
        assert re.fullmatch("[0-9a-f]{40}", args.stock_revision)
        stock = Path(args.stock_tuple)
        stock_receipt = Path(args.stock_receipt)
        assert stock.is_absolute() and stock.resolve() == stock
        assert stock_receipt.is_absolute() and stock_receipt.resolve() == stock_receipt
        historical = json.loads(stock_receipt.read_text())
        assert historical["exit"] == 0
        hashes = historical["sessions"][0]["sha256"]
        for name in ("dnethack", "nhdat"):
            assert digest(stock / name) == hashes[name]
        assert hashes["dnethack"] != manifests[0]["pairs"]["dnethack"]["sha256"]
        old_dump = stock_receipt.parent / "game/dumplog/1700000000"
        assert ("-g" + args.stock_revision[:9]) in old_dump.read_text()
        stock_identity = {
            "revision": args.stock_revision,
            "tuple": str(stock),
            "sha256": hashes,
            "receipt": str(stock_receipt),
            "receipt_sha256": digest(stock_receipt),
            "historical_dump_sha256": digest(old_dump),
            "scope": "historical execution receipt, not a fresh build receipt",
        }
        save(out / "stock-provenance.json", stock_identity)
    else:
        assert not args.stock_receipt and not args.stock_revision
    for name in ("gameplay_support.py", "replay_clock.c"):
        assert digest(Path(__file__).with_name(name)) == digest(
            root / "tests/chaos" / name
        )
    sources = [
        Path(__file__).resolve(),
        Path(__file__).with_name("test_episode_turnloop_oracle.py"),
        root / "tests/chaos/replay_clock.c",
    ]
    for path in sources:
        shutil.copy2(path, out / path.name)
    save(out / "fixture-hashes.json", {p.name: digest(p) for p in sources})
    save(
        out / "provenance.json",
        {
            "revision": args.revision,
            "manifests": manifests,
            "upstream_stock": stock_identity,
            "preparation": "wizard #wish through native command parser; not ordinary-play item availability",
            "argv": sys.argv,
            "matrix": args.matrix,
            "pinned_matrix_inputs": MATRIX_INPUTS,
            "seed_srand": 1234567,
            "seed_srandom": 7654321,
            "entropy_initial_state": 987654321,
            "clock": 1700000000,
        },
    )
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(out),
        "TMPDIR": str(out),
        "MAIL": str(out / "private-mail"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "LC_ALL": "C",
    }
    (out / "private-mail").write_bytes(b"")
    cancel = Cancellation()
    old_handlers = {
        s: signal.signal(s, cancel.handler)
        for s in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM)
    }
    signal.alarm(160)
    clock = out / "clock.so"
    active = []
    try:
        bounded(
            [
                "/usr/bin/cc",
                "-shared",
                "-fPIC",
                "-Wall",
                "-Wextra",
                "-Werror",
                out / "replay_clock.c",
                "-ldl",
                "-o",
                clock,
            ],
            out,
            env,
            out / "clock-build",
            cancel=cancel,
        )

        class OwnedGame(owned_game_type(Game, cancel)):
            def send(self, value):
                assert len(self.inputs) < 80, "input batch cap"
                assert (
                    sum(len(bytes.fromhex(s)) for s in self.inputs) + len(value) <= 2048
                ), "input byte cap"
                return super().send(value)

        games = []
        mismatches = []
        witnesses = {}
        variants = [
            ("reviewed-chaos0", off, False, False),
            ("inactive", current, False, False),
            ("legacy-empty", current, True, False),
            ("legacy-repeat", current, True, False),
            ("v2-empty", current, True, True),
            ("v2-repeat", current, True, True),
        ]
        if stock is not None:
            variants.append(("upstream-stock", stock, False, False))
            # Ground upstream-engine identity in actual source history, not label.
            delta, _ = bounded(
                [
                    "/usr/bin/git",
                    "-C",
                    root,
                    "diff",
                    "a6f0a1c43e66f4fb1bcac34d7d9709706682ec19",
                    args.stock_revision,
                    "--",
                    "src",
                    "include",
                    "sys",
                    "win",
                ],
                out,
                env,
                out / "stock-engine-diff",
                cancel=cancel,
            )
            assert delta == b"", "stock baseline engine differs from upstream"
        for name, source, observe, v2 in variants:
            game = OwnedGame(
                source, clock, observe=observe, wizard=True, root=out / name
            )
            active.append(game)
            if source == stock:
                assert stock_identity is not None
                for filename in ("dnethack", "nhdat"):
                    assert (
                        digest(game.game / filename)
                        == stock_identity["sha256"][filename]
                    )
            else:
                verify_tuple(game.game, manifests[int(source == current)])
            if not observe:
                game.run.rmdir()
            previous_env = dict(os.environ)
            try:
                os.environ.clear()
                os.environ.update(env)
                if v2:
                    os.environ["NYARLATHACK_OBSERVATIONS"] = "1"
                game.start()
            finally:
                os.environ.clear()
                os.environ.update(previous_env)
            witnesses = actions(game, args.matrix)
            save(game.root / "witnesses.json", witnesses)
            quit_code = game.quit()
            assert quit_code == 0
            if args.matrix:
                assert game.inputs == [s.encode().hex() for s in MATRIX_INPUTS], (
                    "pinned input route"
                )
            game.save_artifacts()
            dumps = {
                p.name: p.read_bytes().hex()
                for p in (game.game / "dumplog").iterdir()
                if p.is_file()
            }
            run = {
                "inputs": game.inputs,
                "terminal": bytes(game.raw),
                "xlog": (game.game / "xlogfile").read_bytes(),
                "dumps": dumps,
            }
            validate_native(run)
            if games:
                try:
                    compare_runs(games[0][1], run)
                except AssertionError as exc:
                    mismatches.append(
                        {
                            "variant": name,
                            "failure": str(exc),
                            "equal": {k: games[0][1][k] == run[k] for k in run},
                        }
                    )
            games.append((game, run))
            if observe:
                assert (game.run / "whispers.jsonl").read_bytes() == b""
                assert not (game.run / "whisper.json").exists()
                assert not any(r["event"] == "ack" for r in game.events())
            else:
                assert not game.run.exists()
            print("NATIVE_VARIANT=" + name, flush=True)
        legacy = (games[2][0].run / "events.jsonl").read_bytes()
        v2 = (games[4][0].run / "events.jsonl").read_bytes()
        assert legacy == (games[3][0].run / "events.jsonl").read_bytes()
        assert v2 == (games[5][0].run / "events.jsonl").read_bytes()
        assert legacy_projection(legacy) == legacy_projection(v2)
        sys.path.insert(0, str(root))
        from chaos.episodes import project_episodes

        projection = project_episodes(v2)
        save(out / "projection.json", projection)
        assert any(e["operation"] == "whistling" for e in projection["episodes"]), (
            projection
        )
        roots = [
            r["observation"]
            for r in games[4][0].events()
            if r["v"] == 2 and r["observation"]["stage"] == "started"
        ]
        assert [r["operation"] for r in roots] == (
            ["whistling", "whistling", "fountain_drink"]
            if args.matrix
            else ["whistling"]
        )
        if args.matrix:
            assert projection["coverage"]["completed_without_notice"]["count"] == 1
        save(
            out / "result.json",
            {
                "passed_selected_matrix": not mismatches,
                "task8_closed": False,
                "mismatches": mismatches,
                "variants": [v[0] for v in variants],
                "commands": list(witnesses),
                "clock_sha256": digest(clock),
                "upstream_stock": stock_identity,
                "exact_legacy_repeat": True,
                "exact_v2_repeat": True,
                "legacy_semantics_equal_after_v2_removal_and_seq_renumber": True,
                "fatal_fountain": "deferred: no nonwizard fatal setup",
                "projection": projection,
            },
        )
        print("TURNLOOP_ARTIFACTS=" + str(out))
        assert not mismatches, mismatches
    finally:
        signal.alarm(0)
        for game in active:
            game.cleanup()
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_TURNLOOP_TESTS") == "1", "opt-in real turn-loop driver"
)
class TurnloopTests(unittest.TestCase):
    def test_explicit_native_matrix(self):
        from native_driver_supervision import run_driver

        args = []
        for key in ("ROOT", "RECEIPT", "REVISION", "OFF_TUPLE", "ARTIFACTS"):
            value = os.environ["NYARLATHACK_TURNLOOP_" + key]
            args.extend(["--" + key.lower().replace("_", "-"), value])
        args.append("--matrix")
        if os.environ.get("NYARLATHACK_TURNLOOP_STOCK_TUPLE"):
            for key in ("STOCK_TUPLE", "STOCK_RECEIPT", "STOCK_REVISION"):
                args.extend(
                    [
                        "--" + key.lower().replace("_", "-"),
                        os.environ["NYARLATHACK_TURNLOOP_" + key],
                    ]
                )
        code, logs = run_driver(
            Path(__file__).resolve(),
            args,
            os.environ["NYARLATHACK_TURNLOOP_ROOT"],
            os.environ["NYARLATHACK_TURNLOOP_ARTIFACTS"],
        )
        self.assertEqual(code, 0, str(logs))


if __name__ == "__main__":
    main()
