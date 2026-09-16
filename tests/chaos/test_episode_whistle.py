#!/usr/bin/python3
"""First full doapply baseline; expected selected events remain a RED oracle.

Run from the explicit frozen source root. External fixture/support hashes are
separate from native build identity. This is not the complete Task 6b/8 matrix.
"""

import argparse
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
        results = []
        for case in ("known", "unknown"):
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
                )
                raw, diagnostic = supervisor.bounded(
                    [exe, case],
                    g.game,
                    child_env,
                    work / "terminal",
                    20,
                    True,
                    cancel=cancel,
                )
                assert raw.count(b"You produce a high whistling sound.") == 1
                state = json.loads(diagnostic)
                records = g.events()
                assert not any(e["event"] == "ack" for e in records)
                obs = [e for e in records if e["v"] == 2]
                if not enabled:
                    assert not obs
                pair.append((raw, state))
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
        # Publish genuine action/identity evidence BEFORE the expected missing-events RED.
        save(out / "native-results.json", results)
        for result in results:
            if result["enabled"]:
                obs = result["observations"]
                expected = [
                    ("none", "enabled", "none"),
                    ("whistling", "started", "none"),
                    ("whistling", "notice", "sound_high"),
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
