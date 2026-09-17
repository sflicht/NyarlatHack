#!/usr/bin/env python3
"""External-only all-fate native batch; immutable source-build objects required."""

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import native_observation_contract as wire

import pty
import resource
import shutil
import struct
import subprocess
import sys
import termios
import time

# External helper is sibling-bound and copied/hashed in source manifests.
assert Path(wire.__file__).resolve() == Path(__file__).resolve().with_name(
    "native_observation_contract.py"
)
CURRENT, HISTORICAL = wire.CURRENT, wire.HISTORICAL

DOMAINS = (
    "player",
    "youmonst",
    "terrain",
    "level_flags",
    "inventory",
    "floor",
    "monsters",
    "migrating_monsters",
    "migrating_objects",
    "traps",
    "discovery",
    "definitions",
    "vitals",
    "flags",
    "globals",
    "motion",
    "grid",
)


# Finite fixture configuration, not a public observation vocabulary.
SPECIAL_CASES = [
    dict(
        case=name,
        fate=fate,
        blessed=blessed,
        luck=luck,
        hallucination=hallucination,
        no_mouth=no_mouth,
        restore=restore,
    )
    for name, fate, blessed, luck, hallucination, no_mouth, restore in (
        ("magic-refresh", 1, True, 0, False, False, False),
        ("magic-low-luck", 10, True, 0, False, False, True),
        ("magic-high-luck", 10, True, 4, False, False, True),
        ("magic-negative-luck", 20, True, -1, False, False, False),
        ("depletion", 10, False, 0, False, False, False),
        ("hallucination-map", 26, False, 0, True, False, False),
        ("no-mouth", 10, False, 0, False, True, False),
    )
]


def validate_pair(off, on):
    assert off["state"]["count"] == on["state"]["count"], "native draw count mismatch"
    assert off["state"]["next"] == on["state"]["next"], "native continuation mismatch"
    assert off == on, "canonical native state / terminal / input / RNG mismatch"


def validate_history(raw, before, after, fate, enabled, case=None, *, policy):
    from chaos.episodes import parse_episode_event, project_episodes

    records = [parse_episode_event(line) for line in raw.splitlines()]
    wire.validate_rows(records, policy)
    public = project_episodes(raw)
    expected = []

    def add(context, event, detail="", safe=1, observation=None, phase="result"):
        row = dict(
            context,
            v=policy[0],
            seq=len(expected) + 1,
            event=event,
            detail=detail,
            phase=phase,
            safe=safe,
        )
        if observation is not None:
            row.update(v=policy[1], observation=observation)
        if policy == CURRENT:
            row["cosmetic"] = dict(seen=0, last_turn=0)
        expected.append(row)

    def obs(context, stage, root=0, fact="none", safe=1):
        add(
            context,
            "observation",
            safe=safe,
            phase="attempt" if stage == "started" else "result",
            observation=dict(
                operation="none" if stage == "enabled" else "fountain_drink",
                stage=stage,
                root_seq=root,
                fact=fact,
            ),
        )

    if enabled:
        obs(before, "enabled", safe=0)
    add(before, "session", "new", safe=0)
    add(before, "level_enter", safe=0)
    add(before, "safe_point", "level_enter")
    if fate == 23:
        add(before, "curio", "expired")
    fact = (
        "water_refreshed"
        if fate < 10
        else "water_foul"
        if fate == 20
        else "detection_presented"
        if fate == 26
        else None
    )
    root = 6 if fate == 23 else 5
    rootless = case == "no-mouth"
    if enabled and not rootless:
        obs(before, "started")
        if fact:
            obs(before if case else after, "notice", root, fact)
        obs(after, "completed", root)
    assert records == expected, "exact native history mismatch"
    groups = []
    if enabled and fact and not rootless:
        groups = [
            dict(
                operation="fountain_drink",
                count=1,
                saturated=False,
                evidence=[
                    dict(
                        root_seq=root, notice_seq=root + 1, end_seq=root + 2, fact=fact
                    )
                ],
            )
        ]
    expected_public = dict(
        episode_context_v=1,
        scope="selected_whistle_fountain",
        lookback_roots=32,
        episodes=groups,
        coverage={
            k: dict(
                count=int(
                    k == "completed_without_notice"
                    and enabled
                    and not fact
                    and not rootless
                ),
                saturated=False,
            )
            for k in (
                "incomplete",
                "blocked",
                "completed_without_notice",
                "omitted_roots",
            )
        },
    )
    assert public == expected_public, "exact public projection mismatch"
    return records


def validate_negative(healthy, injected, mode):
    """Require the intended native delta, then reject through the common oracle."""
    import copy

    expected = copy.deepcopy(healthy)
    state, base = injected["state"], healthy["state"]
    cause = "canonical native state / terminal / input / RNG mismatch"
    if mode in ("native", "raw"):
        assert state["count"] == base["count"] + int(mode == "native")
        assert state["next"] != base["next"]
        expected["state"]["count"] = state["count"]
        expected["state"]["next"] = state["next"]
        cause = (
            "native draw count mismatch"
            if mode == "native"
            else "native continuation mismatch"
        )
    else:
        assert mode == "budget"
        assert state["context_after"]["spent"] == base["context_after"]["spent"] + 1
        assert state["context_after"]["budget"] == base["context_after"]["budget"] - 1
        assert state["after"]["player"] != base["after"]["player"]
        expected_player = bytearray.fromhex(base["after"]["player"])
        offset, size = base["spent_layout"]
        assert (
            int.from_bytes(
                expected_player[offset : offset + size], sys.byteorder, signed=True
            )
            == base["context_after"]["spent"]
        )
        expected_player[offset : offset + size] = state["context_after"][
            "spent"
        ].to_bytes(size, sys.byteorder, signed=True)
        expected["state"]["after"]["player"] = expected_player.hex()
        expected["state"]["context_after"].update(
            spent=state["context_after"]["spent"],
            budget=state["context_after"]["budget"],
        )
    assert injected == expected, "negative control changed unrelated native evidence"
    try:
        validate_pair(healthy, injected)
    except AssertionError as exc:
        assert str(exc) == cause, (cause, str(exc))
        return cause
    raise AssertionError("negative control accepted")


def validate_manifest(rows):
    assert [r["fate"] for r in rows] == list(range(1, 31))
    assert all(1 <= r["seed"] <= 4096 for r in rows)


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(p, value):
    p.write_text(json.dumps(value, indent=2) + "\n")


def main():
    if not __debug__ or sys.flags.optimize:
        raise RuntimeError("optimized Python is forbidden")
    # Require the existing external subreaper, not an ambient promise/flag.
    parent_command = Path(f"/proc/{os.getppid()}/cmdline").read_bytes().split(b"\0")
    if not any(
        Path(os.fsdecode(arg)).name == "native_driver_supervision.py"
        for arg in parent_command
        if arg
    ):
        raise RuntimeError("native_driver_supervision.py outer context required")
    if any(
        os.environ.get(key)
        for key in (
            "FOUNTAIN_INJECTION",
            "FOUNTAIN_CASE",
            "LD_PRELOAD",
            "LD_LIBRARY_PATH",
        )
    ):
        raise RuntimeError("unsafe ambient native override")
    parser = argparse.ArgumentParser()
    for key in ("root", "receipt", "revision", "artifacts"):
        parser.add_argument("--" + key, required=True)
    args = parser.parse_args()
    root, receipt, out = map(Path, (args.root, args.receipt, args.artifacts))
    assert Path.cwd() == root and out.is_relative_to("/tmp")
    trusted = root / "tests/chaos"
    sys.path.insert(0, str(trusted))
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import native_fixture_selection
    import native_rng
    from gameplay_support import Game as BaseGame

    spec = importlib.util.spec_from_file_location(
        "matrix_supervisor", Path(__file__).with_name("test_episode_platforms.py")
    )
    supervisor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(supervisor)
    cancel = supervisor.Cancellation()
    Game = supervisor.owned_game_type(BaseGame, cancel)
    env = dict(
        os.environ,
        NYARLATHACK_NATIVE_FIXTURE_MODE="source-build",
        NYARLATHACK_NATIVE_BUILD_RECEIPT=str(receipt),
        NYARLATHACK_NATIVE_EXPECTED_REVISION=args.revision,
    )
    selection = native_fixture_selection.prepare(root, env)
    env = dict(selection.environment)
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    save(out / "selection.json", selection.record())
    manifest = json.loads((receipt / "1-manifest.json").read_text())
    hashes = {n: digest(root / n) for n in manifest["objects"]}
    save(out / "object-hashes-before.json", hashes)
    source = Path(__file__).with_name("episode_fountain_matrix.c").resolve()
    files = [
        source,
        Path(__file__).with_name("native_observation_contract.py"),
        Path(__file__).resolve(),
        Path(__file__).with_name("test_episode_fountain_matrix_oracle.py"),
        Path(__file__).with_name("test_episode_platforms.py"),
        trusted / "native_rng.h",
        trusted / "native_rng.py",
        trusted / "replay_clock.c",
        trusted / "curio_save_layout.c",
    ]
    save(out / "external-hashes.json", {str(p): digest(p) for p in files})
    for p in files:
        shutil.copyfile(p, out / p.name)

    def run(command, label):
        command = list(map(str, command))
        save(out / (label + ".command.json"), command)
        p = subprocess.run(command, env=env, capture_output=True, timeout=45)
        (out / (label + ".stdout")).write_bytes(p.stdout)
        (out / (label + ".stderr")).write_bytes(p.stderr)
        assert p.returncode == 0, (
            label,
            p.returncode,
            p.stderr.decode(errors="replace"),
        )
        return p.stdout

    results = []
    try:
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
        objects = native_rng.controlled_rng_objects(objects, out)
        for original, switches in (
            (root / "src/o_init.o", ["--globalize-symbol=disco"]),
            (root / "sys/unix/unixmain.o", ["--redefine-sym=main=original_game_main"]),
        ):
            target = out / original.name
            run(["objcopy", *switches, original, target], "copy-" + original.stem)
            objects = [target if p == original else p for p in objects]
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
        shutil.copyfile(trusted / "curio_save_layout.c", out / "curio_save_layout.c")
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
        run(
            [
                selection.compiler,
                *flags,
                "-c",
                out / source.name,
                "-o",
                out / "fixture.o",
            ],
            "compile",
        )
        libs = run(["pkg-config", "--libs", "lua5.4"], "libs").decode().split()
        exe = out / "episode-fountain-matrix"
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
            "link",
        )
        clock = out / "clock.so"
        run(
            [
                selection.compiler,
                "-shared",
                "-fPIC",
                out / "replay_clock.c",
                "-ldl",
                "-o",
                clock,
            ],
            "clock",
        )
        save(out / "executable-hashes.json", {str(p): digest(p) for p in (exe, clock)})
        calibration = json.loads(run([exe, "--calibrate"], "calibration"))
        assert len(calibration) == 4096
        chosen = [next(r for r in calibration if r["fate"] == i) for i in range(1, 31)]
        validate_manifest(chosen)
        save(out / "chosen-manifest.json", chosen)  # frozen before any action
        chosen_hash = digest(out / "chosen-manifest.json")
        special_calibration = json.loads(
            run([exe, "--calibrate-specials"], "special-calibration")
        )
        assert len(special_calibration) == 4096
        special_chosen = []
        for case in SPECIAL_CASES:
            pick = next(
                r
                for r in special_calibration
                if r["fate"] == case["fate"]
                and (case["case"] != "depletion" or r["dry"] == 0)
            )
            special_chosen.append(dict(case, seed=pick["seed"]))
        save(out / "special-manifest.json", special_chosen)
        special_hash = digest(out / "special-manifest.json")
        negatives = []
        healthy = None
        healthy_history = None
        for row, injection in [(r, None) for r in chosen + special_chosen] + [
            (chosen[0], mode) for mode in ("native", "raw", "budget")
        ]:
            pair = []
            pair_histories = []
            for enabled in (True,) if injection else (False, True):
                work = out / (
                    "negative-" + injection
                    if injection
                    else (row["case"] + "-" + ("on" if enabled else "off"))
                    if "case" in row
                    else "fate-%02d-%s" % (row["fate"], "on" if enabled else "off")
                )
                g = Game(selection.tuple_dir, clock, root=work)
                selection.verify_copy(g.game)
                # Hardlink one private executable, not sixty retained binary copies.
                (g.game / "dnethack").unlink()
                os.link(exe, g.game / "dnethack")
                options = work / "options"
                options.write_text("OPTIONS=!splash_screen,!perm_invent\n")
                child = dict(
                    env,
                    HOME=str(work),
                    MAIL=str(work / "private-mail"),
                    TERM="xterm",
                    LINES="24",
                    COLUMNS="80",
                    NETHACKOPTIONS="@" + str(options),
                    LD_PRELOAD=str(clock),
                    NYARLATHACK_RUN_DIR=str(g.run),
                    NYARLATHACK_OBSERVATIONS=str(int(enabled)),
                    FOUNTAIN_SEED=str(row["seed"]),
                    FOUNTAIN_STATE=str(work / "state.json"),
                )
                child.pop("FOUNTAIN_INJECTION", None)
                child.pop("FOUNTAIN_CASE", None)
                if "case" in row:
                    child["FOUNTAIN_CASE"] = row["case"]
                if injection:
                    child["FOUNTAIN_INJECTION"] = injection
                proof = []
                try:
                    with (work / "stderr").open("wb") as err:
                        pid, fd = pty.fork()
                        if pid == 0:
                            try:
                                fcntl.ioctl(
                                    0,
                                    termios.TIOCSWINSZ,
                                    struct.pack("HHHH", 24, 80, 0, 0),
                                )
                                os.dup2(err.fileno(), 2)
                                os.chdir(g.game)
                                os.execve(
                                    str(g.game / "dnethack"),
                                    [str(g.game / "dnethack"), str(row["fate"])],
                                    child,
                                )
                            except BaseException:
                                os._exit(127)
                        g.pid, g.fd = pid, fd
                        text = g.read(5)
                        if row.get("no_mouth"):
                            assert b"You have no mouth to drink with!" in text, text
                            assert b"Drink from the fountain?" not in text
                            proof.append("no-mouth-before-prompt")
                        else:
                            assert b"Drink from the fountain?" in text, text
                            assert g._reader_pid == pid
                            proof.append("confirmation")
                            text = g.send(b"y")
                        deadline = time.monotonic() + 10
                        for _ in range(24):
                            assert time.monotonic() < deadline
                            if not g._input_ready():
                                break
                            assert any(
                                s in text for s in (b"--More--", b"(end)", b" of ")
                            ), text
                            proof.append("native-menu-or-more")
                            text = g.send(b" ")
                        else:
                            raise AssertionError("input cap")
                        g.cleanup()
                        assert g.exitcode == 0, (
                            g.exitcode,
                            (work / "stderr").read_text(),
                        )
                finally:
                    if g.pid is not None or g.fd is not None:
                        g.cleanup()
                    (work / "terminal.stdout").write_bytes(g.raw)
                    save(work / "inputs.json", g.inputs)
                    save(work / "prompt-proof.json", proof)
                state = json.loads((work / "state.json").read_text())
                domains = set(DOMAINS) | ({"vision"} if "case" in row else set())
                assert set(state["before"]) == domains == set(state["after"])
                raw_history = (g.run / "events.jsonl").read_bytes()
                # Injection is after journal terminal; compare to frozen healthy
                # contexts and exact bytes, not mutated native budget context.
                history_state = healthy["state"] if injection else state
                events = validate_history(
                    raw_history,
                    history_state["context_before"],
                    history_state["context_after"],
                    row["fate"],
                    enabled,
                    row.get("case"),
                    policy=CURRENT,
                )
                pair_histories.append(events)
                fate = row["fate"]
                witness_text = (
                    b"You have no mouth to drink with!"
                    if row.get("no_mouth")
                    else b"This makes you feel great!"
                    if row.get("restore")
                    else b"The cool draught refreshes you."
                    if fate < 10
                    else b"This tepid water is tasteless."
                    if fate <= 18
                    else {
                        19: b"self-knowledgeable",
                        20: b"gag and vomit",
                        21: b"water is contaminated",
                        22: b"snakes",
                        23: b"unleash",
                        24: b"water's no good",
                        25: b"stalking you",
                        26: b"sense the presence of monsters",
                        27: b"spot a gem",
                        28: b"attract",
                        29: b"bad breath",
                        30: b"Water gushes forth",
                    }[fate]
                )
                assert witness_text in g.raw
                if row.get("case") == "depletion":
                    assert b"fountain dries up!" in g.raw
                if fate == 19:
                    assert len(proof) > 1, "real enlightenment menu must be dismissed"
                pair.append(
                    dict(state=state, terminal=bytes(g.raw).hex(), inputs=g.inputs)
                )
                if injection:
                    assert raw_history == healthy_history
                    cause = validate_negative(healthy, pair[-1], injection)
                    negatives.append(
                        dict(
                            mode=injection,
                            native_exit=g.exitcode,
                            rejected=cause,
                            count=state["count"],
                            next=state["next"],
                            context_before=state["context_before"],
                            context_after=state["context_after"],
                        )
                    )
                    save(out / "negative-controls.json", negatives)
                    continue
                if row["fate"] == 1 and enabled and "case" not in row:
                    healthy = pair[-1]
                    healthy_history = raw_history
                results.append(
                    dict(
                        **row,
                        enabled=enabled,
                        count=state["count"],
                        next=state["next"],
                        witness=state["witness"],
                    )
                )
                save(out / "executed-rows.json", results)
            if injection:
                assert digest(out / "chosen-manifest.json") == chosen_hash
                continue
            validate_pair(*pair)
            assert wire.ordinary_projection(
                pair_histories[0], CURRENT
            ) == wire.ordinary_projection(pair_histories[1], CURRENT)
            assert digest(out / "chosen-manifest.json") == chosen_hash
            assert digest(out / "special-manifest.json") == special_hash
        assert len(results) == 60 + 2 * len(SPECIAL_CASES) and len(negatives) == 3
        save(
            out / "result.json",
            dict(
                normal_actions=len(results),
                special_cases=len(SPECIAL_CASES),
                ordinary_fates=30,
                preflight_candidates=4096,
                preflight_draws=4096,
                special_preflight_candidates=len(special_calibration),
                special_preflight_draws=sum(r["draws"] for r in special_calibration),
                measured_action_draws=sum(r["count"] for r in results),
                sentinel_draws=len(results),
                scope="action counts exclude native startup, RNG controls and one fate-verification draw per process",
                deferred=[
                    "fatal",
                    "decline-potion",
                ],
            ),
        )
    finally:
        after = {n: digest(root / n) for n in hashes}
        save(out / "object-hashes-after.json", after)
        assert after == hashes
        native_fixture_selection.prepare(
            root,
            dict(
                os.environ,
                NYARLATHACK_NATIVE_FIXTURE_MODE="source-build",
                NYARLATHACK_NATIVE_BUILD_RECEIPT=str(receipt),
                NYARLATHACK_NATIVE_EXPECTED_REVISION=args.revision,
            ),
        )


if __name__ == "__main__":
    main()
