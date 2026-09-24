"""Test-only value bridge to the actual C runtime, never native effect commands.

The native codec is host-specific, just like the retained native save. The
transition bridge uses bounded network-order integers/length-prefixed strings.
No journal text is compiled or evaluated. Independent bundle authentication is
required by the caller; self-rehashed negatives are NOT authentic recordings.
"""

import copy
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess

from chaos.next_use_journal import read_journal, JournalError, _TRANSITION, _POST

ROOT = Path(__file__).resolve().parents[2]
TRANSITION = [
    k
    for k in _TRANSITION.split()
    if k not in ("expected_token", "post", "private_records", "public_records")
]
POST = _POST.split()
PRIVATE = "next_use_private_v kind seq at_move program_id source_sha256".split()
INTENT = (
    "callback_ordinal trigger validation failure_code root state_before "
    "state_after delay_used_after context_sha256 intent_present intent_sha256 "
    "intent_sha256_present failure_code_present"
).split()
EFFECT = "family outcome root activation_monstermoves m_id".split()
TERMINATION = "failure_code reason slot_f slot_w w_runtime".split()
PUBLIC = "next_use_public_v family phase root notice_seq end_seq".split()
TOKEN = "root active remap consumed".split()
SNAP = (
    "snapshot_v program_id phase slot_w slot_f w_runtime state delay_used "
    "callback_ordinal admission_move program_expiry delay_until variant source_length "
    "origin_w_live origin_f_live origin_w origin_f origin_w_deadline origin_f_deadline "
    "armed_m_id replay_cursor run_token level_token activation_monstermoves armed_root "
    "witnessed attention_claimed whistle_count fountain_count next_seq termination_emitted "
    "identity_unsafe last_root callback_w callback_f run_token_high journal_state "
    "capture_incomplete journal_bytes"
).split()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def native_snapshot(save, source, destination, prefix, exported):
    """Locate one exact source in a trusted save; C subsequently reads its codec."""
    raw = save.read_bytes()
    assert raw.count(source) == 1, "ambiguous native snapshot source"
    start = raw.index(source) - 355  # native v5: 40 int32 + three 65-byte hashes
    assert start >= 0
    codec = raw[start : start + 355 + len(source)]
    values = dict(zip(SNAP, struct.unpack("=40I", codec[:160])))
    values["run_token"] |= values.pop("run_token_high") << 32
    for index, key in enumerate(("source_sha256", "binding_sha256", "journal_sha256")):
        b = codec[160 + index * 65 : 225 + index * 65]
        assert b[-1] == 0
        values[key] = b.rstrip(b"\0").decode("ascii")
    assert values["snapshot_v"] == 5 and values["source_length"] == len(source)
    assert values["source_sha256"] == sha(source)
    for key in values.keys() & exported.keys():
        assert values[key] == exported[key], "native/export binding: " + key
    prefix_bytes = prefix.read_bytes()
    lines = prefix_bytes.splitlines(keepends=True)
    parsed = read_journal(prefix)
    # An actual terminal save includes the end row, which consumes no cursor.
    # Preserve its COMPLETE anchor verbatim; never normalize it to OPEN.
    complete = parsed["status"] == "structurally_complete"
    assert parsed["status"] in ("incomplete", "structurally_complete")
    assert values["replay_cursor"] == len(parsed["records"]) - (2 if complete else 1)
    assert values["journal_state"] == (2 if complete else 1)
    assert values["capture_incomplete"] == 0
    assert values["journal_bytes"] == sum(map(len, lines))
    assert values["journal_sha256"] == json.loads(lines[-1])["sha256"]
    destination.write_bytes(codec)
    return values


def build(directory):
    binary = directory / "semantic-preflight"
    if binary.exists():
        return binary
    source = ROOT / "tests/chaos/next_use_semantic_preflight.c"
    shutil.copy2(source, directory / source.name)
    shutil.copy2(__file__, directory / Path(__file__).name)
    command = [
        "cc",
        "-DCHAOS",
        "-ffunction-sections",
        "-fdata-sections",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-Wno-misleading-indentation",
        "-isystem",
        str(ROOT / "include"),
        str(source),
    ]
    command += [
        str(ROOT / ("src/" + n + ".c"))
        for n in (
            "chaos_next_use",
            "chaos_next_use_admission",
            "chaos_protocol",
            "chaos_lua",
        )
    ]
    command += [
        "-Wl,--gc-sections",
        *subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "lua5.4"], text=True
        ).split(),
        "-lm",
        "-o",
        str(binary),
    ]
    (directory / "semantic-build-command.json").write_text(
        json.dumps(command, indent=2)
    )
    inputs = [
        source,
        ROOT / "src/chaos_next_use_runtime.c",
        ROOT / "tests/chaos/next_use_replay.c",
    ]
    inputs += [Path(s) for s in command if s.endswith(".c")]
    (directory / "semantic-build-inputs.json").write_text(
        json.dumps({str(p): sha(p.read_bytes()) for p in inputs}, indent=2)
    )
    result = subprocess.run(command, capture_output=True, text=True, timeout=45)
    (directory / "semantic-build.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stderr
    return binary


def wire(records, path):
    output = bytearray(b"NUSP1\0")

    def value(v):
        if isinstance(v, str):
            raw = v.encode("ascii")
            assert len(raw) <= 64
            output.extend(struct.pack(">Q", len(raw)))
            output.extend(raw)
        else:
            assert type(v) is int and 0 <= v <= 9223372036854775807
            output.extend(struct.pack(">Q", v))

    def fields(v, names):
        for k in names:
            value(v[k])

    transitions = [r["data"] for r in records if r["kind"] == "transition"]
    assert 0 < len(transitions) <= 4096
    value(len(transitions))
    for t in transitions:
        fields(t, TRANSITION)
        fields(t["post"], POST)
        fields(t["expected_token"], TOKEN)
        assert len(t["private_records"]) == t["private_count"] <= 4
        assert len(t["public_records"]) == t["public_count"] <= 1
        for r in t["private_records"]:
            fields(r, PRIVATE)
            fields(r["data"], {3: INTENT, 4: EFFECT, 5: TERMINATION}[r["kind"]])
            if r["kind"] == 3:
                fields(r["data"]["intent"], ["op", "state"])
        for r in t["public_records"]:
            fields(r, PUBLIC)
    path.write_bytes(output)


def run_validator(records, directory, label="authentic"):
    path = directory / (label + ".wire")
    wire(records, path)
    result = subprocess.run(
        [
            str(build(directory)),
            str(directory / "initial.codec"),
            str(directory / "middle.codec"),
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    (directory / (label + ".log")).write_text(result.stdout + result.stderr)
    assert result.returncode in (0, 1), result.stdout + result.stderr
    report = json.loads(result.stdout)
    report["returncode"] = result.returncode
    return report


def validate_bundle(decoded, files, directory):
    source = files["source"].read_bytes()
    complete = files["record/next_use-journal.jsonl"].read_bytes()
    for key in (
        "prefix/next_use-journal.jsonl",
        "middle-prefix/next_use-journal.jsonl",
    ):
        assert complete.startswith(files[key].read_bytes()), (
            "checkpoint prefix binding: " + key
        )
    states = json.loads(files["states.json"].read_text())
    schedule = json.loads(files["schedule.json"].read_text())
    middle = [s for s, op in zip(states, schedule) if op["kind"] == "save"]
    assert len(middle) == 1
    initial = native_snapshot(
        files["save"],
        source,
        directory / "initial.codec",
        files["prefix/next_use-journal.jsonl"],
        json.loads(files["initial"].read_text()),
    )
    native_snapshot(
        next(p for k, p in files.items() if k.startswith("middle-save/")),
        source,
        directory / "middle.codec",
        files["middle-prefix/next_use-journal.jsonl"],
        middle[0],
    )
    header = decoded["records"][0]["data"]["snapshot"]
    # NONE is the original pre-writer header; OPEN is the acknowledged native
    # saved prefix. Compare gameplay values, but never rewrite either anchor.
    for k in initial:
        if k not in ("journal_state", "journal_bytes", "journal_sha256"):
            assert initial[k] == header[k], "header/native binding: " + k
    assert initial["replay_cursor"] == 0, (
        "this bounded pair requires its genuine header-only start"
    )
    # Independent native observations bound clocks at each input/session edge.
    previous = json.loads(files["initial"].read_text())
    ts = [r["data"] for r in decoded["records"] if r["kind"] == "transition"]
    for state in states:
        for t in ts[previous["replay_cursor"] : state["replay_cursor"]]:
            assert previous["monstermoves"] <= t["at_move"] <= state["monstermoves"]
        previous = state
    result = run_validator(decoded["records"], directory)
    assert result["returncode"] == 0, result
    (directory / "semantic-result.json").write_text(json.dumps(result, indent=2))
    return result


def rehash(records, path):
    previous, lines = "0" * 64, []
    for r in records:
        r["prev"] = previous
        payload = json.dumps(r, separators=(",", ":"), ensure_ascii=True).encode()
        previous = sha(payload)
        lines.append(
            b'{"payload":' + payload + b',"sha256":"' + previous.encode() + b'"}\n'
        )
    path.write_bytes(b"".join(lines))


def exercise_negatives(test, decoded, files, directory):
    reports = []
    for name in ("source_next_state", "cursor_duplicate", "poststate", "context"):
        records = copy.deepcopy(decoded["records"])
        transitions = [r["data"] for r in records if r["kind"] == "transition"]
        if name == "source_next_state":
            action = next(
                t for t in transitions if t["operation"] == 1 and t["family"] == 2
            )
            for t in transitions[action["cursor"] - 1 :]:
                t["state"] = 2
            d = action["private_records"][0]["data"]
            d["state_after"] = d["intent"]["state"] = 2
            d["intent_sha256"] = sha(
                json.dumps(
                    {"next_use_intent_v": 2, "op": "fountain_refresh", "state": 2},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            )
        elif name == "cursor_duplicate":
            transitions[1]["cursor"] = 1
        elif name == "poststate":
            transitions[0]["post"]["expected_manifest_m_id"] = 1
        else:
            action = next(t for t in transitions if t["operation"] == 1)
            action["private_records"][0]["data"]["context_sha256"] = "0" * 64
        path = directory / ("validator-negative-" + name + ".jsonl")
        rehash(records, path)
        try:
            read_journal(path)
            strict = "passed"
        except JournalError as exc:
            strict = str(exc)
        test.assertEqual(strict == "passed", name in ("source_next_state", "poststate"))
        # Deliberately independent: no weakening of strict reader or trusted
        # digest gate to admit these fabricated validator-negative recordings.
        report = run_validator(records, directory, "validator-negative-" + name)
        test.assertEqual(report["returncode"], 1, report)
        test.assertEqual(report["unchanged"], 1, report)
        expected = {
            "source_next_state": (35, 36, "source_dependent_next_state"),
            "cursor_duplicate": (1, 1, "cursor"),
            "poststate": (0, 1, "poststate"),
            "context": (2, 3, "private_or_public_carrier_mismatch"),
        }[name]
        test.assertEqual(
            (report["cursor"], report["rejected_cursor"], report["reason"]), expected
        )
        reports.append(
            dict(
                name=name, strict_python=strict, native_playback_started=False, **report
            )
        )
    (directory / "validator-negatives.json").write_text(json.dumps(reports, indent=2))
