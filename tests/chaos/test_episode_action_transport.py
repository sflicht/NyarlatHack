#!/usr/bin/python3
"""Selected real-action transport purity; narrow fixture, not moveloop.

Fails closed under optimized Python. External source-build receipt is mandatory.
Write EIO and fsync EIO at enabled/started/notice/completed; short/EINTR remain
covered by the existing lower-level delivery tests, not claimed here.
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


def compare_native(healthy, candidate):
    assert candidate == healthy, "native terminal/input/state/RNG parity"


def validate_transport(healthy, physical, meta, index, kind):
    assert meta["triggered"] == 1, "fault must actually trigger"
    assert meta["committed"] == index
    assert meta["seq_action"] == meta["seq_final"] == index
    assert meta["writes_after"] == meta["syncs_after"] == 0
    lines = healthy.splitlines(keepends=True)
    assert physical == b"".join(lines[: index + int(kind == "fsync")]), (
        "no adoption/rewrite/retiming"
    )


def action_at_prompt(
    g, exe, child_env, work, supervisor, cancel, action, stage, transport
):
    import time

    shutil.copy2(exe, g.game / "dnethack")
    assert supervisor.digest(g.game / "dnethack") == supervisor.digest(exe)
    command = [str(g.game / "dnethack"), action, stage, transport]
    supervisor.save(work / "command.json", command)
    try:
        with (work / "terminal.stderr").open("xb") as diagnostic:
            pid, fd = pty.fork()
            if pid == 0:
                try:
                    resource.setrlimit(resource.RLIMIT_FSIZE, (1048576, 1048576))
                    fcntl.ioctl(
                        0, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0)
                    )
                    os.dup2(diagnostic.fileno(), 2)
                    os.chdir(g.game)
                    os.execve(command[0], command, child_env)
                except BaseException:
                    os._exit(127)
            g.pid, g.fd = pid, fd
            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
            text = g.read(5)
            proofs = []
            for prompt, key in (
                (
                    b"Drink from the fountain?"
                    if action == "fountain"
                    else b"What do you want to use or apply?",
                    b"y" if action == "fountain" else b"a",
                ),
                (b"What do you want to use or apply?", b"a"),
            ):
                assert prompt in text, text
                assert g._reader_pid == pid, (
                    "physical selected input requires native stdin wait"
                )
                assert len(g.raw) <= 65536
                proofs.append(dict(pid=pid, reader_pid=g._reader_pid, input=key.hex()))
                supervisor.save(work / "prompt-proof.json", proofs)
                text = g.send(key)
            deadline = time.monotonic() + 5
            while supervisor.observe(pid) is None:
                cancel.checkpoint()
                assert time.monotonic() < deadline
                assert not g._input_ready(), "no speculative followup input"
                text = g.read(0.2)
                assert b"--More--" not in text
            g.cleanup()
            assert g.exitcode == 0
            assert g.inputs == (["79", "61"] if action == "fountain" else ["61", "61"])
    finally:
        if g.pid is not None or g.fd is not None:
            g.cleanup()
        (work / "terminal.bin").write_bytes(bytes(g.raw))
    assert not (work / "terminal.stderr").read_bytes()
    return dict(
        terminal=bytes(g.raw),
        inputs=g.inputs,
        snapshot=b"".join(
            (g.game / n).read_bytes()
            for n in ("before.bin", "after.bin", "continuation.bin")
        ),
        state=json.loads((g.game / "native.json").read_text()),
    )


def main(argv=None):
    if not __debug__:
        raise RuntimeError("optimized Python is not supported")
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
    spec = importlib.util.spec_from_file_location("fountain_supervision", support)
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
        source = Path(__file__).resolve().with_name("episode_action_transport.c")
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
            root / "src/invent.o": ["--globalize-symbol=nextgetobj"],
            root / "src/o_init.o": ["--globalize-symbol=disco"],
            root / "sys/unix/unixmain.o": ["--redefine-sym=main=original_game_main"],
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
        exe = out / "episode-action-transport"
        run(
            [
                selection.compiler,
                out / "fixture.o",
                *objects,
                "-Wl,--wrap=write,--wrap=fsync",
                "-no-pie",
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
        sys.path.insert(0, str(root))
        from chaos.episodes import parse_episode_event, project_episodes
        import chaos.episodes

        assert Path(chaos.episodes.__file__).resolve() == root / "chaos/episodes.py"
        OwnedGame = supervisor.owned_game_type(gameplay_support.Game, cancel)
        results = []

        def trial(action, stage, transport, enabled=True, negative=None):
            work = out / (
                action
                + "-"
                + stage
                + "-"
                + transport
                + ("-on" if enabled else "-off")
                + ("-" + negative if negative else "")
            )
            g = OwnedGame(selection.tuple_dir, clock, root=work)
            selection.verify_copy(g.game)
            options = work / "options"
            options.write_text("OPTIONS=!splash_screen,!perm_invent\n")
            mail = work / "private-mail"
            mail.write_bytes(b"")
            child = dict(
                env,
                HOME=str(work),
                MAIL=str(mail),
                TERM="xterm",
                LINES="24",
                COLUMNS="80",
                NETHACKOPTIONS="@" + str(options),
                LD_PRELOAD=str(clock),
                NYARLATHACK_RUN_DIR=str(g.run),
                NYARLATHACK_OBSERVATIONS=str(int(enabled)),
            )
            child.pop("ACTION_NEGATIVE", None)
            if negative:
                child["ACTION_NEGATIVE"] = negative
            native = action_at_prompt(
                g, exe, child, work, supervisor, cancel, action, stage, transport
            )
            state = native["state"]
            assert state["action_completed"] and state["continuation_completed"]
            assert native["terminal"].count(b"You produce a high whistling sound.") == (
                1 if action == "fountain" else 2
            )
            assert native["terminal"].count(b"The cool draught refreshes you.") == int(
                action == "fountain"
            )
            calibration = json.loads((g.game / "preflight.json").read_text())
            assert calibration["seed"] == 2 and calibration["count"] == (
                3 if action == "fountain" else 0
            )
            if not negative:
                assert (
                    state["count"] == calibration["count"]
                    and state["next"] == calibration["next"]
                )
            assert state["return"] == (32 if action == "fountain" else 4)
            events = (g.run / "events.jsonl").read_bytes()
            assert len(events) < 65536 and (not events or events.endswith(b"\n"))
            rows = [json.loads(line) for line in events.splitlines()]
            assert [r["seq"] for r in rows] == list(range(1, len(rows) + 1))
            meta = json.loads((g.game / "transport.json").read_text())
            return native, events, meta, work, g.game

        for action in ("whistle", "fountain"):
            off, _, off_meta, _, _ = trial(action, "none", "healthy", False)
            healthy, events, healthy_meta, _, _ = trial(action, "none", "healthy")
            compare_native(off, healthy)
            assert off_meta["triggered"] == healthy_meta["triggered"] == 0
            rows = [json.loads(line) for line in events.splitlines()]
            obs = [r for r in rows if r.get("v") == 2]
            assert [r["observation"]["stage"] for r in obs] == [
                "enabled",
                "started",
                "notice",
                "completed",
                "started",
                "notice",
                "completed",
            ]
            assert [parse_episode_event(line) for line in events.splitlines()] == rows
            projection = project_episodes(events)
            assert sum(group["count"] for group in projection["episodes"]) == 2
            for r in rows:
                assert r["turn"] == 101 and r["sanity"] == 73 and r["insight"] == 19
                assert (r["budget"], r["spent"], r["reserved"], r["last_id"]) == (
                    4,
                    0,
                    0,
                    0,
                )
                assert r["vitals"] == dict(hp=20, hp_max=20, power=20, power_max=23)
            for first, notice, end in (obs[1:4], obs[4:7]):
                assert (
                    notice["observation"]["root_seq"]
                    == end["observation"]["root_seq"]
                    == first["seq"]
                )
                assert first["observation"]["root_seq"] == 0
            for stage in ("started", "notice", "completed", "enabled"):
                index = next(
                    i
                    for i, r in enumerate(rows)
                    if r.get("observation", {}).get("stage") == stage
                )
                for kind in ("write", "fsync"):
                    candidate, physical, meta, work, game = trial(action, stage, kind)
                    compare_native(healthy, candidate)
                    validate_transport(events, physical, meta, index, kind)
                    assert (game / "request.bin").read_bytes() == events.splitlines(
                        keepends=True
                    )[index]
                    # The fsync-failed complete physical line is not committed.
                    committed_prefix = b"".join(
                        physical.splitlines(keepends=True)[:index]
                    )
                    (work / "committed-prefix.jsonl").write_bytes(committed_prefix)
                    if stage != "enabled":
                        public = project_episodes(committed_prefix)
                        assert public["episodes"] == []
                        assert public["coverage"]["incomplete"]["count"] == int(
                            stage in ("notice", "completed")
                        )
                        save(work / "committed-projection.json", public)
                    assert (work / "run/whispers.jsonl").read_bytes() == b""
                    results.append(
                        dict(
                            action=action,
                            stage=stage,
                            transport=kind,
                            committed=index,
                            physical_lines=len(physical.splitlines()),
                            passed=True,
                        )
                    )
                    save(out / "results.json", results)
            for mode in ("native", "raw", "budget"):
                candidate, _, meta, work, _ = trial(
                    action, "notice", "fsync", negative=mode
                )
                assert meta["triggered"] == 1
                state = candidate["state"]
                assert state["count"] == healthy["state"]["count"] + int(
                    mode == "native"
                )
                assert (state["next"] != healthy["state"]["next"]) == (mode != "budget")
                assert state["spent"] == int(mode == "budget")
                assert (candidate["snapshot"] != healthy["snapshot"]) == (
                    mode == "budget"
                )
                try:
                    compare_native(healthy, candidate)
                except AssertionError:
                    save(
                        work / "negative-rejected.json",
                        dict(
                            mode=mode,
                            action_completed=True,
                            oracle="same native comparator",
                            passed=True,
                        ),
                    )
                else:
                    raise AssertionError("negative escaped common comparator")
        assert len(results) == 16
        save(
            out / "result.json",
            dict(
                fault_rows=len(results),
                healthy_off_rows=4,
                negative_rows=6,
                original_objects_unchanged=True,
                scope="linked selected actions, not moveloop",
            ),
        )
    finally:
        signal.alarm(0)
        try:
            after = {p: digest(Path(p)) for p in originals}
            save(out / "manifest-object-hashes-after.json", after)
            assert after == originals
            final = native_fixture_selection.prepare(root, selection_env)
            assert final.record()["source_build"] == selection.record()["source_build"]
            save(out / "final-source-identity.json", final.record())
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
    return 0


@unittest.skipUnless(os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "native opt-in")
class EpisodeActionTransportTests(unittest.TestCase):
    def test_selected_transport(self):
        if not __debug__:
            raise RuntimeError("optimized Python is not supported")
        from native_driver_supervision import run_driver

        args = []
        for key in ("ROOT", "RECEIPT", "REVISION", "ARTIFACTS"):
            value = os.environ["NYARLATHACK_ACTION_TRANSPORT_" + key]
            args.extend(["--" + key.lower(), value])
        code, logs = run_driver(
            Path(__file__).resolve(),
            args,
            os.environ["NYARLATHACK_ACTION_TRANSPORT_ROOT"],
            os.environ["NYARLATHACK_ACTION_TRANSPORT_ARTIFACTS"],
        )
        self.assertEqual(code, 0, str(logs))


if __name__ == "__main__":
    sys.exit(main())
