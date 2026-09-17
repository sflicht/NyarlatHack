#!/usr/bin/python3
"""Strict native fountain acceptance via opt-in unittest discovery or CLI.

Run from the explicit frozen source root. External fixture/support hashes are
separate from native build identity. This is not the complete Task 6b/8 matrix.
The observed-prehook CLI oracle is a manual diagnostic, never acceptance.
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
from native_fixture_config import (
    arguments as fixture_arguments,
    enabled as fixture_enabled,
)


def validate_history(
    records, context, *, enabled, future, fact="water_refreshed", missing_notice=False
):
    """Exact whole history from native context, never from journal envelopes."""
    assert context["safe"] == 1
    expected = []

    def add(event, detail="", safe=0, observation=None, phase="result"):
        record = dict(
            context, v=1, seq=len(expected) + 1, event=event, phase=phase, detail=detail
        )
        record["safe"] = safe
        if observation is not None:
            record.update(v=2, observation=observation)
        expected.append(record)

    if enabled:
        add(
            "observation",
            observation=dict(
                operation="none", stage="enabled", root_seq=0, fact="none"
            ),
        )
    # chaos_start emits session/level before chaos_io_safe increments safe.
    add("session", "new")
    add("level_enter")
    add("safe_point", "level_enter", safe=context["safe"])
    if enabled and future:
        for stage, fact, root, phase in (
            ("started", "none", 0, "attempt"),
            ("notice", fact, 5, "result"),
            ("completed", "none", 5, "result"),
        ):
            if stage == "notice" and missing_notice:
                assert fact == "water_foul"
                continue
            add(
                "observation",
                safe=context["safe"],
                phase=phase,
                observation=dict(
                    operation="fountain_drink", stage=stage, root_seq=root, fact=fact
                ),
            )
    assert records == expected, "complete fountain history mismatch"


REACH_CASES = ("lowlevel-reach-delivered", "lowlevel-reach-noshow")
LEVITATING_CANCEL = "levitating-dodrink-selection-cancel"
DETECTION_CASES = (
    "confirmed-detection-presented",
    "confirmed-detection-map-cancelled",
    "confirmed-detection-empty",
    "confirmed-detection-escape",
    "confirmed-detection-forwarded",
)


def validate_detection_history(records, context, *, enabled, presented):
    prefix = 4 if enabled else 3
    validate_history(records[:prefix], context, enabled=enabled, future=False)
    expected = []
    if enabled:
        stages = [("started", "none", 0, "attempt")]
        if presented:
            stages.append(("notice", "detection_presented", 5, "result"))
        stages.append(("completed", "none", 5, "result"))
        for stage, fact, root, phase in stages:
            expected.append(
                dict(
                    context,
                    v=2,
                    seq=prefix + len(expected) + 1,
                    event="observation",
                    phase=phase,
                    detail="",
                    observation=dict(
                        operation="fountain_drink",
                        stage=stage,
                        root_seq=root,
                        fact=fact,
                    ),
                )
            )
    assert records[prefix:] == expected, "detection presentation history mismatch"


def validate_reach_history(records, context, *, enabled, noshow, prehook=False):
    """Desired blocked history; explicit prehook is diagnostic, not acceptance."""
    prefix = 4 if enabled else 3
    validate_history(records[:prefix], context, enabled=enabled, future=False)
    expected = []
    if enabled:
        stages = [("started", "none", 0, "attempt")]
        if not noshow and not prehook:
            stages.append(("notice", "cannot_reach", 5, "result"))
        stages.append(("completed" if prehook else "blocked", "none", 5, "result"))
        for stage, fact, root, phase in stages:
            expected.append(
                dict(
                    context,
                    v=2,
                    seq=prefix + len(expected) + 1,
                    event="observation",
                    phase=phase,
                    detail="",
                    observation=dict(
                        operation="fountain_drink",
                        stage=stage,
                        root_seq=root,
                        fact=fact,
                    ),
                )
            )
    assert records[prefix:] == expected, (
        "reach: missing expected cannot_reach notice / blocked terminal or invalid history"
    )


def validate_reach_projection(public, *, blocked, prehook=False):
    assert not (blocked and prehook)
    assert public == dict(
        episode_context_v=1,
        scope="selected_whistle_fountain",
        lookback_roots=32,
        episodes=[],
        coverage={
            key: dict(
                count=int(
                    (key == "blocked" and blocked)
                    or (key == "completed_without_notice" and prehook)
                ),
                saturated=False,
            )
            for key in (
                "incomplete",
                "blocked",
                "completed_without_notice",
                "omitted_roots",
            )
        },
    ), "reach coverage must not create a positive episode"


def finish_without_input(g, supervisor, cancel):
    """Never use Game.finish's automatic SPACE/n on a no-input native path."""
    import time

    deadline = time.monotonic() + 5
    while supervisor.observe(g.pid) is None:
        cancel.checkpoint()
        assert time.monotonic() < deadline, "native no-input exit deadline"
        assert not g._input_ready(), "unexpected native stdin wait"
        text = g.read(0.5)
        assert not any(
            p in text for p in (b"--More--", b"[yn", b"What do you", b"Drink from")
        ), text
    g.cleanup()
    assert g.exitcode == 0
    return g.exitcode


def validate_mechanoid_aftermath(state, motion):
    """Private native case-20 oracle: no human hunger draw or vomiting."""
    assert state["hunger_after"] == state["hunger_before"]
    assert state["count"] == 2
    assert motion == dict(
        multi=0, reason="", occupation=False, afternmv=False, nomovemsg=False
    )


def validate_legacy_pair(off, on):
    """Only the enabled marker's single sequence offset is normalized."""
    legacy = [dict(record, seq=record["seq"] - 1) for record in on if record["v"] == 1]
    assert off == legacy, "legacy envelope OFF/ON mismatch"


def validate_negative(mode, status, raw, diagnostic, interval, probe):
    """Reject arbitrary crashes: require completed action and exact purity abort."""
    assert mode in ("native", "raw", "budget")
    assert status == -signal.SIGABRT
    assert raw.count(b"The cool draught refreshes you.") == 1
    assert b"Drink from the fountain?" in raw
    assert interval["action_completed"] is True
    assert interval["case"] == "confirmed-refreshed"
    assert interval["injection"] == mode
    assert interval["returncode"] == interval["move_quaffed"] == 32
    assert interval["seed"] == probe["seed"]
    assert interval["expected_count"] == probe["count"] == 3
    assert interval["expected_next"] == probe["next"]
    assert probe["changed_next"] != probe["next"]
    assert interval["count"] == probe["count"] + int(mode == "native")
    assert interval["next"] == probe["next" if mode == "budget" else "changed_next"]
    assert interval["spent_before"] == 0
    assert interval["spent_after"] == int(mode == "budget")
    assert interval["hunger_after"] - interval["hunger_before"] == probe["hunger"]
    expression = (
        b"!memcmp(&before,&normalized,sizeof before)"
        if mode == "budget"
        else b"result == (decline ? MOVE_CANCELLED : MOVE_QUAFFED) && count == t.count && next == t.next"
    )
    assert re.search(
        rb"episode_fountain\.c:\d+: main: Assertion [`']"
        + re.escape(expression)
        + rb"' failed\.",
        diagnostic,
    ), diagnostic


def confirmed_at_prompt(
    g, exe, child_env, work, supervisor, cancel, case, *, injection=None
):
    """Use pinned stdin-read proof; physical fountain confirmation."""
    # Game readiness pins /proc/exe to this private path. The native tuple was
    # verified before replacing ONLY this private copy with the linked fixture.
    shutil.copy2(exe, g.game / "dnethack")
    assert supervisor.digest(g.game / "dnethack") == supervisor.digest(exe)
    command = [
        str(g.game / "dnethack"),
        case,
    ]
    assert injection in (None, "native", "raw", "budget")
    if injection is not None:
        assert case == "confirmed-refreshed"
        command.append("--inject-" + injection)
    supervisor.save(work / "terminal.command.json", command)
    diagnostic_path = work / "terminal.stderr"
    try:
        cancel.checkpoint()
        with diagnostic_path.open("xb") as diagnostic:
            pid, fd = pty.fork()
            if pid == 0:
                try:
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
            prompt = g.read(5)
            assert len(g.raw) <= 65536, "selection prompt cap"
            if case in REACH_CASES or case == LEVITATING_CANCEL:
                assert b"Drink from the fountain?" not in prompt, prompt
                proof = []
                if case == LEVITATING_CANCEL:
                    assert b"What do you want to drink?" in prompt, prompt
                    assert g._reader_pid == pid, "native selection stdin read required"
                    (work / "drink-selection-prompt.stdout").write_bytes(bytes(g.raw))
                    proof.append(dict(pid=pid, reader_pid=g._reader_pid, input="1b"))
                    response = g.send(b"\x1b")
                else:
                    assert g._reader_pid is None, "lowlevel guard must not read stdin"
                    response = prompt
                supervisor.save(work / "prompt-proof.json", proof)
                assert not any(
                    p in response
                    for p in (b"--More--", b"[yn", b"What do you", b"Drink from")
                ), response
                finish_without_input(g, supervisor, cancel)
                assert g.inputs == (["1b"] if case == LEVITATING_CANCEL else [])
                assert diagnostic_path.stat().st_size <= supervisor.LIMIT
                return bytes(g.raw), diagnostic_path.read_bytes()
            assert b"Drink from the fountain?" in prompt, prompt
            assert g._reader_pid == pid, "native terminal stdin read required"
            (work / "selection-prompt.stdout").write_bytes(bytes(g.raw))
            decline = case == "decline-selection-cancel"
            first = b"n" if decline else b"y"
            proof = [dict(pid=pid, reader_pid=g._reader_pid, input=first.hex())]
            supervisor.save(work / "prompt-proof.json", proof)
            response = g.send(first)
            if case in DETECTION_CASES:
                has_prompt = case in (DETECTION_CASES[0], *DETECTION_CASES[3:])
                dismiss = b"\x1b" if case == DETECTION_CASES[3] else b" "
                (work / "detection-action.stdout").write_bytes(
                    bytes(g.raw)[len((work / "selection-prompt.stdout").read_bytes()) :]
                )
                action_bytes = (work / "detection-action.stdout").read_bytes()
                # Exact native TTY glyph output at the prepared map row. This
                # exists even with WIN_MAP cancelled: NOT a delivery ACK.
                glyphs = (
                    b"\x1b[12;10H\x1b[1m\x1b[37m@\x1b[0m\x1b[C\x1b[1m\x1b[37md\x1b[0m"
                )
                assert (glyphs in action_bytes) == (case != DETECTION_CASES[2])
                if has_prompt:
                    assert b"You sense the presence of monsters." not in response
                    assert response.count(b"--More--") == 1
                    assert g._reader_pid == pid, "fresh detection stdin read required"
                    prefix = (g.run / "events.jsonl").read_bytes()
                    assert prefix.endswith(b"\n")
                    records = [json.loads(line) for line in prefix.splitlines()]
                    assert not any(
                        r.get("observation", {}).get("stage") in ("notice", "completed")
                        for r in records
                    )
                    (work / "detection-prompt.events.jsonl").write_bytes(prefix)
                    (work / "detection-prompt.stdout").write_bytes(bytes(g.raw))
                    proof.append(
                        dict(pid=pid, reader_pid=g._reader_pid, input=dismiss.hex())
                    )
                    supervisor.save(work / "prompt-proof.json", proof)
                    response = g.send(dismiss)
                else:
                    assert b"--More--" not in response
                finish_without_input(g, supervisor, cancel)
                assert g.inputs == (["79", dismiss.hex()] if has_prompt else ["79"])
                return bytes(g.raw), diagnostic_path.read_bytes()
            if decline:
                assert b"What do you want to drink?" in response, response
                assert g._reader_pid == pid, "fresh native selection read required"
                assert len(g.raw) <= 65536, "selection prompt cap"
                (work / "drink-selection-prompt.stdout").write_bytes(response)
                proof.append(dict(pid=pid, reader_pid=g._reader_pid, input="1b"))
                supervisor.save(work / "prompt-proof.json", proof)
                response = g.send(b"\x1b")
            status = g.finish(response)
            assert status == (0 if injection is None else -signal.SIGABRT), status
            assert g.inputs == (["6e", "1b"] if decline else ["79"]), g.inputs
    finally:
        if g.pid is not None or g.fd is not None:
            g.cleanup()
        (work / "terminal.stdout").write_bytes(bytes(g.raw))
    # Retained post-exit cap; this is not an in-flight stderr file-size limit.
    assert diagnostic_path.stat().st_size <= supervisor.LIMIT
    return bytes(g.raw), diagnostic_path.read_bytes()


def main(argv=None):
    if not __debug__:
        raise RuntimeError("optimized Python is not supported")
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "receipt", "revision", "artifacts"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument(
        "--oracle", choices=("observed-prehook", "strict-desired"), required=True
    )
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
        source = Path(__file__).resolve().with_name("episode_fountain.c")
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
        exe = out / "episode-fountain"
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
        assert [r["seed"] for r in calibration] == list(range(1, 257))
        calls = sum(r["count"] + 1 for r in calibration)
        assert calls <= 1024
        chosen = next(r for r in calibration if r["fate"] < 10 and r["dry"] > 0)
        # Separate real-stream calibration, no extra native actions or rerolls.
        probe = json.loads(
            supervisor.bounded(
                [exe, "--probe-controls"],
                out,
                dict(env, FOUNTAIN_SEED=str(chosen["seed"])),
                out / "control-probe",
                45,
                cancel=cancel,
            )[0]
        )
        for key in ("seed", "count", "next", "hunger"):
            assert probe[key] == chosen[key]
        assert probe["changed_next"] != chosen["next"]
        assert probe["calls"] == chosen["count"] + 2
        save(out / "negative-calibration.json", probe)
        save(
            out / "rng-calibration.json",
            dict(candidates=calibration, chosen=chosen, preflight_calls=calls),
        )
        sys.path.insert(0, str(root))
        from chaos.episodes import parse_episode_event, project_episodes
        import chaos.episodes

        assert Path(chaos.episodes.__file__).resolve() == root / "chaos/episodes.py"
        OwnedGame = supervisor.owned_game_type(gameplay_support.Game, cancel)
        results = []
        reach_failures = []
        detection_failures = []
        detection_calibration = json.loads(
            run([exe, "--calibrate-detection"], "detection-seed-preflight")
        )
        assert [r["seed"] for r in detection_calibration] == list(range(1, 257))
        detection_calls = sum(r["count"] + 1 for r in detection_calibration)
        assert detection_calls <= 1024
        detection_chosen = next(
            r for r in detection_calibration if r["fate"] == 26 and r["dry"] > 0
        )
        assert detection_chosen["count"] == 3 and detection_chosen["hunger"] == 0
        save(
            out / "detection-calibration.json",
            dict(
                candidates=detection_calibration,
                chosen=detection_chosen,
                preflight_calls=detection_calls,
                action_rerolls=0,
                trace=[
                    "rnd(30)",
                    "rn2(19) wisdom exercise",
                    "rn2(3) dryup",
                    "rn2(100000) sentinel",
                ],
            ),
        )
        mech_calibration = json.loads(
            run([exe, "--calibrate-mechanoid"], "mechanoid-seed-preflight")
        )
        assert [r["seed"] for r in mech_calibration] == list(range(1, 257))
        mech_calls = sum(r["count"] + 1 for r in mech_calibration)
        assert mech_calls <= 768
        mech_chosen = next(
            r for r in mech_calibration if r["fate"] == 20 and r["dry"] > 0
        )
        assert mech_chosen["count"] == 2 and mech_chosen["hunger"] == 0
        save(
            out / "mechanoid-calibration.json",
            dict(
                candidates=mech_calibration,
                chosen=mech_chosen,
                preflight_calls=mech_calls,
                trace=["rnd(30)", "rn2(3) in dryup", "rn2(100000) sentinel"],
                action_rerolls=0,
            ),
        )
        foul_chosen = next(r for r in calibration if r["fate"] == 20 and r["dry"] > 0)
        save(out / "foul-calibration.json", foul_chosen)
        for case in (
            "decline-selection-cancel",
            "confirmed-refreshed",
            "confirmed-foul",
            "confirmed-foul-mechanoid",
            *REACH_CASES,
            LEVITATING_CANCEL,
            *DETECTION_CASES,
        ):
            detection = case in DETECTION_CASES
            reach = case in REACH_CASES
            levitating = reach or case == LEVITATING_CANCEL
            is_foul = case in ("confirmed-foul", "confirmed-foul-mechanoid")
            action_seed = (
                mech_chosen
                if case == "confirmed-foul-mechanoid"
                else (foul_chosen if is_foul else chosen)
            )
            if levitating:
                action_seed = dict(seed=1)
            if detection:
                action_seed = detection_chosen
            pair, histories = [], []
            for enabled in (False, True):
                work = out / (case + "-" + ("on" if enabled else "off"))
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
                    NYARLATHACK_OBSERVATIONS=str(int(enabled)),
                    FOUNTAIN_SEED=str(action_seed["seed"]),
                    FOUNTAIN_STATE=str(work / "state.json"),
                )
                raw, diagnostic = confirmed_at_prompt(
                    g, exe, child_env, work, supervisor, cancel, case
                )
                assert raw.count(b"The cool draught refreshes you.") == int(
                    case == "confirmed-refreshed"
                )
                assert raw.count(b"The water is foul!  You gag and vomit.") == int(
                    case == "confirmed-foul"
                )
                assert raw.count(
                    b"The water is foul! It offends your olfactory receptors."
                ) == int(case == "confirmed-foul-mechanoid")
                state = json.loads(diagnostic)
                assert state["native_oracles_passed"] is True
                assert state["case"] == case
                if levitating:
                    assert state["seed"] == 1
                    assert state["count"] == int(reach)
                    assert state["next"] == state["expected_next"]
                    assert state["hunger_after"] == state["hunger_before"]
                    assert state["hunger_delta"] == 0
                    assert state["return"] == (0 if reach else state["move_cancelled"])
                    assert raw.count(b"You start to float in the air!") == 1
                    assert raw.count(
                        b"You are floating high above the fountain."
                    ) == int(case == REACH_CASES[0])
                    assert b"Drink from the fountain?" not in raw
                    assert raw.count(b"What do you want to drink?") == int(not reach)
                    assert b"You sense" not in raw and b"--More--" not in raw
                elif case != "decline-selection-cancel":
                    assert state["return"] == state["move_quaffed"]
                    for key in ("seed", "count", "next", "fate", "dry"):
                        assert state[key] == action_seed[key]
                    assert (
                        state["hunger_after"] - state["hunger_before"]
                        == action_seed["hunger"]
                    )
                else:
                    assert state["return"] == state["move_cancelled"]
                    assert state["seed"] == chosen["seed"]
                    assert state["count"] == 0
                    assert state["next"] == state["expected_next"]
                    assert state["hunger_after"] == state["hunger_before"]
                assert state["status_before"] == state["status_after"]
                records_raw = (g.run / "events.jsonl").read_bytes()
                records = [
                    parse_episode_event(line) for line in records_raw.splitlines()
                ]
                projection = project_episodes(records_raw)
                save(work / "projection.json", projection)
                native = json.loads((work / "state.json").read_text())
                obs = [r for r in records if r["v"] == 2]
                assert native["context_before"] == native["context_after"]
                assert native["inventory_before_hex"] == native["inventory_after_hex"]
                assert native["seq_before"] == 3 + int(enabled)
                assert native["seq_after"] == len(records)
                # A strict pre-hook run must still validate the entire actual
                # prefix, before reporting only the missing future feature.
                future = (
                    args.oracle == "strict-desired"
                    and enabled
                    and case != "decline-selection-cancel"
                    and len(obs) > 1
                )
                if detection:
                    presented = case in (DETECTION_CASES[0], DETECTION_CASES[3])
                    has_prompt = presented or case == DETECTION_CASES[4]
                    empty = case == DETECTION_CASES[2]
                    assert b"You sense the presence of monsters." not in raw
                    assert raw.count(b"--More--") == int(has_prompt)
                    private = native["detection"]
                    if has_prompt:
                        prefix = (work / "detection-prompt.events.jsonl").read_bytes()
                        assert [
                            json.loads(line) for line in prefix.splitlines()
                        ] == records[: 5 if enabled else 3]
                    assert private["population"] == int(not empty)
                    assert private["monster_bytes_unchanged"] is True
                    assert private["wisdom_before"] == 0
                    assert (
                        private["wisdom_after"]
                        == private["predicted_wisdom"]
                        == detection_chosen["wisdom"]
                    )
                    assert (
                        private["map_flags_before"]
                        == private["map_flags_after"]
                        == int(case == DETECTION_CASES[1])
                    )
                    if not empty:
                        assert private["monster_hp"] > 0
                        assert (private["monster_x"], private["monster_y"]) == (12, 10)
                    if case in DETECTION_CASES[3:]:
                        followup = native["presentation_followup"]
                        forwarded = case == DETECTION_CASES[4]
                        assert followup["message_flags_before"] == 0
                        assert followup["message_flags_after"] == int(not forwarded)
                        assert (
                            followup["forwarded_calls"] == followup["forwarded_returns"]
                        )
                        assert followup["forwarded_blocking_maps"] == int(forwarded)
                        assert (followup["forwarded_calls"] > 0) == forwarded
                    try:
                        validate_detection_history(
                            records,
                            native["context_before"],
                            enabled=enabled,
                            presented=presented,
                        )
                    except AssertionError:
                        assert enabled and presented
                        validate_detection_history(
                            records,
                            native["context_before"],
                            enabled=True,
                            presented=False,
                        )
                        detection_failures.append(
                            dict(
                                case=case,
                                missing_expected_observations=[
                                    "fountain_drink.detection_presented"
                                ],
                                actual="started -> completed without notice",
                            )
                        )
                    if not enabled or not presented or detection_failures:
                        validate_reach_projection(
                            projection, blocked=False, prehook=enabled
                        )
                    else:
                        if case == DETECTION_CASES[3]:
                            assert projection == dict(
                                episode_context_v=1,
                                scope="selected_whistle_fountain",
                                lookback_roots=32,
                                episodes=projection["episodes"],
                                coverage={
                                    key: dict(count=0, saturated=False)
                                    for key in (
                                        "incomplete",
                                        "blocked",
                                        "completed_without_notice",
                                        "omitted_roots",
                                    )
                                },
                            )
                        assert projection["episodes"] == [
                            dict(
                                operation="fountain_drink",
                                count=1,
                                saturated=False,
                                evidence=[
                                    dict(
                                        root_seq=5,
                                        notice_seq=6,
                                        end_seq=7,
                                        fact="detection_presented",
                                    )
                                ],
                            )
                        ]
                elif reach:
                    noshow = case == REACH_CASES[1]
                    # Existing reach cases remain independently strict.
                    try:
                        validate_reach_history(
                            records,
                            native["context_before"],
                            enabled=enabled,
                            noshow=noshow,
                        )
                    except AssertionError:
                        # Only the exact known prehook history is a missing-feature
                        # diagnostic. Every other malformed journal fails here.
                        validate_reach_history(
                            records,
                            native["context_before"],
                            enabled=enabled,
                            noshow=noshow,
                            prehook=True,
                        )
                        assert enabled
                        validate_reach_projection(
                            projection, blocked=False, prehook=True
                        )
                        reach_failures.append(
                            dict(
                                case=case,
                                enabled=True,
                                missing_expected_observations=(
                                    ["fountain_drink.cannot_reach"]
                                    if not noshow
                                    else []
                                )
                                + ["fountain_drink.blocked"],
                                actual="started -> completed without notice",
                                refusal_delivered=not noshow,
                            )
                        )
                    else:
                        validate_reach_projection(projection, blocked=enabled)
                else:
                    validate_history(
                        records,
                        native["context_before"],
                        enabled=enabled,
                        future=False if levitating else future,
                        fact="water_foul" if is_foul else "water_refreshed",
                        missing_notice=is_foul and enabled and len(obs) == 3,
                    )
                if levitating:
                    assert native["reach"] == dict(
                        lowlevel_calls=int(reach),
                        void_returned=reach,
                        dodrink_calls=int(not reach),
                        timeout_before=500,
                        timeout_after=500,
                    )
                    assert native["motion"] == dict(
                        multi=0,
                        reason="",
                        occupation=False,
                        afternmv=False,
                        nomovemsg=False,
                    )
                    if not reach:
                        validate_reach_projection(projection, blocked=False)
                if is_foul and enabled and len(obs) == 3:
                    assert projection["episodes"] == []
                    assert projection["coverage"]["completed_without_notice"] == dict(
                        count=1, saturated=False
                    )
                if case == "confirmed-foul":
                    assert native["vomiting"] == dict(
                        multi=-2,
                        reason="vomiting",
                        occupation=False,
                        afternmv=False,
                        nomovemsg=False,
                        free_action=False,
                    )
                if case == "confirmed-foul-mechanoid":
                    validate_mechanoid_aftermath(state, native["motion"])
                if not future:
                    assert projection["episodes"] == []
                histories.append(records)
                pair.append(
                    (
                        raw,
                        state,
                        g.inputs,
                        native["map_before_hex"],
                        native["map_after_hex"],
                        native.get("detection"),
                        native.get("presentation_followup"),
                    )
                )
                results.append(
                    dict(
                        case=case,
                        enabled=enabled,
                        state=state,
                        observations=obs,
                        records=records,
                        projection=projection,
                        native_returncode=0,
                    )
                )
                save(out / "native-results.json", results)
            assert pair[0] == pair[1], "terminal/input/native state OFF/ON mismatch"
            validate_legacy_pair(*histories)
        assert len(results) == 24
        save(out / "native-results.json", results)
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
                FOUNTAIN_SEED=str(chosen["seed"]),
                FOUNTAIN_STATE=str(work / "state.json"),
                FOUNTAIN_INTERVAL=str(work / "interval.json"),
            )
            raw, diagnostic = confirmed_at_prompt(
                g,
                exe,
                child_env,
                work,
                supervisor,
                cancel,
                "confirmed-refreshed",
                injection=mode,
            )
            interval = json.loads((work / "interval.json").read_text())
            validate_negative(mode, g.exitcode, raw, diagnostic, interval, probe)
            cleanup = json.loads((work / "cleanup.json").read_text())
            assert cleanup == dict(pid=None, returncode=-signal.SIGABRT, errors=[])
            assert g.pid is None and g.fd is None
            assert g.inputs == ["79"]
            # Full-state file is deliberately not written after a purity abort.
            assert not (work / "state.json").exists()
            records_raw = (g.run / "events.jsonl").read_bytes()
            records = [parse_episode_event(line) for line in records_raw.splitlines()]
            validate_history(
                records,
                interval["context_before"],
                enabled=True,
                future=len(results[3]["observations"]) > 1,
            )
            after_context = dict(interval["context_after"])
            after_context["spent"] -= int(mode == "budget")
            # chaos_budget reports remaining allowance, not capacity; the
            # injected spent point must reduce this derived value by one.
            after_context["budget"] += int(mode == "budget")
            assert after_context == interval["context_before"]
            negative = dict(
                mode=mode,
                native_returncode=g.exitcode,
                interval=interval,
                records=records,
                inputs=g.inputs,
                cleanup=cleanup,
            )
            negatives.append(negative)
            save(out / "negative-results.json", negatives)
        assert len(negatives) == 3
        # native_rng.h: 34 calls in test_rng_control + one in its unused
        # negative-control dispatch, for every native process including calibration.
        header_calls = 35
        per_action_calls = [
            (header_calls + 2 * (result["state"]["count"] + 1))
            if result["case"] in (*REACH_CASES, LEVITATING_CANCEL)
            else header_calls
            + (
                mech_chosen["count"]
                if result["case"] == "confirmed-foul-mechanoid"
                else chosen["count"]
            )
            + 1
            + int(result["case"] == "decline-selection-cancel")
            + result["state"]["count"]
            + 1
            for result in results
        ]
        negative_action_calls = [
            header_calls + chosen["count"] + 1 + row["interval"]["count"] + 1
            for row in negatives
        ]
        probe_calls = header_calls + probe["calls"]
        total_calls = (
            header_calls
            + calls
            + header_calls
            + mech_calls
            + sum(per_action_calls)
            + probe_calls
            + sum(negative_action_calls)
            + header_calls
            + detection_calls
        )
        assert total_calls < 4096
        save(
            out / "rng-call-budget.json",
            dict(
                calibration_calls=header_calls + calls,
                mechanoid_calibration_calls=header_calls + mech_calls,
                detection_calibration_calls=header_calls + detection_calls,
                per_action_calls=per_action_calls,
                negative_action_calls=negative_action_calls,
                probe_calls=probe_calls,
                raw_libc_injected_calls=1,
                raw_libc_note="extra random() is not a native reseed counter invocation",
                total_calls=total_calls,
                scope="native RNG control/preflight/action/sentinel; initialization excluded",
            ),
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

    # Strict feature assertion only AFTER native paired results and source guards.
    if args.oracle == "observed-prehook":
        for result in results:
            assert len(result["observations"]) == int(result["enabled"])
            assert result["projection"]["episodes"] == []
        save(
            out / "oracle-result.json",
            dict(
                oracle=args.oracle,
                native_oracles_passed=True,
                acceptance=False,
                actions=len(results) + len(negatives),
                normal_actions=len(results),
                negative_actions=len(negatives),
            ),
        )
        return 0
    obs = results[3]["observations"]
    if len(obs) == 1:
        save(
            out / "strict-failure.json",
            dict(
                oracle=args.oracle,
                native_oracles_passed=True,
                case="confirmed-refreshed",
                native_return_verified=True,
                actions=len(results) + len(negatives),
                negative_controls_passed=len(negatives),
                missing_expected_observations=[
                    "fountain_drink.started",
                    "fountain_drink.water_refreshed",
                    "fountain_drink.completed",
                ],
            ),
        )
        print(
            "confirmed-refreshed: missing expected observations: fountain_drink started / water_refreshed notice / completed; native_return verified",
            file=sys.stderr,
        )
        return 1
    root_seq = 5
    notice, end = obs[2:]
    assert results[3]["projection"]["episodes"] == [
        dict(
            operation="fountain_drink",
            count=1,
            saturated=False,
            evidence=[
                dict(
                    root_seq=root_seq,
                    notice_seq=notice["seq"],
                    end_seq=end["seq"],
                    fact="water_refreshed",
                )
            ],
        )
    ]
    foul = results[5]
    if len(foul["observations"]) == 3:
        save(
            out / "strict-failure.json",
            dict(
                oracle=args.oracle,
                acceptance=False,
                native_oracles_passed=True,
                case="confirmed-foul",
                native_return_verified=True,
                actions=len(results) + len(negatives),
                negative_controls_passed=len(negatives),
                missing_expected_observations=["fountain_drink.water_foul"],
            ),
        )
        print(
            "confirmed-foul: missing expected water_foul notice; native hunger/vomiting/RNG/return verified",
            file=sys.stderr,
        )
        return 1
    assert foul["projection"]["episodes"] == [
        dict(
            operation="fountain_drink",
            count=1,
            saturated=False,
            evidence=[dict(root_seq=5, notice_seq=6, end_seq=7, fact="water_foul")],
        )
    ]
    mechanoid = results[7]
    if len(mechanoid["observations"]) == 3:
        save(
            out / "strict-failure.json",
            dict(
                oracle=args.oracle,
                acceptance=False,
                native_oracles_passed=True,
                case="confirmed-foul-mechanoid",
                native_return_verified=True,
                actions=len(results) + len(negatives),
                normal_actions=len(results),
                preserved_normal_actions=6,
                negative_controls_passed=len(negatives),
                missing_expected_observations=["fountain_drink.water_foul"],
            ),
        )
        print(
            "confirmed-foul-mechanoid: missing expected water_foul notice; native alternate wording/hunger/motion/RNG/return verified",
            file=sys.stderr,
        )
        return 1
    assert mechanoid["projection"]["episodes"] == [
        dict(
            operation="fountain_drink",
            count=1,
            saturated=False,
            evidence=[dict(root_seq=5, notice_seq=6, end_seq=7, fact="water_foul")],
        )
    ]
    if reach_failures:
        save(
            out / "strict-failure.json",
            dict(
                oracle=args.oracle,
                acceptance=False,
                native_oracles_passed=True,
                source_guards_passed=True,
                actions=len(results) + len(negatives),
                normal_actions=len(results),
                preserved_normal_actions=8,
                negative_controls_passed=len(negatives),
                failures=reach_failures,
            ),
        )
        for failure in reach_failures:
            print(
                failure["case"]
                + ": missing expected "
                + " / ".join(failure["missing_expected_observations"])
                + "; native return/state/RNG/delivery distinction verified",
                file=sys.stderr,
            )
        return 1
    if detection_failures:
        save(
            out / "strict-failure.json",
            dict(
                oracle=args.oracle,
                acceptance=False,
                native_oracles_passed=True,
                source_guards_passed=True,
                actions=len(results) + len(negatives),
                normal_actions=len(results),
                preserved_normal_actions=14,
                negative_controls_passed=len(negatives),
                failures=detection_failures,
            ),
        )
        print(
            "confirmed-detection-presented: missing detection_presented notice; native map/prompt/input/state/RNG and cancelled/empty controls verified",
            file=sys.stderr,
        )
        return 1
    return 0


@unittest.skipUnless(fixture_enabled("fountain"), "native opt-in")
class EpisodeFountainTests(unittest.TestCase):
    def test_strict_fountain(self):
        if not __debug__:
            self.fail("optimized Python is not supported")
        values, args = fixture_arguments(
            "fountain", Path(__file__).resolve().parents[2]
        )
        args.extend(["--oracle", "strict-desired"])
        from native_driver_supervision import run_driver

        code, logs = run_driver(
            Path(__file__).resolve(), args, values["root"], values["artifacts"]
        )
        self.assertEqual(
            code, 0, f"fountain driver failed ({code}); diagnostics: {logs}"
        )


if __name__ == "__main__":
    sys.exit(main())
