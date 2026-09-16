#!/usr/bin/python3
"""Selected whistle sounds: native purity and measured negative controls.

Run from the explicit frozen source root. External fixture/support hashes are
separate from native build identity. This is not the complete Task 6b/8 matrix.
"""

import argparse
import fcntl
import pty
import struct
import termios
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import sys
import unittest


# Private fixture expectations, never observation metadata. Draw counts are
# source predictions checked over the complete native action interval.
SOUND_CASES = {
    "ordinary-cursed": ("shrill whistling sound", "sound_shrill", 0, 0, 101, 1, 0),
    "magic-uncursed": ("strange whistling sound", "sound_strange", 0, 1, 0, 0, 0),
    "magic-hallucinated": ("normal whistling sound", "sound_normal", 0, 1, 0, 0, 1),
    "magic-cursed-humming": (
        "high-pitched humming noise",
        "sound_humming",
        1,
        0,
        0,
        1,
        0,
    ),
    "magic-cursed-success": ("strange whistling sound", "sound_strange", 1, 1, 0, 1, 0),
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "receipt", "revision", "artifacts"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        raise ValueError("full lowercase 40hex revision required")
    for name in ("root", "receipt", "artifacts"):
        value = getattr(args, name)
        p = Path(value)
        if not p.is_absolute() or str(p) != value or p.resolve() != p:
            raise ValueError("canonical absolute path required: " + name)
    root, receipt, out = map(Path, (args.root, args.receipt, args.artifacts))
    if Path.cwd() != root or not out.is_relative_to(Path("/tmp")):
        raise ValueError("launch from selected root; artifacts under /tmp")
    if out.is_relative_to(root):
        raise ValueError("external artifacts required")
    trusted = root / "tests/chaos"
    helpers = (
        "gameplay_support",
        "native_fixture_selection",
        "native_rng",
        "native_build_calibration",
        "native_build_identity",
    )
    for name in helpers:
        cached = sys.modules.get(name)
        if cached is not None and (
            not getattr(cached, "__file__", None)
            or Path(cached.__file__).resolve().parent != trusted
        ):
            raise ValueError("foreign cached helper: " + name)
    sys.path.insert(0, str(trusted))
    import gameplay_support
    import native_fixture_selection
    import native_rng  # noqa: F401

    for name in helpers:
        if Path(sys.modules[name].__file__).resolve().parent != trusted:
            raise ValueError("foreign helper: " + name)
    if gameplay_support.ROOT != root:
        raise ValueError("helper ROOT mismatch")
    selection_env = dict(
        os.environ,
        NYARLATHACK_NATIVE_FIXTURE_MODE="source-build",
        NYARLATHACK_NATIVE_BUILD_RECEIPT=str(receipt),
        NYARLATHACK_NATIVE_EXPECTED_REVISION=args.revision,
    )
    selection = native_fixture_selection.prepare(root, selection_env)
    if selection.environment is None:
        raise ValueError("source build environment required")
    # Explicit external reviewed test support, NOT a frozen native helper.
    support = Path(__file__).resolve().with_name("test_episode_platforms.py")
    spec = importlib.util.spec_from_file_location("whistle_supervision", support)
    assert spec is not None and spec.loader is not None
    supervisor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(supervisor)
    digest, save = supervisor.digest, supervisor.save
    os.umask(0o077)
    out.mkdir(mode=0o700, exist_ok=False)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    env = dict(
        selection.environment,
        HOME=str(out),
        TMPDIR=str(out),
        MAIL=str(out / "private-mail"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    (out / "private-mail").write_bytes(b"")
    manifest = json.loads((receipt / "1-manifest.json").read_text())
    originals = {str(root / n): digest(root / n) for n in manifest["objects"]}
    save(out / "manifest-object-hashes.json", originals)
    cancel = supervisor.Cancellation()
    handlers = {
        s: signal.signal(s, cancel.handler)
        for s in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM)
    }
    signal.alarm(180)
    try:

        def run(command, name, timeout=45):
            return supervisor.bounded(
                command, out, env, out / name, timeout, cancel=cancel
            )[0]

        for name in native_fixture_selection.ORACLE_SOURCES:
            shutil.copyfile(root / name, out / Path(name).name)
        selection.verify_helper_copy(out)
        source = Path(__file__).resolve().with_name("episode_whistle.c")
        fixture_paths = (
            source,
            Path(__file__).resolve(),
            support,
            trusted / "native_rng.h",
            trusted / "native_rng.py",
        )
        save(
            out / "external-fixture-and-support-hashes.json",
            {str(p): digest(p) for p in fixture_paths},
        )
        for p in fixture_paths:
            shutil.copyfile(p, out / p.name)
            assert digest(p) == digest(out / p.name)
        flags = [
            "-std=gnu17",
            "-g",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-DCHAOS",
            "-DDLB",
            "-isystem" + str(root / "include"),
        ]
        run(
            [
                selection.compiler,
                *flags,
                out / "curio_save_layout.c",
                "-o",
                out / "layout",
            ],
            "layout-build",
        )
        selection.validate_schema(json.loads(run([out / "layout"], "layout")))
        save(out / "selection.json", selection.record())
        objects = (
            sorted((root / "src").glob("*.o"))
            + [
                root / p
                for p in (
                    "sys/unix/unixres.o",
                    "sys/unix/unixunix.o",
                    "sys/unix/unixmain.o",
                    "sys/share/ioctl.o",
                    "sys/share/unixtty.o",
                )
            ]
            + sorted((root / "win/tty").glob("*.o"))
            + sorted((root / "win/curses").glob("*.o"))
        )
        transforms = {
            root / "sys/unix/unixmain.o": ["--redefine-sym=main=original_game_main"],
            root / "src/invent.o": ["--globalize-symbol=nextgetobj"],
            root / "src/rnd.o": [
                "--globalize-symbol=reseed_period",
                "--globalize-symbol=reseed_count",
            ],
        }
        # Same symbol-only RNG copy as controlled_rng_objects, bounded supervisor.
        for original, switches in transforms.items():
            target = out / original.name
            run(
                ["/usr/bin/objcopy", *switches, original, target],
                "copy-" + original.stem,
            )
            objects = [target if p == original else p for p in objects]
        run(
            [
                selection.compiler,
                *flags,
                "-c",
                out / source.name,
                "-o",
                out / "fixture.o",
            ],
            "fixture-compile",
        )
        libs = (
            run(["/usr/bin/pkg-config", "--libs", "lua5.4"], "lua-libs")
            .decode()
            .split()
        )
        exe = out / "episode-whistle"
        run(
            [
                selection.compiler,
                out / "fixture.o",
                *objects,
                "-lncursesw",
                "-ltinfo",
                "-lm",
                "-ldl",
                *libs,
                "-o",
                exe,
            ],
            "fixture-link",
        )
        clock = out / "clock.so"
        run(
            [
                selection.compiler,
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
            "clock-build",
        )
        again = native_fixture_selection.prepare(root, selection_env)
        assert again.record()["source_build"] == selection.record()["source_build"]
        save(out / "executable-hashes.json", {str(p): digest(p) for p in (exe, clock)})
        calibration = json.loads(run([exe, "--calibrate"], "seed-preflight"))
        assert [r["seed"] for r in calibration] == list(range(1, 17))
        seeds = {
            branch: next(r for r in calibration if r["first_rn2_2"] == branch)
            for branch in (0, 1)
        }
        # Measured native libc seeds: fail rather than reselect on a new platform.
        # No measured action is retried to find a branch.
        assert {branch: row["seed"] for branch, row in seeds.items()} == {0: 2, 1: 1}
        save(
            out / "rng-calibration.json",
            {
                "provenance": "native copied rnd.o rn2 plus libc srandom; pre-action only",
                "candidates": calibration,
                "chosen": seeds,
            },
        )
        results = []
        for case in ("known", "unknown", *SOUND_CASES):
            descriptor = SOUND_CASES.get(case)
            calibrated = seeds[case == "magic-cursed-success"]
            pair = []
            for enabled in (False, True):
                work = out / (case + ("-on" if enabled else "-off"))
                g = gameplay_support.Game(selection.tuple_dir, clock, root=work)
                selection.verify_copy(g.game)
                options = work / "options"
                options.write_text("OPTIONS=!splash_screen,!perm_invent\n")
                child_env = dict(
                    env,
                    HOME=str(work),
                    TERM="xterm",
                    LINES="24",
                    COLUMNS="80",
                    NETHACKOPTIONS="@" + str(options),
                    LD_PRELOAD=str(clock),
                    NYARLATHACK_RUN_DIR=str(g.run),
                    NYARLATHACK_OBSERVATIONS=str(int(enabled)),
                    WHISTLE_CHAOS_STATE=str(work / "chaos-state.json"),
                )
                if descriptor:
                    child_env["WHISTLE_SEED"] = str(calibrated["seed"])
                raw, diagnostic = supervisor.bounded(
                    [exe, case],
                    g.game,
                    child_env,
                    work / "terminal",
                    20,
                    True,
                    cancel=cancel,
                )
                message = descriptor[0] if descriptor else "high whistling sound"
                assert raw.count(("You produce a " + message + ".").encode()) == 1
                state = json.loads(diagnostic)
                if descriptor:
                    _, _, draws, sleeping, whistle_time, cursed, hallucinated = (
                        descriptor
                    )
                    assert state["case"] == case
                    assert state["seed"] == calibrated["seed"]
                    assert state["rng_draws"] == draws
                    continuation = calibrated[
                        "next_after_one" if draws else "next_after_zero"
                    ]
                    assert state["next_draw"] == state["expected_next"] == continuation
                    assert state["return"] == (
                        4 if case == "ordinary-cursed" else state["move_default"]
                    )
                    assert state["sleeping"] == sleeping
                    assert state["whistletime"] == whistle_time
                    assert state["cursed"] == cursed
                    assert state["hallucinating"] == hallucinated
                    assert state["hallucination_timeout"] == (10 if hallucinated else 0)
                    for key in (
                        "known",
                        "dknown",
                        "type_known",
                        "tame",
                        "hallucination_resistance",
                    ):
                        assert state[key] == 0
                records = g.events()
                chaos = json.loads((work / "chaos-state.json").read_text())
                before, after = chaos["before"].copy(), chaos["after"].copy()
                assert after.pop("seq") - before.pop("seq") == (4 if enabled else 1)
                assert before == after, chaos
                assert chaos["after"]["seq"] == records[-1]["seq"]
                assert set(before) == {
                    "version",
                    "budget",
                    "spent",
                    "reserved",
                    "last_id",
                    "safe",
                    "effects",
                    "haunt",
                }
                assert len(before["effects"]) == 3
                assert not any(e["event"] == "ack" for e in records)
                obs = [e for e in records if e["v"] == 2]
                if not enabled:
                    assert not obs
                pair.append((raw, state, before))
                results.append(
                    {
                        "case": case,
                        "enabled": enabled,
                        "state": state,
                        "observations": obs,
                        "native_returncode": 0,
                    }
                )
            assert pair[0] == pair[1], "native terminal/state off-on mismatch"
        assert len(results) == 14
        save(out / "native-results.json", results)
        # Expected aborts use owned status capture, never a caught bounded error.
        OwnedGame = supervisor.owned_game_type(gameplay_support.Game, cancel)
        negatives = []
        for mode in ("native", "raw", "budget"):
            work = out / ("negative-" + mode)
            g = OwnedGame(selection.tuple_dir, clock, root=work)
            selection.verify_copy(g.game)
            options = work / "options"
            options.write_text("OPTIONS=!splash_screen,!perm_invent\n")
            child_env = dict(
                env,
                HOME=str(work),
                TERM="xterm",
                LINES="24",
                COLUMNS="80",
                NETHACKOPTIONS="@" + str(options),
                LD_PRELOAD=str(clock),
                NYARLATHACK_RUN_DIR=str(g.run),
                NYARLATHACK_OBSERVATIONS="1",
                WHISTLE_CHAOS_STATE=str(work / "chaos-state.json"),
            )
            command = [str(exe), "known", "--inject-" + mode]
            save(work / "command.json", command)
            try:
                pid, fd = pty.fork()
                if pid == 0:
                    os.chdir(g.game)
                    os.execve(exe, command, child_env)
                g.pid, g.fd = pid, fd
                fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
                status = g.finish(g.read(3))
            finally:
                if g.pid is not None or g.fd is not None:
                    g.cleanup()
            raw = bytes(g.raw)
            records = g.events()
            negative = dict(mode=mode, native_returncode=status, records=records)
            negatives.append(negative)
            save(out / "negative-results.json", negatives)
            assert status == -signal.SIGABRT, negative
            assert raw.count(b"You produce a high whistling sound.") == 1, raw
            diagnostic = (
                b"draws == 0 && next == expected"
                if mode != "budget"
                else b"!memcmp(&saved_u.chaos, &after_u.chaos, sizeof saved_u.chaos)"
            )
            assert diagnostic in raw, raw
            measured = re.search(rb"WHISTLE_INTERVAL (\{[^\r\n]+\})", raw)
            assert measured is not None, raw
            interval = json.loads(measured[1])
            negative["interval"] = interval
            assert interval["return"] == 4
            assert interval["draws"] == (1 if mode == "native" else 0)
            if mode == "budget":
                assert interval["next"] == interval["expected"]
                chaos = json.loads((work / "chaos-state.json").read_text())
                assert chaos["after"]["spent"] == chaos["before"]["spent"] + 1
            else:
                assert interval["next"] != interval["expected"]
            assert not any(e["event"] == "ack" for e in records)
            results.append(
                dict(
                    case="negative-" + mode,
                    enabled=True,
                    observations=[e for e in records if e["v"] == 2],
                )
            )
        assert len(negatives) == 3
        save(out / "negative-results.json", negatives)
        for result in results:
            if result["enabled"]:
                obs = result["observations"]
                expected = [
                    ("none", "enabled", "none"),
                    ("whistling", "started", "none"),
                    (
                        "whistling",
                        "notice",
                        SOUND_CASES[result["case"]][1]
                        if result["case"] in SOUND_CASES
                        else "sound_high",
                    ),
                    ("whistling", "completed", "none"),
                ]
                actual = [
                    (
                        e["observation"]["operation"],
                        e["observation"]["stage"],
                        e["observation"]["fact"],
                    )
                    for e in obs
                ]
                assert actual == expected, (
                    "missing selected whistle events",
                    result["case"],
                    actual,
                    expected,
                )
                start, notice, end = obs[1:]
                assert obs[0]["seq"] == 1 and obs[0]["observation"]["root_seq"] == 0
                assert (start["seq"], notice["seq"], end["seq"]) == (6, 7, 8)
                assert [e["phase"] for e in obs] == [
                    "result",
                    "attempt",
                    "result",
                    "result",
                ]
                for event in obs:
                    assert set(event["observation"]) == {
                        "operation",
                        "stage",
                        "root_seq",
                        "fact",
                    }
                    assert event["detail"] == ""
                assert start["turn"] == notice["turn"] == end["turn"]
                assert start["observation"]["root_seq"] == 0
                assert (
                    notice["observation"]["root_seq"]
                    == end["observation"]["root_seq"]
                    == start["seq"]
                )
    finally:
        signal.alarm(0)
        try:
            after = {p: digest(Path(p)) for p in originals}
            save(out / "manifest-object-hashes-after.json", after)
            assert after == originals, "original objects changed"
            final_selection = native_fixture_selection.prepare(root, selection_env)
            assert (
                final_selection.record()["source_build"]
                == selection.record()["source_build"]
            )
            save(out / "final-source-identity.json", final_selection.record())
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)


@unittest.skipUnless(os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "native opt-in")
class EpisodeWhistleTests(unittest.TestCase):
    def test_selected_ordinary_whistle(self):
        args = []
        for key in ("ROOT", "RECEIPT", "REVISION", "ARTIFACTS"):
            value = os.environ.get("NYARLATHACK_WHISTLE_" + key)
            self.assertIsNotNone(value, "set NYARLATHACK_WHISTLE_" + key)
            args.extend(["--" + key.lower(), value])
        from native_driver_supervision import run_driver

        code, logs = run_driver(
            Path(__file__).resolve(),
            args,
            os.environ["NYARLATHACK_WHISTLE_ROOT"],
            os.environ["NYARLATHACK_WHISTLE_ARTIFACTS"],
        )
        self.assertEqual(
            code, 0, f"whistle driver failed ({code}); diagnostics: {logs}"
        )


if __name__ == "__main__":
    main()
