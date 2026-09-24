#!/usr/bin/env python3
"""Opt-in passive full-game hunger demo. No seed search or action retries.

Native execution must be launched through native_driver_supervision.run_driver.
The oracle is importable without importing the concurrently developed director.
"""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import unittest

PREFIX = (("sanity", "80"), ("wait", "2")) + (
    ("wish", "fountain"),
    ("drink", "yes"),
) * 8
SUFFIX = (("sanity", "60"), ("wait", "24"), ("quit", "yes"))
WARNING = b"An unnatural hunger coils in your stomach."


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _integers(row, names):
    require(
        all(type(row.get(k)) is int for k in names.split()),
        "missing/noninteger witness field",
    )


def _phase(row, request, ack, expiry):
    _integers(row, "event_seq last_id spent reserved effect_value effect_expires safe")
    require(row["event_seq"] >= 0 and row["safe"] >= 0, "negative native counter")
    state = tuple(
        row[k]
        for k in ("last_id", "spent", "reserved", "effect_value", "effect_expires")
    )
    if request is None:
        require(state == (0, 0, 0, 0, 0), "nonempty control state")
        return "before"
    if row["event_seq"] < ack["seq"]:
        require(
            row["turn"] <= ack["turn"]
            and row["safe"] <= ack["safe"]
            and state == (0, 0, 0, 0, 0),
            "pre-admission state",
        )
        return "before"
    require(row["turn"] >= ack["turn"] and row["safe"] >= ack["safe"], "ACK ordering")
    if row["event_seq"] < expiry["seq"]:
        require(
            row["turn"] <= expiry["turn"]
            and state == (request["id"], 3, 3, 2, ack["expires"]),
            "active native state",
        )
    else:
        require(
            row["turn"] >= expiry["turn"] and state == (request["id"], 3, 0, 0, 0),
            "expiry/refund native state",
        )
    return "during" if row["turn"] < ack["expires"] else "after"


def _extra(row, capacities):
    """Independent eat.c:4078-4148 arithmetic, never a nutrition residual."""
    flags = (
        "artifact gluttony clear_thoughts regen_hurt hunger ahazu conflict "
        "fast_ring left_ring right_ring amulet yendor"
    )
    _integers(row, flags + " regen_mask insanity nightmare_sanity capacity_count")
    require(all(row[k] in (0, 1) for k in flags.split()), "nonboolean source flag")
    require(
        0 <= row["insanity"] <= 100
        and 0 <= row["nightmare_sanity"] <= 100
        and row["regen_mask"] >= 0,
        "unsupported source range",
    )
    require(row["capacity_count"] == len(capacities), "capacity count mismatch")
    turn = row["turn"]
    extra = 9 * row["artifact"] * bool(row["count"])
    if row["gluttony"] and not row["clear_thoughts"] and row["nightmare_sanity"] < 100:
        delta, remainder = divmod(row["insanity"], 25)
        extra += delta + (turn * remainder // 25 > (turn - 1) * remainder // 25)
    if turn % 2:
        require(capacities, "missing native odd capacity call")
        extra += bool(row["regen_hurt"] or row["regen_mask"])
        extra += capacities[0]["result"] > 1  # SLT_ENCUMBER, hack.h:33
    else:
        extra += row["hunger"] + row["conflict"] + row["fast_ring"]
        extra += bool(row["ahazu"] and turn % 10 == 1)  # native unreachable condition
        extra += {
            4: row["left_ring"],
            8: row["amulet"],
            12: row["right_ring"],
            16: row["yendor"],
        }.get(turn % 20, 0)
    return extra


def check_control(rows):
    """Use the identical all-call/source oracle with no admitted request."""
    return check_hunger(rows, None, None, None)


def check_hunger(rows, request, ack, expiry):
    """Fail closed; only ordinary nonpolymorphed food metabolism is supported.

    real_calls is a wrapper consistency counter, not independent interception.
    Forward-once is source-checked; reconciliation also detects doubled loss.
    """
    if request is not None:
        _integers(request, "v id value telegraph duration at")
        require(
            request["v"] == 1
            and request["id"] > 0
            and request["at"] > 0
            and request["mutation"] == "hunger_rate"
            and request["value"] == 2
            and request["telegraph"] == 3
            and request["duration"] in (10, 20),
            "wrong selected request",
        )
        _integers(
            ack,
            "v id value telegraph duration at turn expires seq safe cost spent reserved last_id",
        )
        # Archived v1 evidence remains readable; it is not current replay proof.
        require(ack["v"] in (1, 3), "unsupported ordinary ACK policy")
        if ack["v"] == 3:
            _integers(ack, "cosmetic_cost")
            require(ack["cosmetic_cost"] == 0, "hunger cosmetic tariff")
            for event in (ack, expiry):
                cosmetic = event.get("cosmetic")
                require(isinstance(cosmetic, dict), "missing cosmetic snapshot")
                _integers(cosmetic, "seen last_turn")
                # This frozen hunger-only route has no cosmetic admissions.
                require(
                    cosmetic == {"seen": 0, "last_turn": 0},
                    "unexpected route cosmetic state",
                )
        projected = {k: ack.get(k) for k in request}
        projected["v"] = 1  # request grammar, not the event envelope version
        require(
            projected == request
            and ack.get("event") == "ack"
            and ack.get("phase") == "result"
            and ack.get("status") == "accepted"
            and ack.get("detail") == "ok"
            and ack["cost"] == ack["spent"] == ack["reserved"] == 3
            and ack["last_id"] == request["id"]
            and ack["safe"] == request["at"]
            and ack["seq"] > 0
            and ack["turn"] >= 0,
            "exact native ACK required",
        )
        require(
            ack["expires"] == ack["turn"] + request["duration"], "wrong expiry duration"
        )
        _integers(expiry, "v turn seq safe spent reserved last_id")
        require(
            expiry["v"] == ack["v"]
            and expiry.get("event") == "expiry"
            and expiry.get("phase") == "result"
            and expiry.get("detail") == "hunger_rate"
            and expiry["turn"] >= ack["expires"]
            and expiry["seq"] > ack["seq"]
            and expiry["safe"] >= ack["safe"]
            and expiry["spent"] == 3
            and expiry["reserved"] == 0
            and expiry["last_id"] == request["id"],
            "missing native expiry",
        )
    else:
        require(ack is None and expiry is None, "unexpected control admission")
    food_count = hungry_count = capacity_count = total_loss = extra_loss = 0
    pending, capacities = [], []
    phases = dict(before=0, during=0, after=0)
    last_turn = last_seq = last_safe = -1
    released = False
    for row in rows:
        _integers(row, "turn call real_calls")
        require(row["turn"] >= max(0, last_turn), "nonmonotonic witness")
        last_turn = row["turn"]
        kind = row.get("kind")
        if kind == "capacity":
            _integers(row, "scope result")
            capacity_count += 1
            require(
                row["call"] == row["real_calls"] == capacity_count
                and row["scope"] == hungry_count + 1
                and 0 <= row["result"] <= 5,
                "capacity scope/counter/result",
            )
            capacities.append(row)
            continue
        require(kind in ("food", "hungry"), "unknown witness record")
        _integers(row, "before after")
        phase = _phase(row, request, ack, expiry)
        require(
            row["event_seq"] >= last_seq and row["safe"] >= last_safe,
            "nonmonotonic native state",
        )
        last_seq, last_safe = row["event_seq"], row["safe"]
        released |= request is not None and row["event_seq"] >= expiry["seq"]
        if kind == "food":
            _integers(row, "scope input output")
            food_count += 1
            require(
                row["call"] == row["real_calls"] == food_count,
                "food forwarding counter",
            )
            require(row["scope"] == hungry_count + 1, "unscoped food call")
            require(row["before"] == row["after"], "adapter changed nutrition")
            require(0 < row["input"] <= 1073741823, "nonordinary food amount")
            require(
                row["output"] == row["input"] * (2 if phase == "during" else 1),
                "ordinary multiplier mismatch",
            )
            phases[phase] += 1
            pending.append(row)
        else:
            _integers(row, "ordinary end_turn count input_sum output_sum")
            hungry_count += 1
            require(
                row["call"] == row["real_calls"] == hungry_count,
                "gethungry forwarding counter",
            )
            require(
                row["ordinary"] == 1 and row["end_turn"] == row["turn"],
                "nonordinary metabolism or turn changed",
            )
            require(
                row["count"] == len(pending) and len(pending) <= 1,
                "ordinary native source count",
            )
            require(
                all(p["turn"] == row["turn"] for p in pending + capacities),
                "nested turn mismatch",
            )
            require(
                all(
                    all(
                        p[k] == row[k]
                        for k in (
                            "event_seq",
                            "last_id",
                            "spent",
                            "reserved",
                            "effect_value",
                            "effect_expires",
                            "safe",
                        )
                    )
                    for p in pending
                ),
                "scope admission state changed",
            )
            require(
                row["input_sum"] == sum(p["input"] for p in pending)
                and row["output_sum"] == sum(p["output"] for p in pending),
                "ordinary sums mismatch",
            )
            extra = _extra(row, capacities)
            loss = row["before"] - row["after"]
            require(loss == row["output_sum"] + extra, "unexplained nutrition loss")
            total_loss += loss
            extra_loss += extra
            pending.clear()
            capacities.clear()
    require(
        not pending and not capacities and hungry_count > 0, "unfinished/empty witness"
    )
    require(
        all(phases.values()) and released
        if request is not None
        else phases["before"] > 0,
        "missing positive baseline/during/expiry witness",
    )
    return dict(
        phases=phases,
        food_calls=food_count,
        hungry_calls=hungry_count,
        capacity_calls=capacity_count,
        total_loss=total_loss,
        additional_loss=extra_loss,
    )


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


# Frozen before the first arm; UI responses are NOT gameplay commands.
GAMEPLAY_BYTES = (
    (b"#setsanity\n", b"80\n", b".", b".")
    + (
        b"#wish\n",
        b"fountain\n",
        b"q",
        b"y",
    )
    * 8
    + (b"#setsanity\n", b"60\n")
    + (b".",) * 24
    + (b"#quit\n", b"y")
)
PROMPT_POLICY = {
    "more": "space only when the immediately preceding native read contains --More--",
    "startup": "n only at No past inheritance; no save/recovery prompts",
    "dry_up": "n only at native Dry up fountain? [yn], preserving the offered default",
    "finish": "n only at native [ynq] after the frozen quit confirmation",
    "comparison": "primary/replay raw exact; control prefix raw exact and gameplay bytes exact; all-call turn schedule exact",
    "terminal": [24, 80],
}


def disciplined_game_type(base):
    class DisciplinedGame(base):
        scripted = False
        command_index = 0
        last_text = b""

        def read(self, *args, **kwargs):
            text = super().read(*args, **kwargs)
            self.last_text = text
            require(
                not any(
                    marker in text.lower()
                    for marker in (
                        b"die?",
                        b"you die",
                        b"keep the save file",
                        b"delete the old file?",
                    )
                ),
                "death/recovery prompt: no retry",
            )
            return text

        def send(self, value, **kwargs):
            value = value.encode() if isinstance(value, str) else value
            require(len(self.inputs) < 240, "input count cap")
            require(
                sum(len(bytes.fromhex(x)) for x in self.inputs) < 8192, "input byte cap"
            )
            if not hasattr(self, "prompt_inputs"):
                self.prompt_inputs = []
                self.command_inputs = []
            if value == b" ":
                require(b"--More--" in self.last_text, "unjustified More response")
                self.prompt_inputs.append(
                    dict(
                        index=len(self.inputs),
                        kind="more",
                        evidence=self.last_text.hex(),
                    )
                )
            elif value == b"n" and b"Dry up fountain? [yn]" in self.last_text:
                self.prompt_inputs.append(
                    dict(
                        index=len(self.inputs),
                        kind="dry_up_decline",
                        evidence=self.last_text.hex(),
                    )
                )
            elif not self.scripted:
                require(
                    value == b"n" and b"No past inheritance" in self.last_text,
                    "unexpected startup input",
                )
                self.prompt_inputs.append(
                    dict(
                        index=len(self.inputs),
                        kind="inheritance",
                        evidence=self.last_text.hex(),
                    )
                )
            elif self.command_index == len(GAMEPLAY_BYTES):
                require(
                    value == b"n" and b"[ynq]" in self.last_text,
                    "unexpected post-quit input",
                )
                self.prompt_inputs.append(
                    dict(
                        index=len(self.inputs),
                        kind="disclosure",
                        evidence=self.last_text.hex(),
                    )
                )
            else:
                require(
                    b"--More--" not in self.last_text, "unhandled native More prompt"
                )
                require(
                    value == GAMEPLAY_BYTES[self.command_index],
                    "frozen gameplay byte mismatch",
                )
                self.command_index += 1
                self.command_inputs.append(value.hex())
            return super().send(value, **kwargs)

    return DisciplinedGame


@contextmanager
def arm_session(game, env, verify):
    """Own startup too; preserve the triggering error while attempting all cleanup."""
    fd = None
    previous = dict(os.environ)
    try:
        telemetry = game.root / "hunger.jsonl"
        fd = os.open(
            telemetry, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL, 0o600
        )
        try:
            os.set_inheritable(fd, True)
            os.environ.clear()
            os.environ.update(env, NYARLATHACK_HUNGER_FD=str(fd))
            game.start()
        finally:
            os.environ.clear()
            os.environ.update(previous)
            if fd is not None:
                os.close(fd)
                fd = None
        yield telemetry
    finally:
        original = sys.exc_info()[1]
        errors = []
        for operation in (game.save_artifacts, game.cleanup, verify):
            try:
                operation()
            except BaseException as exc:
                errors.append(exc)
        if original is not None:
            for exc in errors:
                original.add_note("cleanup/protected verification: " + repr(exc))
        elif errors:
            raise errors[0]


def finish_arm(game, telemetry, request):
    # No native input or append may follow the final oracle read.
    require(game.quit() == 0, "native exit failed")
    events = game.events()
    rows = [json.loads(line) for line in telemetry.read_text().splitlines()]
    if request is None:
        require(
            not any(e.get("event") in ("ack", "expiry", "telegraph") for e in events),
            "control admission",
        )
        require(WARNING not in game.raw, "control warning")
        return check_control(rows)
    acks = [e for e in events if e.get("event") == "ack"]
    expiry = [
        e
        for e in events
        if e.get("event") == "expiry" and e.get("detail") == "hunger_rate"
    ]
    require(len(acks) == len(expiry) == 1, "unique ACK and expiry required")
    require(WARNING in game.raw, "native warning missing")
    telegraphs = [e for e in events if e.get("event") == "telegraph"]
    require(len(telegraphs) == 1, "unique native telegraph required")
    signal = telegraphs[0]
    require(
        signal.get("detail") == "hunger_rate"
        and signal.get("phase") == "result"
        and signal["seq"] < acks[0]["seq"] < expiry[0]["seq"]
        and signal["turn"] == acks[0]["turn"]
        and signal["safe"] == acks[0]["safe"]
        and signal["spent"] == signal["reserved"] == 0
        and signal["last_id"] == request["id"],
        "telegraph/admission ordering",
    )
    return check_hunger(rows, request, acks[0], expiry[0])


def preparation(game):
    # Module import deliberately avoids aliasing another unittest.TestCase.
    import test_episode_turnloop as turnloop

    for operation, argument in PREFIX:
        if operation == "sanity":
            game.sanity(int(argument))
        elif operation == "wait":
            game.wait_turns(int(argument))
        elif operation == "wish":
            turnloop.wish(game, argument)
        else:
            text = game.send("q")
            require(
                b"Drink from the fountain?" in text, "missing native fountain prompt"
            )
            text = game.more(game.send("y"))
            if b"Dry up fountain? [yn]" in text:
                game.more(game.send("n"))
        require(
            not any(e.get("event") == "death" for e in game.events()), "death: no retry"
        )
    starts = [
        e
        for e in game.events()
        if e.get("v") == 4
        and e["observation"]["stage"] == "started"
        and e["observation"]["operation"] == "fountain_drink"
    ]
    require(len(starts) == 8, "retain exactly eight natural confirmed drinks")


class RecordedHistoryBackend:
    """Test-only replay of an externally retained response; no provider calls.

    Checks local evidence consistency, not signatures or hostile-user authenticity.
    The caller also binds the complete native source prefix before publication.
    """

    def __init__(self, record):
        import copy
        from chaos.history_choice import _BoundedChoice

        self.record = copy.deepcopy(record)
        self.bound = _BoundedChoice()
        self.attempts = 0
        self.deadline = float("inf")
        self.last_receipt = self.last_response = None

    def choose(self, context, menu):
        import copy
        from chaos.protocol import parse_request
        from chaos.response import normalize_whisper_response

        self.bound.attempts = self.attempts
        self.bound.deadline = self.deadline
        prepared = self.bound._prepare(context, menu)
        if prepared is None:
            return None
        self.attempts += 1
        frozen, prompt = prepared
        record = self.record
        digest = hashlib.sha256(
            (self.bound.instructions + "\0" + prompt).encode()
        ).hexdigest()
        require(
            record.get("status") == "selected"
            and record.get("context") == context
            and record.get("candidates") == frozen
            and record.get("prompt_sha256") == digest,
            "recorded choice context/menu/prompt mismatch",
        )
        receipt = record.get("receipt", {})
        require(
            receipt.get("model") == "gpt-5.6-luna"
            and receipt.get("provider") == "openai-codex"
            and receipt.get("record", {}).get("status") == "completed"
            and receipt["record"].get("prompt_sha256") == digest,
            "recorded choice receipt mismatch",
        )
        selected = parse_request(
            normalize_whisper_response(record.get("raw_response"), cap=8192)
        )
        require(
            selected == record.get("selected") and selected in frozen,
            "recorded response is not exact selected menu member",
        )
        self.last_response = record["raw_response"]
        self.last_receipt = copy.deepcopy(receipt)
        return selected


def native(args):
    """One build, one primary, one empty control, one original schedule replay."""
    from gameplay_support import Game
    import test_episode_platforms as platform
    from chaos.history import snapshot_history, candidate_requests
    from chaos.history_choice import RandomHistoryBackend
    from chaos.history_director import run_history, load_history_replay
    from chaos.director import ScheduleBackend

    root, receipt, out = map(Path, (args.root, args.receipt, args.output))
    for path in (root, receipt, out):
        require(
            path.is_absolute() and path.resolve() == path,
            "canonical absolute paths required",
        )
    require(
        re.fullmatch(r"[0-9a-f]{40}", args.revision), "literal full revision required"
    )
    require(
        not out.is_relative_to(root) and not out.exists(),
        "fresh external output required",
    )
    require(out.parent.stat().st_mode & 0o077 == 0, "private output parent required")
    os.umask(0o077)
    out.mkdir(mode=0o700)
    manifest = json.loads(receipt.read_text())
    require(
        manifest["mode"] == 1 and manifest["revision"] == args.revision,
        "compiled base identity mismatch",
    )
    require(
        len(manifest["objects"]) == 163
        and "sys/unix/unixmain.o" in manifest["objects"]
        and "src/chaos_next_use_journal.o" in manifest["objects"]
        and "src/chaos_presentation.o" in manifest["objects"],
        "complete original production object receipt required",
    )
    require(
        len(manifest["generated_headers"]) == 130
        and "include/date.h" in manifest["generated_headers"]
        and "include/chaos_next_use_schedule.h" in manifest["generated_headers"]
        and "include/chaos_next_use_journal.h" in manifest["generated_headers"]
        and "include/chaos_presentation.h" in manifest["generated_headers"],
        "complete frozen header receipt required",
    )
    protected = dict(manifest["generated_headers"], **manifest["objects"])

    def verify():
        for name, expected in protected.items():
            p = root / name
            require(
                p.resolve().is_relative_to(root)
                and not p.is_symlink()
                and digest(p) == expected,
                "changed production input: " + name,
            )

    verify()
    for name, expected in manifest["pairs"].items():
        require(
            digest(root / "dnethackdir" / name) == expected["sha256"],
            "base tuple mismatch",
        )
    here = Path(__file__).resolve().parent
    sources = [
        here / "history_hunger.c",
        here / "test_history_gameplay.py",
        here / "test_history_gameplay_oracle.py",
        here / "replay_clock.c",
        here / "gameplay_support.py",
        here / "test_episode_turnloop.py",
        here / "test_episode_platforms.py",
        here / "native_driver_supervision.py",
    ]
    sources += sorted((here.parents[1] / "chaos").rglob("*.py"))
    sources += [here.parents[1] / "chaos/prompts/history-director.txt"]
    recorded = None
    choice_path = getattr(args, "choice_evidence", None)
    if choice_path is not None:
        from chaos.protocol import strict_json

        path = Path(choice_path)
        require(
            path.is_absolute() and path.resolve() == path and not path.is_symlink(),
            "canonical recorded-choice path required",
        )
        require(path.stat().st_size <= 32768, "recorded choice exceeds cap")
        recorded = strict_json(path.read_text(), 32768)
        sources.append(path)
    hashes = {str(p): digest(p) for p in sources}
    env = dict(
        PATH="/usr/bin:/bin",
        HOME=str(out),
        TMPDIR=str(out),
        LC_ALL="C",
        PYTHONDONTWRITEBYTECODE="1",
        NYARLATHACK_OBSERVATIONS="1",
    )
    cancel = platform.Cancellation()

    def command(argv, label):
        return platform.bounded(argv, out, env, out / label, cancel=cancel)

    # Sequential: never more than one compiler job. No production object writes.
    # Receipt covers generators too; GAME_O excludes util/* and win/share/*.
    # GNUmakefile:97-100 uses only these five object directories.
    game_objects = [
        p
        for p in manifest["objects"]
        if Path(p).parent.as_posix()
        in ("src", "sys/unix", "sys/share", "win/tty", "win/curses")
    ]
    require("sys/unix/unixmain.o" in game_objects, "original native main required")
    link = [
        "/usr/bin/cc",
        "-g",
        "-DCHAOS",
        "-isystem" + str(root / "include"),
        str(here / "history_hunger.c"),
        *[str(root / p) for p in game_objects],
        "-Wl,--wrap=gethungry",
        "-Wl,--wrap=chaos_food",
        "-Wl,--wrap=near_capacity",
        "-lncursesw",
        "-ltinfo",
        "-lm",
        "-llua5.4",
        "-o",
        str(out / "dnethack"),
    ]
    clock = [
        "/usr/bin/cc",
        "-shared",
        "-fPIC",
        str(here / "replay_clock.c"),
        "-ldl",
        "-o",
        str(out / "clock.so"),
    ]
    recipe = dict(
        base_revision=args.revision,
        base_receipt_sha256=digest(receipt),
        fixture_sources=hashes,
        prefix=PREFIX,
        suffix=SUFFIX,
        gameplay_bytes=[v.hex() for v in GAMEPLAY_BYTES],
        prompt_policy=PROMPT_POLICY,
        link=link,
        clock=clock,
        selector_seed=0 if recorded is None else None,
        selection_kind="seeded-offline"
        if recorded is None
        else "recorded-model-response",
        choice_evidence_sha256=digest(Path(choice_path)) if choice_path else None,
        caveat="compiled base and current Python fixture have separate identities",
    )
    save(out / "recipe.json", recipe)
    recipe_hash = digest(out / "recipe.json")
    save(out / "recipe-sha256.json", recipe_hash)
    command(["/usr/bin/cc", "--version"], "compiler-version")
    command(link, "link")
    command(clock, "clock-build")
    for name in ("nhdat", "license"):
        shutil.copy2(root / "dnethackdir" / name, out / name)
    BoundedGame = disciplined_game_type(platform.owned_game_type(Game, cancel))
    completed = []
    request = None

    def verify_all():
        verify()
        require(
            {str(p): digest(p) for p in sources} == hashes, "fixture source changed"
        )
        require(digest(out / "recipe.json") == recipe_hash, "frozen recipe changed")
        for name, expected in manifest["pairs"].items():
            require(
                digest(root / "dnethackdir" / name) == expected["sha256"],
                "base tuple changed",
            )

    for arm in ("primary", "control", "replay"):
        verify_all()
        game = BoundedGame(out, out / "clock.so", root=out / arm, wizard=True)
        with arm_session(game, env, verify_all) as telemetry:
            game.scripted = True
            preparation(game)
            state, checkpoint = snapshot_history(game.run)
            require(
                candidate_requests(state, True),
                "no qualifying history after all eight: stop",
            )
            game.prefix_inputs = list(game.inputs)
            game.prefix_events = (game.run / "events.jsonl").read_bytes()
            save(game.root / "prefix-checkpoint.json", checkpoint)
            require(
                state.latest["spent"] == state.latest["reserved"] == state.last_id == 0,
                "nonempty preparation admission state",
            )
            if arm != "primary":
                require(
                    game.prefix_inputs == completed[0].prefix_inputs
                    and game.prefix_events == completed[0].prefix_events,
                    "prefix divergence",
                )
            if arm != "control":
                if recorded is not None:
                    require(
                        checkpoint["event"]["sha256"]
                        == recorded["source_prefix_sha256"],
                        "recorded model source prefix differs",
                    )
                backend = (
                    (
                        RandomHistoryBackend(0)
                        if recorded is None
                        else RecordedHistoryBackend(recorded)
                    )
                    if arm == "primary"
                    else ScheduleBackend(
                        load_history_replay(
                            out / "primary/run/whispers.jsonl",
                            out / "primary/run/events.jsonl",
                        )
                    )
                )
                result = run_history(
                    game.run,
                    backend,
                    ordinary_food=True,
                    max_runtime=2,
                    install_only=True,
                )
                save(game.root / "decision.json", result)
                require(
                    result["reason"] == "installed_pending_ack"
                    and result["submitted"] == 1
                    and result["accepted"] == 0
                    and result["rejected"] == 0,
                    "publication failed",
                )
                if arm == "primary":
                    require(backend.attempts == 1, "selector must choose exactly once")
                selected = result["decision"]["selected"]
                require(selected["at"] == state.safe + 1, "wrong next safe point")
                if arm == "primary":
                    request = selected
                else:
                    require(selected == request, "replay changed original schedule")
            game.sanity(60)
            game.wait_turns(24)
            require(
                not any(e.get("event") == "death" for e in game.events()),
                "death: no retry",
            )
            if arm != "control":
                state, _ = snapshot_history(game.run)
                require(
                    state.latest["spent"] == 3
                    and state.latest["reserved"] == 0
                    and state.last_id == request["id"],
                    "expiry must retain lifetime spending",
                )
                require(
                    any(
                        e.get("event") == "expiry" and e.get("detail") == "hunger_rate"
                        for e in game.events()
                    ),
                    "native expiry before quiet check required",
                )
                require(
                    not candidate_requests(state, True),
                    "accepted hunger must suppress repeat",
                )
                paths = [
                    game.run / n
                    for n in ("whisper.json", "whispers.jsonl", "events.jsonl")
                ]
                before = [p.read_bytes() if p.exists() else None for p in paths]
                quiet_backend = RandomHistoryBackend(0)
                quiet = run_history(
                    game.run,
                    quiet_backend,
                    ordinary_food=True,
                    max_runtime=0.05,
                    poll=0.01,
                )
                require(
                    quiet_backend.attempts == 0
                    and quiet["submitted"]
                    == quiet["accepted"]
                    == quiet["rejected"]
                    == 0
                    and quiet["decision"] is None,
                    "repeat runner not quiet",
                )
                require(
                    before == [p.read_bytes() if p.exists() else None for p in paths],
                    "repeat runner changed mailbox/journal/events",
                )
                after, _ = snapshot_history(game.run)
                require(
                    after.latest["spent"] == state.latest["spent"],
                    "repeat spending changed",
                )
                save(game.root / "repeat-quiet.json", quiet)
            summary = finish_arm(game, telemetry, None if arm == "control" else request)
            save(game.root / "hunger-check.json", summary)
            require(
                game.command_index == len(GAMEPLAY_BYTES), "unfinished frozen commands"
            )
            save(game.root / "prompt-inputs.json", game.prompt_inputs)
            save(game.root / "gameplay-inputs.json", game.command_inputs)
            game.save_artifacts()
        completed.append(game)
    first, control, replay = completed
    require(first.inputs == replay.inputs, "raw replay input divergence")
    require(
        first.command_inputs == control.command_inputs == replay.command_inputs,
        "gameplay input divergence",
    )

    def call_schedule(game):
        rows = [
            json.loads(line)
            for line in (game.root / "hunger.jsonl").read_text().splitlines()
        ]
        return [(r["kind"], r["turn"], r["call"], r.get("scope")) for r in rows]

    require(
        call_schedule(first) == call_schedule(control),
        "control turn/call schedule divergence",
    )
    for relative in (
        "terminal.raw",
        "inputs.json",
        "hunger.jsonl",
        "run/events.jsonl",
        "game/xlogfile",
    ):
        require(
            (first.root / relative).read_bytes()
            == (replay.root / relative).read_bytes(),
            "exact replay mismatch: " + relative,
        )

    def dumps(g):
        return {
            p.name: p.read_bytes()
            for p in (g.game / "dumplog").iterdir()
            if p.is_file()
        }

    require(dumps(first) == dumps(replay), "same-build strict dump mismatch")
    verify()
    require(
        {str(p): digest(p) for p in sources} == hashes, "fixture changed during arms"
    )
    verify_all()
    arm_hashes = {
        g.root.name: {
            str(p.relative_to(g.root)): digest(p)
            for p in sorted(g.root.rglob("*"))
            if p.is_file()
        }
        for g in completed
    }
    origins = [
        e
        for e in first.events()
        if e.get("v") == 4 and e.get("observation", {}).get("fact") == "water_refreshed"
    ]
    save(
        out / "result.json",
        dict(
            native_passed=True,
            arms=arm_hashes,
            selected=request,
            base_revision=args.revision,
            base_receipt_sha256=digest(receipt),
            fixture_sources=hashes,
            qualifying_origins=origins,
            effect_measurement="complete native trace including quit",
            control="full baseline oracle and exact turn/call schedule",
            repeat_quiet="zero attempts/submissions/acceptances; unchanged mailbox/journal/events",
            cleanup="all arms completed cleanup",
            protected_recheck=True,
            excluded_scope=["active/pending save-restore", "stock equivalence"],
            clock_sha256=digest(out / "clock.so"),
            binary_sha256=digest(out / "dnethack"),
        ),
    )


class HistoryGameplayNativeTests(unittest.TestCase):
    def test_explicit_native_driver(self):
        from native_fixture_config import KEY, family

        if KEY in os.environ:
            values = family("history", Path(__file__).resolve().parents[2])
            from native_driver_supervision import run_driver

            argv = [
                "--root",
                values["root"],
                "--receipt",
                str(Path(values["receipt"]) / "1-manifest.json"),
                "--revision",
                values["revision"],
                "--output",
                values["artifacts"],
            ]
            code, logs = run_driver(
                Path(__file__).resolve(), argv, values["root"], values["artifacts"]
            )
            self.assertEqual(code, 0, str(logs))
            return
        # Reuse the common native-build profile; no per-family environment set.
        names = (
            "NYARLATHACK_GAME_TESTS",
            "NYARLATHACK_NATIVE_FIXTURE_MODE",
            "NYARLATHACK_NATIVE_BUILD_RECEIPT",
            "NYARLATHACK_NATIVE_EXPECTED_REVISION",
        )
        enabled, mode, receipt, revision = (os.environ.get(name) for name in names)
        if all(name not in os.environ for name in names):
            self.skipTest("unconfigured common native-build profile")
        if enabled != "1" or mode != "source-build" or not receipt or not revision:
            self.fail("complete source-build native configuration required")
        import tempfile
        from native_driver_supervision import run_driver

        root = Path(__file__).resolve().parents[2]
        parent = Path(tempfile.mkdtemp(prefix="history-native-"))
        artifacts = parent / "output"
        argv = [
            "--root",
            str(root),
            "--receipt",
            str(Path(receipt) / "1-manifest.json"),
            "--revision",
            revision,
            "--output",
            str(artifacts),
        ]
        code, logs = run_driver(Path(__file__).resolve(), argv, root, artifacts)
        self.assertEqual(code, 0, str(logs))


def main():
    require(not sys.flags.optimize, "optimized Python unsupported")
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "receipt", "output", "revision"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument(
        "--choice-evidence", help="retained exact model response; no network"
    )
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    native(args)


if __name__ == "__main__":
    main()
