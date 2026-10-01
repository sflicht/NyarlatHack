"""One-terminal offline play supervisor (NGPL; see dat/license).

POSIX only. The supervisor and forked director share the *same* flock open
file description; neither probes/releases/reacquires it. The supervisor keeps
its copy until both children are reaped, even if the director stops early.
No model modules are imported and the game inherits the caller's terminal.
"""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import shlex
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
    OrdinaryBackend,
    RandomBackend,
    ScheduleBackend,
    State,
    eligible,
    secure_open,
)
from .protocol import parse_request

SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
GRACE = 2.0
RUN_PREFIX = "nyarlathack-"
_SCAN_CAP = 4096
HAUNT_DEFAULT = Path(__file__).resolve().parent / "packs" / "footsteps.lua"


def add_parser(sub):
    p = sub.add_parser("play", help="launch the game and an offline director together")
    p.add_argument(
        "--backend",
        choices=("pack", "random"),
        help="default pack; a fresh --ordinary run defaults to the #1 M1 menu",
    )
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
    next_use = p.add_mutually_exclusive_group()
    next_use.add_argument(
        "--next-use",
        action="store_true",
        help="host-built next-use selection from a ready origin schedule; "
        "RandomHistoryBackend seed 0; no model call (on by default with --ordinary)",
    )
    next_use.add_argument(
        "--no-next-use",
        action="store_true",
        help="--ordinary: turn off the default next-use program (#198)",
    )
    haunt = p.add_mutually_exclusive_group()
    haunt.add_argument(
        "--haunt",
        nargs="?",
        const=HAUNT_DEFAULT,
        type=Path,
        metavar="PACK",
        help="echo hound: install a Lua haunting candidate (default "
        "chaos/packs/footsteps.lua; on by default with --ordinary) before "
        "fresh play, VERIFY ONLY on restore; the game's shadow trial still "
        "decides admission",
    )
    haunt.add_argument(
        "--no-haunt",
        action="store_true",
        help="--ordinary: turn off the default echo hound (#198)",
    )
    p.add_argument(
        "game_args",
        nargs=argparse.REMAINDER,
        help="put game arguments after --; forwarded literally",
    )


def _m1_default(args):
    """#1 M1: --ordinary with no explicit whisper option (--seed allowed)."""
    return (
        args.ordinary
        and args.backend is None
        and not args.ordinary_food
        and all(x is None for x in (args.pack, args.at, args.id))
    )


def _configuration(args):
    if (
        not 0 < args.max_runtime <= 86400
        or not 0.01 <= args.poll <= 60
        or min(args.max_events, args.max_bytes, args.max_submissions) < 1
    ):
        raise ValueError("invalid director limits")
    m1 = _m1_default(args)
    if args.backend in ("pack", None):
        if (args.seed is not None and not m1) or args.ordinary_food:
            raise ValueError("random options require random backend")
        raw = (
            Path(__file__).parent / "packs" / ((args.pack or "ambient") + ".json")
        ).read_bytes()
        request = parse_request(raw)
        request.update(
            id=1 if args.id is None else args.id, at=1 if args.at is None else args.at
        )
        # #1 M1: play() swaps in OrdinaryBackend when the fresh record (or a
        # restored v2 record) selects it; the pack is the pre-M1 fallback.
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
        path = Path(tempfile.mkdtemp(prefix=RUN_PREFIX))
    return path.resolve(strict=True)


def _ordinary_name(env, game_args):
    """The player name the game will use: -u wins, then NETHACKOPTIONS, $USER."""
    name = None
    for index, arg in enumerate(game_args):
        if arg == "-u" and index + 1 < len(game_args):
            name = game_args[index + 1]
        elif arg.startswith("-u") and len(arg) > 2:
            name = arg[2:]
    if name is None:
        options = env.get("NETHACKOPTIONS", "")
        if options.startswith("@"):
            return None  # Options file: do not guess its contents.
        for option in options.split(","):
            key, _, value = option.strip().partition(":")
            if key.strip().lower() == "name" and value.strip():
                name = value.strip()
    if name is None:
        name = env.get("USER") or env.get("LOGNAME")
    if not name:
        return None
    # Mirror plnamesuffix() and set_savefile_name()/regularize() on Unix.
    name = name[:31].split("-", 1)[0].replace(",", " ")
    for ch in "./ ":
        name = name.replace(ch, "_")
    return name or None


def _save_path(root, env, name):
    playground = env.get("NETHACKDIR") or env.get("HACKDIR")
    base = root / playground if playground else root
    return base / "save" / (str(os.getuid()) + name)


def _owning_run(save_mtime):
    """Best-effort, read-only search of the launcher's own mkdtemp directories.

    A candidate began with a new game, has not ended, passes the director's
    usual history checks and was last written no later than the save. Only a
    single most recent match is named; anything else is reported as unknown.
    """
    parent = Path(tempfile.gettempdir())
    found = []
    try:
        entries = os.scandir(parent)
    except OSError:
        return None
    with entries:
        for index, entry in enumerate(entries):
            if index >= _SCAN_CAP:
                break
            if not entry.name.startswith(RUN_PREFIX):
                continue
            try:
                s = entry.stat(follow_symlinks=False)
                if (
                    not stat.S_ISDIR(s.st_mode)
                    or s.st_uid != os.getuid()
                    or stat.S_IMODE(s.st_mode) != 0o700
                ):
                    continue
                path = Path(entry.path)
                events = path / "events.jsonl"
                mtime = events.lstat().st_mtime
                if mtime > save_mtime:
                    continue
                reader = EventReader(events, DEFAULT_BYTES, DEFAULT_EVENTS)
                state = State()
                first = None
                for event in reader.read(allow_observations=True):
                    if event.get("v") in (2, 4) and event.get("event") == "observation":
                        continue
                    if first is None:
                        first = event
                    state.ingest(event)
            except (OSError, ValueError):
                continue
            if (
                first is None
                or first.get("event") != "session"
                or first.get("detail") != "new"
                or reader.tail
                or state.ended
            ):
                continue
            found.append((mtime, path))
    if not found:
        return None
    found.sort()
    if len(found) > 1 and found[-1][0] == found[-2][0]:
        return None
    return found[-1][1]


def _refuse_ordinary_over_save(args, root):
    """Fresh --ordinary over an existing save would restore into a new run (#175).

    Read-only: never creates, moves or deletes a save or run directory.
    Returns an exit status to stop with, or None to continue.
    """
    if not args.ordinary or args.reuse_run_dir is not None:
        return None
    from .ordinary_start import OPTIONS

    env = dict(os.environ)
    env.setdefault("NETHACKOPTIONS", OPTIONS)
    game_args = args.game_args[1:] if args.game_args[:1] == ["--"] else args.game_args
    name = _ordinary_name(env, game_args)
    if name is None:
        return None
    save = _save_path(root, env, name)
    try:
        s = save.lstat()
    except FileNotFoundError:
        return None
    lines = [
        "chaos: refusing a fresh ordinary run: a saved game already exists at",
        "  " + json.dumps(str(save)),
        "chaos: a fresh run would restore it into a new run directory that never",
        "chaos: saw that game, and the director would stop.",
    ]
    owner = _owning_run(s.st_mtime) if stat.S_ISREG(s.st_mode) else None
    if owner is not None:
        command = ["python3", "-m", "chaos", "play", "--ordinary"]
        if args.next_use:
            command.append("--next-use")
        if getattr(args, "no_next_use", False):
            command.append("--no-next-use")
        haunt = getattr(args, "haunt", None)
        if haunt is not None:
            command.append("--haunt")
            if Path(haunt).resolve() != HAUNT_DEFAULT:
                command.append(str(haunt))
        if getattr(args, "no_haunt", False):
            command.append("--no-haunt")
        default_root = (
            Path(__file__).resolve().parent.parent / "dnethackdir"
        ).resolve()
        if root != default_root:
            command += ["--game-root", str(root)]
        command += ["--reuse-run-dir", str(owner)]
        lines += [
            "chaos: its run directory appears to be " + json.dumps(str(owner)),
            "chaos: resume it (add any other options you used) with:",
            "  " + shlex.join(command),
        ]
    else:
        lines += [
            "chaos: no single run directory for this save was found.",
        ]
    lines += [
        "chaos: to start fresh instead, move or remove the save file yourself, e.g.",
        "  mv " + shlex.quote(str(save)) + " " + shlex.quote(str(save) + ".bak"),
        "chaos: nothing was launched and no file was changed.",
    ]
    print("\n".join(lines), file=sys.stderr, flush=True)
    return 2


CHOICE = "ordinary-choice.json"
CHOICE_KEYS = {"v", "haunt", "haunt_pack", "haunt_sha256", "next_use"}
# #1 M1, record v2: "whispers" is {"backend": "m1", "seed": int} when the run
# uses OrdinaryBackend, or null when explicit whisper flags chose the backend.
CHOICE_KEYS_V2 = CHOICE_KEYS | {"whispers"}
CHOICE_KEYS_V3 = CHOICE_KEYS_V2 | {"m2"}


def _explicit(args):
    """Flags the player typed: True on, False off, None left to the default."""
    haunt = None
    if getattr(args, "haunt", None) is not None:
        haunt = True
    elif getattr(args, "no_haunt", False):
        haunt = False
    next_use = None
    if getattr(args, "next_use", False):
        next_use = True
    elif getattr(args, "no_next_use", False):
        next_use = False
    return haunt, next_use


def _read_choice(directory):
    """The fresh game's recorded choice, or None for a pre-#198 run directory."""
    try:
        fd = secure_open(Path(directory) / CHOICE)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as f:
        raw = f.read(4097)
    if len(raw) > 4096:
        raise ValueError("ordinary choice record too large")
    record = json.loads(raw)
    if (
        not isinstance(record, dict)
        or type(record.get("v")) is not int
        or record["v"] not in (1, 2, 3)
        or set(record)
        != {1: CHOICE_KEYS, 2: CHOICE_KEYS_V2, 3: CHOICE_KEYS_V3}[record["v"]]
        or not isinstance(record["haunt"], bool)
        or not isinstance(record["next_use"], bool)
    ):
        raise ValueError("invalid ordinary choice record")
    if record["v"] == 3:
        m2 = record["m2"]
        if (
            type(m2) is not dict
            or set(m2) != {"enabled", "cap"}
            or type(m2["enabled"]) is not bool
            or type(m2["cap"]) is not int
            or m2["cap"] != 3
            or (m2["enabled"] and not record["next_use"])
        ):
            raise ValueError("invalid ordinary M2 choice")
    whispers = record.get("whispers")
    if whispers is not None and (
        not isinstance(whispers, dict)
        or set(whispers) != {"backend", "seed"}
        or whispers["backend"] != "m1"
        or type(whispers["seed"]) is not int
        or not 0 <= whispers["seed"] < 2**63
    ):
        raise ValueError("invalid ordinary choice record")
    pack, digest = record["haunt_pack"], record["haunt_sha256"]
    if record["haunt"]:
        if not (isinstance(pack, str) and isinstance(digest, str)):
            raise ValueError("invalid ordinary choice record")
    elif pack is not None or digest is not None:
        raise ValueError("invalid ordinary choice record")
    return record


def _pack_digest(pack):
    from .haunt import read_source

    return hashlib.sha256(read_source(pack)).hexdigest()


def _resolve_choice(args, restore_dir):
    """#198: --ordinary turns the hound and next-use on by default.

    Sets args.haunt / args.next_use to the effective choice. A fresh ordinary
    run returns the record to write into its run directory; restore follows
    that record and never re-reads today's defaults. A run directory from
    before #198 has no record and keeps exactly its explicit flags.
    """
    haunt, next_use = _explicit(args)
    args.next_use_programs = 1
    if restore_dir is not None:
        record = _read_choice(restore_dir)
        args.m1_seed = None
        if record is None:
            args.next_use = next_use is True
            return None
        if (haunt is not None and haunt != record["haunt"]) or (
            next_use is not None and next_use != record["next_use"]
        ):
            raise ValueError("restore options conflict with the run's recorded choice")
        whispers = record.get("whispers")
        if whispers is not None and (
            not _m1_default(args)
            or (args.seed is not None and args.seed != whispers["seed"])
        ):
            raise ValueError("restore options conflict with the run's recorded choice")
        if whispers is None and args.seed is not None and args.backend is None:
            raise ValueError("restore options conflict with the run's recorded choice")
        args.m1_seed = None if whispers is None else whispers["seed"]
        if record["haunt"]:
            pack = args.haunt if args.haunt is not None else record["haunt_pack"]
            if _pack_digest(pack) != record["haunt_sha256"]:
                raise ValueError("haunt pack differs from the run's recorded pack")
            args.haunt = Path(pack)
        args.next_use = record["next_use"]
        if record.get("m2", {}).get("enabled"):
            args.next_use_programs = record["m2"]["cap"]
        return None
    args.m1_seed = None
    if not args.ordinary:
        args.next_use = next_use is True
        return None
    if haunt is None:
        args.haunt = HAUNT_DEFAULT
    args.next_use = next_use is not False
    args.m1_seed = (
        (0 if args.seed is None else args.seed) if _m1_default(args) else None
    )
    args.next_use_programs = 3 if args.next_use else 1
    record = {"v": 3, "haunt": args.haunt is not None, "next_use": args.next_use}
    record["m2"] = {"enabled": args.next_use, "cap": 3}
    record["whispers"] = (
        None if args.m1_seed is None else {"backend": "m1", "seed": args.m1_seed}
    )
    record["haunt_pack"] = record["haunt_sha256"] = None
    if args.haunt is not None:
        pack = Path(args.haunt).resolve()
        record["haunt_pack"] = str(pack)
        record["haunt_sha256"] = _pack_digest(pack)
    return record


def _write_choice(directory, record):
    """Exclusive, private and durable; never replaces an existing record."""
    fd = os.open(
        Path(directory) / CHOICE,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
    )
    with os.fdopen(fd, "wb") as f:
        f.write(json.dumps(record, sort_keys=True).encode() + b"\n")
        f.flush()
        os.fsync(f.fileno())


def _validate_startup_pending(backend, state, pending):
    """An existing mailbox is evidence, not permission to skip configuration."""
    if pending is not None and pending["at"] <= state.safe:
        raise ValueError("pending request has missed its safe index")
    if isinstance(backend, ScheduleBackend):
        expected = backend.next(state)
        if pending is not None and pending != expected:
            raise ValueError("pending request conflicts with selected pack")
    if isinstance(backend, OrdinaryBackend) and pending is not None:
        expected = backend.next(state)
        if expected is not None and pending != expected:
            raise ValueError("pending request conflicts with the recorded menu")


def _observe(reader, state, box, backend, *, next_use=False):
    for event in reader.read(allow_observations=next_use):
        # Match the opt-in live loop; observations are not legacy whisper state.
        if event.get("v") in (2, 4) and event.get("event") == "observation":
            continue
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
            box.path,
            seed=0 if args.seed is None else args.seed,
            programs=getattr(args, "next_use_programs", 1),
        )
    while time.monotonic() < deadline or first:
        for event in reader.read(allow_observations=getattr(args, "next_use", False)):
            if event.get("v") in (2, 4) and event.get("event") == "observation":
                continue
            state.ingest(event)
        if next_use is not None:
            result = next_use.poll(box)
            status = result["status"]
            key = (getattr(next_use, "ordinal", 1), status)
            if key != next_use_status:
                print("chaos: next-use: " + status, file=sys.stderr, flush=True)
                next_use_status = key
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
            elif isinstance(backend, OrdinaryBackend) and backend.next(state):
                request = backend.next(state)
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


def _haunt_preflight(args):
    """Read the pack before any directory exists; the game re-validates it."""
    source = getattr(args, "haunt", None)
    if source is None:
        return None
    from .haunt import read_source

    return read_source(source)


def _haunt_install(box, raw, *, restore):
    """The existing `chaos haunt` publication, under the supervisor's own lock.

    Fresh play publishes haunting.lua exactly once. Restore only verifies the
    installed bytes: no repair, and a run that never had a candidate fails
    closed before the game starts.
    """
    from . import haunt

    if restore:
        haunt.verify(box.path, raw)
    else:
        haunt.publish(box.path, raw)


def play(args):
    backend, root, executable = _configuration(args)
    refused = _refuse_ordinary_over_save(args, root)
    if refused is not None:
        return refused
    curio = _curio_preflight(args)
    restore_dir = _directory(args) if args.reuse_run_dir is not None else None
    choice = _resolve_choice(args, restore_dir)
    if args.m1_seed is not None:
        backend = OrdinaryBackend(args.m1_seed)
    haunt = _haunt_preflight(args)
    directory = restore_dir if restore_dir is not None else _directory(args)
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
            _observe(reader, state, box, backend, next_use=args.next_use)
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
            if choice is not None:
                _write_choice(directory, choice)
            if haunt is not None:
                _haunt_install(box, haunt, restore=args.reuse_run_dir is not None)
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
