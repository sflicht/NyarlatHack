"""One-terminal offline play supervisor (NGPL; see dat/license).

POSIX only. The supervisor and forked director share the *same* flock open
file description; neither probes/releases/reacquires it. The supervisor keeps
its copy until both children are reaped, even if the director stops early.
No model modules are imported and the game inherits the caller's terminal.
"""

import argparse
import fcntl
import json
import os
from pathlib import Path
import select
import signal
import stat
import subprocess
import sys
import tempfile
import time

from .director import (
    DEFAULT_BYTES,
    DEFAULT_EVENTS,
    EventReader,
    Mailbox,
    RandomBackend,
    ScheduleBackend,
    State,
    eligible,
    secure_open,
)
from .protocol import parse_request

SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
GRACE = 2.0


def add_parser(sub):
    p = sub.add_parser("play", help="launch the game and an offline director together")
    p.add_argument("--backend", choices=("pack", "random"), default="pack")
    p.add_argument(
        "--pack",
        choices=("ambient", "silence", "ward", "hunger"),
        help="pack backend only; default ambient",
    )
    p.add_argument(
        "--at", type=int, help="pack safe index; default 1 (not retimed on restore)"
    )
    p.add_argument("--id", type=int, help="pack request ID; default 1")
    p.add_argument(
        "--seed", type=int, help="random director seed; default 0, not the game RNG"
    )
    p.add_argument(
        "--ordinary-food",
        action="store_true",
        help="random only: enable hunger proposals",
    )
    paths = p.add_mutually_exclusive_group()
    paths.add_argument(
        "--run-dir", type=Path, help="create a NEW private directory; default mkdtemp"
    )
    paths.add_argument(
        "--reuse-run-dir",
        type=Path,
        help="existing owned private directory for restore",
    )
    curio = p.add_mutually_exclusive_group()
    curio.add_argument(
        "--curio-source",
        type=Path,
        help="offline saved mode-0600 source in private 0700 parent; install before fresh play, "
        "VERIFY ONLY on restore (no repair); installation is not native admission",
    )
    curio.add_argument(
        "--curio-bundle-root",
        type=Path,
        help="existing private saved-bundle root; requires --curio-candidate-id; "
        "install before fresh play, VERIFY ONLY on restore (no repair)",
    )
    p.add_argument(
        "--curio-candidate-id",
        help="exact 64 lowercase hex source identity; requires --curio-bundle-root",
    )
    p.add_argument(
        "--game-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "dnethackdir",
        help="game installation directory (binary and matching data)",
    )
    p.add_argument(
        "--game",
        type=Path,
        default=Path("dnethack"),
        help="executable inside game root",
    )
    p.add_argument(
        "--max-runtime",
        type=float,
        default=300,
        help="director seconds, default 300; game continues",
    )
    p.add_argument(
        "--poll", type=float, default=0.25, help="director poll seconds, default .25"
    )
    p.add_argument("--max-events", type=int, default=DEFAULT_EVENTS)
    p.add_argument("--max-bytes", type=int, default=DEFAULT_BYTES)
    p.add_argument("--max-submissions", type=int, default=12)
    p.add_argument(
        "--ordinary",
        action="store_true",
        help="start a human Bard with no wizard mode; sets NETHACKOPTIONS if unset",
    )
    p.add_argument(
        "--next-use",
        action="store_true",
        help="host-built next-use selection from a ready origin schedule; RandomHistoryBackend seed 0; no model call",
    )
    p.add_argument(
        "game_args",
        nargs=argparse.REMAINDER,
        help="put game arguments after --; forwarded literally",
    )


def _configuration(args):
    if (
        not 0 < args.max_runtime <= 86400
        or not 0.01 <= args.poll <= 60
        or min(args.max_events, args.max_bytes, args.max_submissions) < 1
    ):
        raise ValueError("invalid director limits")
    if args.backend == "pack":
        if args.seed is not None or args.ordinary_food:
            raise ValueError("random options require random backend")
        raw = (
            Path(__file__).parent / "packs" / ((args.pack or "ambient") + ".json")
        ).read_bytes()
        request = parse_request(raw)
        request.update(
            id=1 if args.id is None else args.id, at=1 if args.at is None else args.at
        )
        backend = ScheduleBackend([request])
    else:
        if any(x is not None for x in (args.pack, args.at, args.id)):
            raise ValueError("pack options require pack backend")
        backend = RandomBackend(
            0 if args.seed is None else args.seed, args.ordinary_food
        )
    root = args.game_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("game root must be a directory")
    game = (root / args.game).resolve(strict=True)
    if (
        not game.is_relative_to(root)
        or not game.is_file()
        or not os.access(game, os.X_OK)
    ):
        raise ValueError("game must be executable inside game root")
    if args.ordinary:
        from .ordinary_start import reject_wizard_args

        extra = args.game_args[1:] if args.game_args[:1] == ["--"] else args.game_args
        reject_wizard_args(extra)
    return backend, root, game


def _directory(args):
    if args.reuse_run_dir is not None:
        path = args.reuse_run_dir.absolute()
        s = path.lstat()  # Do not resolve away a final symlink before validating.
        if (
            not stat.S_ISDIR(s.st_mode)
            or s.st_uid != os.getuid()
            or stat.S_IMODE(s.st_mode) != 0o700
        ):
            raise ValueError("restore directory must be owned and mode 0700")
    elif args.run_dir is not None:
        path = args.run_dir.absolute()
        path.mkdir(mode=0o700)  # Never adopt an existing directory implicitly.
        path.chmod(0o700)
    else:
        path = Path(tempfile.mkdtemp(prefix="nyarlathack-"))
    return path.resolve(strict=True)


def _validate_startup_pending(backend, state, pending):
    """An existing mailbox is evidence, not permission to skip configuration."""
    if pending is not None and pending["at"] <= state.safe:
        raise ValueError("pending request has missed its safe index")
    if isinstance(backend, ScheduleBackend):
        expected = backend.next(state)
        if pending is not None and pending != expected:
            raise ValueError("pending request conflicts with selected pack")


def _observe(reader, state, box, backend):
    for event in reader.read():
        state.ingest(event)
    if reader.tail:
        raise ValueError("incomplete existing event history; reconcile before restore")
    if state.ended:
        raise ValueError("run already ended; select a fresh run directory")
    pending = box.pending(state)
    _validate_startup_pending(backend, state, pending)
    return pending


def _offline_loop(box, backend, reader, state, args, ready):
    """Use existing admission primitives; this loop owns no game state.

    Separate from director.run because that entry point acquires its own flock;
    reopening here would contend with our inherited lock. Keep the same bounded
    scheduling rules (including one choice per fresh safe index).
    """
    deadline = time.monotonic() + args.max_runtime
    submitted, last_choice = 0, None
    known_pending = None
    first = True
    next_use = None
    next_use_status = None
    if getattr(args, "next_use", False):
        from .next_use_schedule import NextUseScheduler

        next_use = NextUseScheduler(
            box.path, seed=0 if args.seed is None else args.seed
        )
    while time.monotonic() < deadline or first:
        for event in reader.read(allow_observations=getattr(args, "next_use", False)):
            if event.get("v") in (2, 4) and event.get("event") == "observation":
                continue
            state.ingest(event)
        if next_use is not None:
            status = next_use.poll(box)["status"]
            if status != next_use_status:
                print("chaos: next-use: " + status, file=sys.stderr, flush=True)
                next_use_status = status
        if first and reader.tail:
            raise ValueError("incomplete event history before game startup")
        if state.ended:
            return
        pending = box.pending(state, known=known_pending)
        if first:
            _validate_startup_pending(backend, state, pending)
        known_pending = dict(pending) if pending is not None else None
        done = False
        if not pending:
            request = None
            if isinstance(backend, ScheduleBackend):
                request = backend.next(state)
                done = request is None and not getattr(args, "next_use", False)
            elif (
                state.latest
                and last_choice != state.safe
                and eligible(state, backend.ordinary_food)
            ):
                last_choice = state.safe
                request = backend.choose(state, state.last_id + 1, state.safe + 1)
            if request:
                if submitted >= args.max_submissions:
                    done = True
                else:
                    box.submit(request, state)
                    known_pending = dict(request)
                    submitted += 1
        if first:
            os.write(ready, b"R")  # Ready means valid state + initial pack publication.
            os.close(ready)
            first = False
        if done:
            return
        time.sleep(min(args.poll, max(0, deadline - time.monotonic())))


def _fork_director(box, backend, reader, state, args, log):
    read_fd, write_fd = os.pipe()
    try:
        pid = os.fork()
    except BaseException:
        os.close(read_fd)
        os.close(write_fd)
        raise
    if pid:
        os.close(write_fd)
        return pid, read_fd
    # No terminal reads, writes or foreground-group signals in the director.
    try:
        os.close(read_fd)
        os.setsid()
        for sig in SIGNALS:
            signal.signal(sig, signal.SIG_DFL)
        null = os.open(os.devnull, os.O_RDONLY)
        os.dup2(null, 0)
        os.close(null)
        os.dup2(log, 1)
        os.dup2(log, 2)
        os.close(log)
        _offline_loop(box, backend, reader, state, args, write_fd)
        os._exit(0)
    except BaseException as exc:
        # No raw event contents or paths reach the terminal or log.
        os.write(
            2,
            ("chaos: offline director stopped (" + type(exc).__name__ + ")\n").encode(),
        )
        os._exit(2)


def _stop_director(pid):
    """Always reap; tolerate a director that already died, then bound shutdown."""
    if os.waitpid(pid, os.WNOHANG)[0]:
        return
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + GRACE
    while time.monotonic() < deadline:
        if os.waitpid(pid, os.WNOHANG)[0]:
            return
        time.sleep(0.02)
    os.kill(pid, signal.SIGKILL)
    os.waitpid(pid, 0)


def _curio_preflight(args):
    source = getattr(args, "curio_source", None)
    bundle_root = getattr(args, "curio_bundle_root", None)
    candidate_id = getattr(args, "curio_candidate_id", None)
    if source is None and bundle_root is None and candidate_id is None:
        return None
    from . import curio_store as store

    prepared = store._source(source, bundle_root, candidate_id)
    if args.reuse_run_dir is not None:
        # Mailbox normally creates a missing lock. Curio restore must not do so.
        # Validate the original path, before _directory resolves any symlinks.
        with store._directory(args.reuse_run_dir) as d:
            fd = store._open_file(d, ".director.lock")
            os.close(fd)
    return prepared


def _curio_install(directory, box, prepared, *, restore):
    from . import curio_store as store

    with store._directory(directory) as d:
        # Reassert the SAME open file description, never reopen/unlock/reacquire.
        # Anchored identity checks reject a replaced lock, not just a busy one.
        store._private(os.fstat(box.lock))
        store._same_entry(d, ".director.lock", os.fstat(box.lock))
        fcntl.flock(box.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        store._same_entry(d, ".director.lock", os.fstat(box.lock))
        store._install_locked(d, *prepared, "verify" if restore else "fresh")


def play(args):
    backend, root, executable = _configuration(args)
    curio = _curio_preflight(args)
    directory = _directory(args)
    print(
        "chaos: run directory " + json.dumps(str(directory)) + " (preserved on exit)",
        file=sys.stderr,
        flush=True,
    )
    game = None
    director = None
    ready = None
    received = None
    interrupted_at = None

    def forward(sig, _frame):
        nonlocal received, interrupted_at
        if received is None:
            received, interrupted_at = sig, time.monotonic()
        if game is not None and game.poll() is None:
            game.send_signal(sig)

    old_handlers = {sig: signal.signal(sig, forward) for sig in SIGNALS}
    try:
        with Mailbox(directory) as box:
            # Supervisor holds this exact lock until game AND director are reaped.
            reader = EventReader(
                directory / "events.jsonl", args.max_bytes, args.max_events
            )
            state = State()
            _observe(reader, state, box, backend)
            try:
                journal = secure_open(directory / "whispers.jsonl")
            except FileNotFoundError:
                pass
            else:
                os.close(journal)
            if curio is not None:
                _curio_install(
                    args.reuse_run_dir or args.run_dir or directory,
                    box,
                    curio,
                    restore=args.reuse_run_dir is not None,
                )
            log = secure_open(
                directory / "director.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND
            )
            try:
                director, ready = _fork_director(box, backend, reader, state, args, log)
            finally:
                os.close(log)
            try:
                deadline = time.monotonic() + 5
                while not received and time.monotonic() < deadline:
                    if select.select([ready], [], [], 0.05)[0]:
                        if os.read(ready, 1) != b"R":
                            raise ValueError("offline director startup failed")
                        break
                else:
                    if received:
                        return -received
                    raise ValueError("offline director startup timed out")
                os.close(ready)
                ready = None
                if received:
                    return -received
                game_args = args.game_args
                if game_args[:1] == ["--"]:
                    game_args = game_args[1:]
                env = dict(os.environ, NYARLATHACK_RUN_DIR=str(directory))
                if args.ordinary:
                    from .ordinary_start import OPTIONS, reject_wizard_args

                    reject_wizard_args(game_args)
                    env.setdefault("NETHACKOPTIONS", OPTIONS)
                if args.next_use:
                    env["NYARLATHACK_OBSERVATIONS"] = "1"
                    env["NYARLATHACK_NEXT_USE_ADMIT"] = "1"
                game = subprocess.Popen(
                    [str(executable), *game_args],
                    cwd=root,
                    env=env,
                )
                # A signal can arrive inside Popen before assignment to game.
                if received:
                    game.send_signal(received)
                while game.poll() is None:
                    if (
                        interrupted_at is not None
                        and time.monotonic() - interrupted_at >= GRACE
                    ):
                        game.kill()
                    try:
                        game.wait(timeout=0.05)
                    except subprocess.TimeoutExpired:
                        pass
                return -received if received else game.returncode
            finally:
                if ready is not None:
                    os.close(ready)
                if game is not None and game.poll() is None:
                    game.terminate()
                    try:
                        game.wait(timeout=GRACE)
                    except subprocess.TimeoutExpired:
                        game.kill()
                        game.wait()
                if director is not None:
                    _stop_director(director)
                print(
                    "chaos: director stopped; run data retained",
                    file=sys.stderr,
                    flush=True,
                )
    finally:
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
