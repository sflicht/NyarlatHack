#!/usr/bin/python3
"""Full-linked native TTY output, synthetic scope: not doapply acceptance.

Normal-render baseline reached missing-notice RED before this candidate.
Real More SPACE/ESC and append cases extend the three original regressions.
Early filters and controlled port identities extend regression coverage.
Actual unsupported ports, nesting, failures and CHAOS-off remain pending;
these synthetic scopes do not discharge action or whole-game acceptance.
"""

import argparse
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pty
import re
import resource
import select
import shutil
import signal
import struct
import subprocess
import sys
import termios
import tempfile
import time
import unittest


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "receipt", "revision", "artifacts"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        raise ValueError("revision must already be full lowercase 40hex")
    for name in ("root", "receipt", "artifacts"):
        value = getattr(args, name)
        path = Path(value)
        if not path.is_absolute() or str(path) != value or path.resolve() != path:
            raise ValueError("explicit canonical absolute path required: " + name)
    root, receipt, out = map(Path, (args.root, args.receipt, args.artifacts))
    if Path.cwd() != root:
        raise ValueError("launch from the selected trusted checkout root")
    if not out.is_relative_to(Path("/tmp")) or out.is_relative_to(root):
        raise ValueError("artifacts must be outside checkout, under /tmp")
    trusted = root / "tests/chaos"
    helper_names = (
        "gameplay_support",
        "native_fixture_selection",
        "native_rng",
        "native_build_calibration",
        "native_build_identity",
    )
    # Reject conflicting cached helpers; never discard them to repair provenance.
    for name in helper_names:
        cached = sys.modules.get(name)
        if cached is not None:
            origin = getattr(cached, "__file__", None)
            if origin is None or Path(origin).resolve().parent != trusted:
                raise ValueError("unexpected cached verifier path")
    # An external test script must not shadow the explicitly selected helpers.
    # Keep all post-import path and source/build receipt checks below intact.
    sys.path.insert(0, str(trusted))
    # No PYTHONPATH editing, source override, archived fallback, or model imports.
    import gameplay_support
    import native_fixture_selection
    import native_rng

    for module in (sys.modules[name] for name in helper_names):
        if module.__file__ is None or Path(module.__file__).resolve().parent != trusted:
            raise ValueError("unexpected imported verifier path")
    if gameplay_support.ROOT != root:
        raise ValueError("selected root is not actual gameplay_support.ROOT")
    selection_env = dict(os.environ)
    selection_env.update(
        NYARLATHACK_NATIVE_FIXTURE_MODE="source-build",
        NYARLATHACK_NATIVE_BUILD_RECEIPT=str(receipt),
        NYARLATHACK_NATIVE_EXPECTED_REVISION=args.revision,
    )
    selection = native_fixture_selection.prepare(root, selection_env)
    if selection.environment is None:
        raise ValueError("source-build selection must provide an isolated environment")
    # Guard has passed before any artifact publication/compiler/copy.
    os.umask(0o077)
    out.mkdir(mode=0o700, parents=False, exist_ok=False)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    env = dict(selection.environment)
    env.update(HOME=str(out), TMPDIR=str(out), MAIL=str(out / "private-mail"))
    (out / "private-mail").write_bytes(b"")
    (out / "options").write_text("# isolated native fixture options\n")
    env.update(
        NETHACKOPTIONS="@" + str(out / "options"),
        TERM="xterm",
        LINES="24",
        COLUMNS="80",
    )

    def save(name, value):
        (out / name).write_text(json.dumps(value, indent=2) + "\n")

    def run(command, name, timeout=60):
        save(name + ".command.json", list(map(str, command)))
        result = subprocess.run(
            list(map(str, command)),
            cwd=out,
            env=env,
            capture_output=True,
            timeout=timeout,
        )
        (out / (name + ".stdout")).write_bytes(result.stdout)
        (out / (name + ".stderr")).write_bytes(result.stderr)
        save(name + ".status.json", {"returncode": result.returncode})
        result.check_returncode()
        return result.stdout

    # Use the existing source-matched reporter and existing static calibrator.
    for name in native_fixture_selection.ORACLE_SOURCES:
        shutil.copyfile(root / name, out / Path(name).name)
    selection.verify_helper_copy(out)
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
        [selection.compiler, *flags, out / "curio_save_layout.c", "-o", out / "layout"],
        "layout-build",
    )
    schema = json.loads(run([out / "layout"], "layout", 10))
    selection.validate_schema(schema)  # Never adjust schema/pins to make it pass.
    save("selection.json", selection.record())

    objects = (
        sorted((root / "src").glob("*.o"))
        + [
            root / "sys/unix/unixres.o",
            root / "sys/unix/unixunix.o",
            root / "sys/unix/unixmain.o",
            root / "sys/share/ioctl.o",
            root / "sys/share/unixtty.o",
        ]
        + sorted((root / "win/tty").glob("*.o"))
        + sorted((root / "win/curses").glob("*.o"))
    )
    originals = {str(obj): digest(obj) for obj in objects}
    save("original-object-hashes.json", originals)
    run(
        [
            "/usr/bin/objcopy",
            "--redefine-sym",
            "main=original_game_main",
            root / "sys/unix/unixmain.o",
            out / "unixmain.o",
        ],
        "rename-main",
        15,
    )
    objects = [
        out / "unixmain.o" if obj == root / "sys/unix/unixmain.o" else obj
        for obj in objects
    ]
    # Existing helper exposes native statics on a COPY, never replaces RNG code.
    # Its objcopy/nm calls have no internal timeout; a 20s alarm bounds this step.
    old_env = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)

    def alarm_handler(_signum, _frame):
        raise TimeoutError("controlled_rng_objects exceeded 20 seconds")

    old_alarm = signal.signal(signal.SIGALRM, alarm_handler)
    try:
        signal.alarm(20)
        objects = native_rng.controlled_rng_objects(objects, out)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_alarm)
        os.environ.clear()
        os.environ.update(old_env)
    source = Path(__file__).resolve().with_name("episode_delivery.c")
    shutil.copyfile(source, out / source.name)
    shutil.copyfile(trusted / "native_rng.h", out / "native_rng.h")
    save(
        "fixture-hashes.json",
        {
            p.name: digest(p)
            for p in (source, Path(__file__).resolve(), trusted / "native_rng.h")
        },
    )
    # Sequential compiler invocations (one job, never full make/rebuild).
    run(
        [
            selection.compiler,
            *flags,
            "-I" + str(out),
            "-c",
            out / source.name,
            "-o",
            out / "fixture.o",
        ],
        "fixture-compile",
        45,
    )
    libs = (
        run(["/usr/bin/pkg-config", "--libs", "lua5.4"], "lua-libs", 10)
        .decode()
        .split()
    )
    exe = out / "episode-delivery"
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
        75,
    )
    # Recheck exact root/receipt/revision plus original objects before executing.
    again = native_fixture_selection.prepare(root, selection_env)
    if again.record()["source_build"] != selection.record()["source_build"]:
        raise ValueError("source build changed during fixture link")
    if originals != {name: digest(Path(name)) for name in originals}:
        raise ValueError("native originals changed")
    save("linked-object-hashes.json", {str(obj): digest(obj) for obj in objects})
    save("executable.json", {"sha256": digest(exe)})
    old_cwd = Path.cwd()
    os.chdir(out)
    os.environ.clear()
    os.environ.update(env)
    try:
        native_rng.verify_native_fixture(unittest.TestCase(), exe, out)
    finally:
        os.chdir(old_cwd)
        os.environ.clear()
        os.environ.update(old_env)

    def render(enabled, scenario):
        work = out / (scenario + ("-on" if enabled else "-off"))
        work.mkdir(mode=0o700)
        run_dir = work / "run"
        run_dir.mkdir(mode=0o700)
        child_env = dict(
            env,
            NYARLATHACK_RUN_DIR=str(run_dir),
            NYARLATHACK_OBSERVATIONS=str(int(enabled)),
        )
        master, slave = pty.openpty()
        terminal = bytearray()
        inputs = []
        process = None
        key = (
            b" "
            if scenario == "pre-more-space"
            else b"\x1b"
            if scenario.endswith("-escape")
            else b""
        )
        expected_prompts = int(bool(key))
        command = [str(exe), "--" + scenario]
        (work / "command.json").write_text(json.dumps(command) + "\n")
        try:
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
            with (work / "stderr.txt").open("wb") as errors:
                process = subprocess.Popen(
                    command,
                    cwd=work,
                    env=child_env,
                    stdin=slave,
                    stdout=slave,
                    stderr=errors,
                    start_new_session=True,
                )
                os.close(slave)
                slave = None
                deadline = time.monotonic() + 20
                while True:
                    if time.monotonic() > deadline:
                        raise TimeoutError("native TTY scenario exceeded 20s; not RED")
                    if not select.select([master], [], [], 0.1)[0]:
                        continue
                    try:
                        data = os.read(master, 65536)
                    except OSError as exc:
                        if exc.errno != errno.EIO:
                            raise
                        break
                    if not data:
                        break
                    if len(terminal) + len(data) > 1024 * 1024:
                        raise RuntimeError("native terminal capture exceeds 1 MiB")
                    terminal.extend(data)
                    prompts = terminal.count(b"--More--")
                    if prompts > expected_prompts:
                        raise AssertionError(
                            "unexpected More prompt; no extra input sent"
                        )
                    if prompts == 1 and not inputs:
                        # Exactly one byte, only after the actual native prompt.
                        written = os.write(master, key)
                        inputs.append(
                            {
                                "hex": key[:written].hex(),
                                "bytes_written": written,
                                "prompt_count": prompts,
                                "prompt_offset": terminal.index(b"--More--"),
                                "terminal_bytes_before_write": len(terminal),
                            }
                        )
                        assert written == 1
                code = process.wait(timeout=3)
        except BaseException as exc:
            (work / "failure.txt").write_text(repr(exc) + "\n")
            raise
        finally:
            if process is not None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=3)
            if slave is not None:
                os.close(slave)
            os.close(master)
            (work / "terminal.bin").write_bytes(terminal)
            (work / "input.json").write_text(
                json.dumps(
                    {
                        "expected_key_hex": key.hex(),
                        "writes": inputs,
                        "prompt_count": terminal.count(b"--More--"),
                        "returncode": process.returncode if process else None,
                    },
                    indent=2,
                )
                + "\n"
            )
        if code:
            raise RuntimeError(f"native render exited {code}; inspect {work}; not RED")
        assert terminal.count(b"--More--") == len(inputs) == expected_prompts
        assert b"".join(bytes.fromhex(item["hex"]) for item in inputs) == key
        rows = [
            json.loads(line)
            for line in (run_dir / "events.jsonl").read_text().splitlines()
        ]
        state = json.loads((work / "stderr.txt").read_text())
        return bytes(terminal), rows, state, (work / "native-history.txt").read_bytes()

    results = []
    # Independent contract oracles, not derived from observed rendering/notices.
    # Target totals include the one unarmed priming message in repeat cases;
    # raw fallback is visible but never acknowledged as supported delivery.
    extra_cases = {
        "filter-noshow": dict(target=0, prime=0, followup=1, notices=0, forwarded=0),
        "filter-msgtype-norep": dict(
            target=1, prime=1, followup=1, notices=0, forwarded=0
        ),
        "filter-norep": dict(target=1, prime=1, followup=1, notices=0, forwarded=0),
        "early-empty": dict(target=0, prime=0, followup=1, notices=0, forwarded=0),
        "early-raw": dict(target=1, prime=0, followup=1, notices=0, forwarded=0),
        "port-native-renamed": dict(
            target=1, prime=0, followup=0, notices=1, forwarded=0
        ),
        "port-wrapper": dict(target=1, prime=0, followup=0, notices=0, forwarded=1),
        "port-wrapper-tty": dict(target=1, prime=0, followup=0, notices=0, forwarded=1),
    }
    for scenario in (
        "render",
        "stop-append",
        "stop-replacement",
        "append",
        "pre-more-space",
        "pre-more-escape",
        "post-newline-escape",
        "post-wrap-escape",
        *extra_cases,
    ):
        off_text, off_rows, off_state, off_history = render(False, scenario)
        on_text, on_rows, on_state, on_history = render(True, scenario)
        expected_notices = int(
            scenario
            not in (
                "stop-append",
                "stop-replacement",
                "pre-more-escape",
            )
        )
        expected_target = expected_notices
        if scenario in extra_cases:
            expected_notices = extra_cases[scenario]["notices"]
            expected_target = extra_cases[scenario]["target"]
        target = b"You produce a high whistling sound."
        assert off_text.count(target) == on_text.count(target) == expected_target, (
            scenario
        )
        followup = b"You listen."
        expected_followup = extra_cases.get(scenario, {}).get("followup", 0)
        assert off_text.count(followup) == on_text.count(followup) == expected_followup
        assert (
            on_state["forwarded_calls"]
            == off_state["forwarded_calls"]
            == (extra_cases.get(scenario, {}).get("forwarded", 0))
        )
        if scenario in extra_cases:
            case = extra_cases[scenario]
            if case["prime"]:
                # Selected repeat contributes no second target/history entry.
                assert on_text.index(target) < on_text.index(followup)
                assert on_history.startswith(
                    b"toplines:" + target + b"  " + followup + b"\n"
                )
            elif expected_followup:
                assert on_history.startswith(b"toplines:" + followup + b"\n")
            else:
                assert on_history.startswith(b"toplines:" + target + b"\n")
            if scenario == "early-raw":
                assert on_text.index(target) < on_text.index(followup)
        assert on_text == off_text, (
            "observation on/off terminal bytes differ: " + scenario
        )
        more = scenario.startswith("pre-more-") or scenario.startswith("post-")
        assert on_text.count(b"--More--") == int(more), scenario
        if scenario == "pre-more-space":
            assert on_text.index(b"--More--") < on_text.index(target)
        if scenario.startswith("pre-more-"):
            prime = b"You wait beside the quiet fountain and listen to the water."
            assert on_text.count(prime) == 1
            assert on_text.index(prime) < on_text.index(b"--More--")
        if scenario.startswith("post-"):
            # The exact first phrase is intentionally unwrapped in both cases.
            # Do not strip terminal controls or normalize whitespace to find it.
            assert on_text.index(target) < on_text.index(b"--More--")
            ending = (
                b"The echo fades."
                if scenario == "post-newline-escape"
                else b"and slowly fades into silence."
            )
            if scenario == "post-wrap-escape":
                # At 80 columns, the native word-wrap splits after 'corridor'.
                # Assert the actual line break/control sequence, not normalized text.
                assert (
                    b"empty corridor\x1b[K\x1b[K\r\nand slowly fades into silence."
                    in on_text
                )
            assert on_text.count(ending) == 1
            assert (
                on_text.index(target)
                < on_text.index(ending)
                < on_text.index(b"--More--")
            )
            assert on_history.split(b"maxrow:")[0].count(b"\n") == 2, scenario
        if scenario == "append":
            assert on_text.count(b"You wait.") == 1
            assert on_text.index(b"You wait.") < on_text.index(target)
            assert on_history.startswith(b"toplines:You wait.  " + target + b"\n")
        assert not [row for row in off_rows if "observation" in row]
        assert off_state.pop("root") == 0
        root_seq = on_state.pop("root")
        assert root_seq > 0 and on_state == off_state, scenario
        assert on_history == off_history, "native history differs: " + scenario
        obs = [row for row in on_rows if "observation" in row]
        notices = [row for row in obs if row["observation"]["stage"] == "notice"]
        save(
            scenario + "-observed.json",
            {
                "target_count": on_text.count(target),
                "followup_count": on_text.count(followup),
                "expected": extra_cases.get(scenario),
                "same_terminal_bytes": True,
                "same_selected_state_and_history": True,
                "root_seq": root_seq,
                "selected_notices": len(notices),
            },
        )
        assert len(notices) == expected_notices, (
            "MISSING OR SPURIOUS DELIVERY: " + scenario
        )
        stages = ["enabled", "started"] + ["notice"] * expected_notices + ["completed"]
        assert [row["observation"]["stage"] for row in obs] == stages, scenario
        start, end = obs[1], obs[-1]
        assert start["seq"] == root_seq
        assert start["observation"] == {
            "operation": "whistling",
            "stage": "started",
            "root_seq": 0,
            "fact": "none",
        }
        assert end["observation"] == {
            "operation": "whistling",
            "stage": "completed",
            "root_seq": root_seq,
            "fact": "none",
        }
        if expected_notices:
            notice = notices[0]
            assert notice["observation"] == {
                "operation": "whistling",
                "stage": "notice",
                "root_seq": root_seq,
                "fact": "sound_high",
            }
            assert start["seq"] < notice["seq"] < end["seq"]
            assert start["turn"] == notice["turn"] == end["turn"]
        results.append(
            {
                "scenario": scenario,
                "notices": len(notices),
                "prompt_count": on_text.count(b"--More--"),
                "passed": True,
            }
        )
    final_hashes = {name: digest(Path(name)) for name in originals}
    save("final-original-object-hashes.json", final_hashes)
    assert originals == final_hashes, "native originals changed during execution"
    save(
        "result.json",
        {
            "cases": results,
            "original_objects_unchanged": True,
            "scenario_count": len(results),
        },
    )
    print(json.dumps({"artifacts": str(out), "cases": results}), flush=True)


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class EpisodeDeliveryTests(unittest.TestCase):
    def test_full_linked_delivery(self):
        root = Path(__file__).resolve().parents[2]
        # No archived/default identity: the parent must supply a fresh source build.
        self.assertEqual(
            os.environ.get("NYARLATHACK_NATIVE_FIXTURE_MODE"), "source-build"
        )
        receipt = os.environ["NYARLATHACK_NATIVE_BUILD_RECEIPT"]
        revision = os.environ["NYARLATHACK_NATIVE_EXPECTED_REVISION"]
        container = Path(tempfile.mkdtemp(prefix="nyarl-episode-delivery-"))
        artifacts = container / "evidence"
        print("EPISODE_DELIVERY_ARTIFACTS=" + str(artifacts), flush=True)
        # Keep the driver's umask, signal, environment and resource changes private.
        env = {
            key: os.environ[key]
            for key in (
                "PATH",
                "LANG",
                "TZ",
                "PKG_CONFIG_LIBDIR",
                "PKG_CONFIG_PATH",
            )
            if key in os.environ
        }
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--root",
                str(root),
                "--receipt",
                receipt,
                "--revision",
                revision,
                "--artifacts",
                str(artifacts),
            ],
            cwd=root,
            env=env,
            capture_output=True,
            timeout=240,
        )
        (container / "driver.stdout").write_bytes(result.stdout)
        (container / "driver.stderr").write_bytes(result.stderr)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))


if __name__ == "__main__":
    main()
