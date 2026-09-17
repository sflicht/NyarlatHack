"""Bounded native static calibration; NEVER permission to run native code.

Caller first uses verify_source_build with independently selected trusted local
builder receipts/root/revision, then supplies the trusted reporter schema (never
values learned from a save). SourceBuildInputs is a typed value, not an
attestation. Cooperating stable files only; no malicious same-UID race defense.
Only Ubuntu GCC 13.3, DWARF5, ELF64 x86-64 little-endian on-build is supported.
"""

from dataclasses import asdict, dataclass
import copy
import hashlib
import os
from pathlib import Path
import re
import selectors
import struct
import subprocess
import time

from native_build_identity import SourceBuildInputs, verify_source_build


class CalibrationError(ValueError):
    """Missing, ambiguous or unsupported static evidence."""


def _require(condition, message):
    if not condition:
        raise CalibrationError(message)


PRODUCER = (
    "GNU C17 13.3.0 -mtune=generic -march=x86-64 -g -std=gnu17 "
    "-fasynchronous-unwind-tables -fstack-protector-strong "
    "-fstack-clash-protection -fcf-protection"
)
MEMBERS = {
    "you": "chaos curio usanity uinsight".split(),
    "chaos_curio_state": "version phase source_len owner charges state disabled name source".split(),
    "chaos_state": ["spent"],
    "obj": "nobj cobj curio_tag".split(),
    "version_info": "incarnation feature_set entity_count struct_sizes".split(),
}
ENUMS = {
    "chaos_curio_phase": {
        "CHAOS_CURIO_" + n: i
        for i, n in enumerate(("VIRGIN", "REJECTED", "ADMITTED", "PLACED", "EXPIRED"))
    },
    "chaos_curio_tag": {
        "CHAOS_CURIO_" + n: i
        for i, n in enumerate(("ORDINARY", "GENERATED", "INERT_REMNANT"))
    },
}
NOOP = [
    "endbr64",
    "push %rbp",
    "mov %rsp,%rbp",
    "mov %rdi,-0x8(%rbp)",
    "nop",
    "pop %rbp",
    "ret",
]


class _ELF:
    """Only uncompressed, ordinary section-table ELF64; no inspected execution."""

    def __init__(self, data):
        self.data = data
        _require(
            len(data) >= 64 and data[:7] == b"\x7fELF\x02\x01\x01",
            "unsupported ELF class/endian/version",
        )
        h = struct.unpack_from("<16sHHIQQQIHHHHHH", data)
        self.kind = h[1]
        _require(
            h[1] in (1, 3) and h[2] == 62 and h[3] == 1 and h[8] == 64,
            "unsupported ELF profile",
        )
        off, width, count, string_index = h[6], h[11], h[12], h[13]
        _require(
            width == 64 and 0 < count < 4096 and string_index < count,
            "unsupported ELF section table",
        )
        _require(off + count * 64 <= len(data), "truncated ELF section table")
        self.sections = [
            struct.unpack_from("<IIQQQQIIQQ", data, off + i * 64) for i in range(count)
        ]
        for section in self.sections:
            _require(not section[2] & 0x800, "compressed ELF sections unsupported")
            if section[1] != 8:
                self._slice(section[4], section[5])
        self.symbols = {}
        tables = [s for s in self.sections if s[1] == 2]
        _require(len(tables) == 1, "missing/ambiguous ELF symtab")
        table = tables[0]
        _require(
            table[9] == 24 and table[5] % 24 == 0 and table[6] < count,
            "invalid ELF symtab",
        )
        strings = self.sections[table[6]]
        _require(strings[1] == 3, "invalid ELF symbol strings")
        names = self._slice(strings[4], strings[5])
        for pos in range(table[4], table[4] + table[5], 24):
            name, info, _, index, value, size = struct.unpack_from("<IBBHQQ", data, pos)
            if not name or not index or index >= 0xFF00:
                continue
            _require(
                index < count and name < len(names) and b"\0" in names[name:],
                "invalid ELF symbol",
            )
            text = names[name : names.index(b"\0", name)].decode("ascii")
            # Only function/data symbols; file/section/debug names are not evidence.
            if info & 15 not in (1, 2):
                continue
            record = {
                "address": value,
                "size": size,
                "section": index,
                "type": info & 15,
            }
            if text in self.symbols:
                # Local static duplicates are normal elsewhere, but never select
                # an ambiguous target symbol later.
                self.symbols[text] = None
            else:
                self.symbols[text] = record

    def _slice(self, offset, size):
        _require(
            0 <= offset <= len(self.data) and 0 <= size <= len(self.data) - offset,
            "truncated ELF data",
        )
        return self.data[offset : offset + size]

    def symbol_bytes(self, name, size):
        symbol = self.symbols.get(name)
        _require(
            symbol is not None and symbol["size"] == size,
            f"missing/ambiguous/wrong-sized symbol: {name}",
        )
        section = self.sections[symbol["section"]]
        delta = symbol["address"] - (section[3] if self.kind == 3 else 0)
        _require(
            section[1] == 1
            and section[2] & 2
            and 0 <= delta
            and delta + size <= section[5],
            "symbol is not mapped file data",
        )
        return self._slice(section[4] + delta, size)


def _number(value):
    match = re.fullmatch(
        r"\((?:data[1248]|implicit_const|udata|sdata)\) (0x[0-9a-f]+|[0-9]+)", value
    )
    _require(match is not None, "unsupported DWARF constant/location")
    return int(match[1], 16 if match[1].startswith("0x") else 10)


def _string(value):
    match = re.fullmatch(
        r"(?:\((?:strp|line_strp)\) \(offset: (?:0x)?[0-9a-f]+\): |\(string\) )(.*)",
        value,
    )
    _require(match is not None, "unsupported DWARF string")
    return match[1]


def _dwarf(lines, root, *, cosmetic=False):
    """Stream CUs; retain only type trees, not functions or giant debug dumps."""
    members = {**MEMBERS}
    if cosmetic:
        members["chaos_state"] = [
            "spent",
            "version",
            "cosmetic_seen",
            "cosmetic_last_turn",
        ]
    layouts, enums, bases, producers, directories = {}, {}, {}, set(), set()
    nodes, stack, current = {}, {}, None
    versions, pointers, units = [], [], 0
    retained = {
        "compile_unit",
        "base_type",
        "pointer_type",
        "typedef",
        "const_type",
        "volatile_type",
        "array_type",
        "subrange_type",
        "structure_type",
        "member",
        "enumeration_type",
        "enumerator",
    }

    def agree(target, name, value):
        _require(
            name not in target or target[name] == value,
            f"conflicting DWARF layout/value: {name}",
        )
        target[name] = value

    def consume():
        if not nodes:
            return

        def width(address, seen=()):
            _require(
                address not in seen and len(seen) < 32 and address in nodes,
                "unsupported DWARF type reference",
            )
            tag, attrs, children = nodes[address]
            if "byte_size" in attrs:
                return _number(attrs["byte_size"])
            ref = re.match(r"\(ref4\) <0x([0-9a-f]+)>", attrs.get("type", ""))
            _require(ref is not None, "missing DWARF type/size")
            result = width(int(ref[1], 16), (*seen, address))
            if tag == "array_type":
                dims = [nodes[c] for c in children if nodes[c][0] == "subrange_type"]
                _require(len(dims) == 1, "only fixed one-dimensional arrays supported")
                dim = dims[0][1]
                _require(
                    _number(dim.get("lower_bound", "(data1) 0")) == 0,
                    "unsupported array lower bound",
                )
                result *= _number(dim.get("upper_bound", "")) + 1
            else:
                _require(
                    tag in ("typedef", "const_type", "volatile_type"),
                    "unsupported DWARF sized type",
                )
            return result

        for address, (tag, attrs, children) in nodes.items():
            name = _string(attrs["name"]) if "name" in attrs else None
            if tag == "compile_unit":
                producers.add(_string(attrs.get("producer", "")))
                directories.add(_string(attrs.get("comp_dir", "")))
            elif tag == "base_type" and name in (
                "int",
                "unsigned int",
                "long unsigned int",
                "char",
            ):
                agree(bases, name, width(address))
            elif tag == "pointer_type":
                _require(width(address) == 8, "unsupported DWARF pointer width")
            elif tag == "structure_type" and name in members:
                if "declaration" in attrs and "byte_size" not in attrs:
                    continue  # Forward declaration is not a layout observation.
                fields = {}
                size = width(address)
                for child in children:
                    ct, ca, _ = nodes[child]
                    member = _string(ca["name"]) if "name" in ca else None
                    if ct != "member" or member not in members[name]:
                        continue
                    _require(member not in fields, "duplicate required DWARF member")
                    ref = re.match(r"\(ref4\) <0x([0-9a-f]+)>", ca.get("type", ""))
                    _require(
                        ref is not None and "bit_size" not in ca,
                        "unsupported required member type/bitfield",
                    )
                    field = {
                        "offset": _number(ca.get("data_member_location", "")),
                        "size": width(int(ref[1], 16)),
                    }
                    _require(
                        field["size"] > 0 and field["offset"] + field["size"] <= size,
                        "DWARF member outside structure",
                    )
                    fields[member] = field
                _require(
                    set(fields) == set(members[name]), f"missing DWARF members: {name}"
                )
                agree(layouts, name, {"size": size, "fields": fields})
            elif tag == "enumeration_type" and name in ENUMS:
                values = {}
                for child in children:
                    ct, ca, _ = nodes[child]
                    if ct == "enumerator":
                        key = _string(ca.get("name", ""))
                        _require(key not in values, "duplicate enumerator")
                        values[key] = _number(ca.get("const_value", ""))
                agree(enums, name, values)

    die = re.compile(
        r"^\s*<(\d+)><([0-9a-f]+)>: Abbrev Number: \d+(?: \(DW_TAG_(\w+)\))?"
    )
    attr = re.compile(r"^\s*<[0-9a-f]+>\s+DW_AT_(\w+)\s*:\s*(.*)$")
    for line in lines:
        _require(len(line) <= 16384, "DWARF line bound exceeded")
        if "Compilation Unit @ offset" in line:
            consume()
            nodes, stack, current = {}, {}, None
            units += 1
            _require(units <= 512, "DWARF unit bound exceeded")
        elif re.match(r"\s*Version:", line):
            versions.append(int(line.split(":")[1].strip()))
        elif re.match(r"\s*Pointer Size:", line):
            pointers.append(int(line.split(":")[1].strip()))
        elif match := die.match(line):
            depth, address, tag = int(match[1]), int(match[2], 16), match[3]
            _require(depth < 64, "DWARF depth bound exceeded")
            stack = {d: a for d, a in stack.items() if d < depth}
            current = None
            if tag in retained:
                _require(
                    address not in nodes and len(nodes) < 30000,
                    "DWARF node bound/duplicate",
                )
                current = (tag, {}, [])
                nodes[address] = current
                parent = stack.get(depth - 1)
                if parent in nodes:
                    nodes[parent][2].append(address)
            stack[depth] = address
        elif current is not None and (match := attr.match(line)):
            _require(match[1] not in current[1], "duplicate DWARF attribute")
            current[1][match[1]] = match[2].strip()
    consume()
    _require(
        units > 0 and versions == [5] * units and pointers == [8] * units,
        "missing/unsupported DWARF5 CU profile",
    )
    _require(
        producers == {PRODUCER} and directories == {root},
        "unsupported DWARF producer/directory profile",
    )
    _require(set(layouts) == set(members), "missing required DWARF layouts")
    _require(
        bases == {"int": 4, "unsigned int": 4, "long unsigned int": 8, "char": 1},
        "unsupported primitive widths",
    )
    _require(enums == ENUMS, "missing/unsupported phase or tag enums")
    return {
        "layouts": layouts,
        "enums": enums,
        "base_sizes": bases,
        "producers": sorted(producers),
        "directories": sorted(directories),
        "pointer_size": 8,
        "dwarf_version": 5,
        "units": units,
    }


def _instructions(text, symbol):
    headers = re.findall(r"^([0-9a-f]+) <([^>]+)>:$", text, re.M)
    _require(
        len(headers) == 1 and headers[0][1] == symbol,
        f"missing/ambiguous disassembly: {symbol}",
    )
    return [
        " ".join(line.split())
        for line in re.findall(r"^\s*[0-9a-f]+:[ \t]+([^\n]+)", text, re.M)
    ]


def _compression(text, symbol):
    ops = _instructions(text, symbol)
    _require(ops == NOOP, f"unsupported compression body: {symbol}")
    return ops


@dataclass(frozen=True)
class NativeProfile:
    layout: dict
    elf_sha256: str
    evidence: dict
    limits: str = (
        "bounded static profile only; not gameplay acceptance; no driver/oracle, "
        "copied artifact, runtime or whole-binary semantic validation; trusted "
        "local source/build provenance remains primary; stable cooperating files only"
    )


def _tool_lines(tool, args, *, limit=16 * 1024 * 1024, timeout=180):
    """Stream fixed read-only binutils, bounding both pipes and every line.

    No shell, receipt commands, ambient tool search or inspected execution.
    Consumers must exhaust or close this generator (including on parser errors).
    """
    _require(tool in ("/usr/bin/readelf", "/usr/bin/objdump"), "unsupported tool")
    _require(
        type(args) is list and all(type(a) is str for a in args),
        "invalid tool arguments",
    )
    version = args == ["--version"]
    inspection = (
        tool == "/usr/bin/readelf"
        and len(args) == 3
        and args[:2] == ["--debug-dump=info", "--wide"]
    ) or (
        tool == "/usr/bin/objdump"
        and len(args) == 4
        and args[:2] == ["-d", "--no-show-raw-insn"]
        and re.fullmatch(r"--disassemble=[a-z_]+", args[2])
    )
    _require(
        version or (inspection and Path(args[-1]).is_absolute()),
        "unsupported read-only tool arguments",
    )
    _require(timeout > 0, "tool timeout")
    deadline = time.monotonic() + timeout
    process = None
    try:
        process = subprocess.Popen(
            [tool, *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
            cwd="/",
            bufsize=0,
        )
        total, errors = 0, bytearray()
        buffers = {process.stdout: b"", process.stderr: b""}
        with selectors.DefaultSelector() as selector:
            for pipe in buffers:
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                _require(remaining > 0, "tool timeout")
                ready = selector.select(remaining)
                _require(bool(ready), "tool timeout")
                for key, _ in ready:
                    pipe = key.fileobj
                    chunk = os.read(pipe.fileno(), 65536)
                    total += len(chunk)
                    _require(total <= limit, "tool output bound exceeded")
                    parts = (buffers[pipe] + chunk).split(b"\n")
                    buffers[pipe] = parts.pop()
                    if not chunk:
                        selector.unregister(pipe)
                        if buffers[pipe]:
                            parts.append(buffers[pipe])
                        buffers[pipe] = b""
                    _require(len(buffers[pipe]) <= 16384, "tool line bound exceeded")
                    for line in parts:
                        _require(len(line) <= 16384, "tool line bound exceeded")
                        if pipe is process.stderr:
                            _require(
                                len(errors) + len(line) < 65536,
                                "tool stderr output bound exceeded",
                            )
                            errors.extend(line + b"\n")
                        else:
                            yield line.decode("utf-8") + "\n"
            remaining = deadline - time.monotonic()
            _require(remaining > 0, "tool timeout")
            code = process.wait(timeout=remaining)
            _require(
                code == 0 and not errors,
                f"tool failed ({code}): {errors.decode('utf-8', 'replace')}",
            )
    except subprocess.TimeoutExpired as exc:
        raise CalibrationError("tool timeout") from exc
    except (OSError, UnicodeError) as exc:
        raise CalibrationError(f"read-only tool failed: {exc}") from exc
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()
            process.stderr.close()


def _read(path, limit=128 * 1024 * 1024):
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    _require(len(data) <= limit, f"file bound exceeded: {path}")
    return data


def _macro(text, name):
    values = re.findall(
        r"^\s*#\s*define\s+" + re.escape(name) + r"\s+([^\n]+)", text, re.M
    )
    _require(len(values) == 1, f"missing/ambiguous macro: {name}")
    match = re.fullmatch(r"(0x[0-9a-fA-F]+|[0-9]+)(?:UL)?\s*(?:/\*.*\*/)?", values[0])
    _require(match is not None, f"unsupported macro: {name}")
    return int(match[1], 16 if match[1].startswith("0x") else 10)


def _exact(actual, expected):
    """JSON type fidelity, including bool/int and unexpected nested keys."""
    if type(actual) is not type(expected):
        return False
    if type(actual) is dict:
        return actual.keys() == expected.keys() and all(
            type(k) is str and _exact(actual[k], expected[k]) for k in actual
        )
    return type(actual) in (int, str, bool) and actual == expected


def _disassemble(path, image, symbol):
    record = image.symbols.get(symbol)
    _require(
        record is not None and record["type"] == 2 and record["size"] > 0,
        f"missing/ambiguous function symbol: {symbol}",
    )
    text = "".join(
        _tool_lines(
            "/usr/bin/objdump",
            ["-d", "--no-show-raw-insn", "--disassemble=" + symbol, str(path)],
        )
    )
    ops = _instructions(text, symbol)
    header = re.search(r"^([0-9a-f]+) <", text, re.M)
    _require(
        int(header[1], 16) == record["address"],
        f"disassembly address mismatch: {symbol}",
    )
    return text, ops


def _sequence(ops, patterns, label):
    """Require one contiguous, operand-preserving bounded signature."""
    matches = [
        i
        for i in range(len(ops) - len(patterns) + 1)
        if all(re.fullmatch(p, op) for p, op in zip(patterns, ops[i:]))
    ]
    _require(len(matches) == 1, f"missing/ambiguous {label} signature")
    return ops[matches[0] : matches[0] + len(patterns)]


def _cosmetic_init(ops, layout, header_version):
    """Exact GCC13 initializer body; version is read from the linked instruction.

    This adds a policy/schema observation, not a new compiler/ABI allowlist.
    No execution of the inspected ELF, and no reporter/save-derived values.
    """
    _require(
        layout["fields"]["version"] == {"offset": 0, "size": 4},
        "unsupported chaos version member",
    )
    _require(len(ops) == 15, "unsupported chaos initializer body")
    value = re.fullmatch(r"movl \$0x([0-9a-f]+),\(%rax\)", ops[11])
    _require(value is not None, "unsupported chaos initializer version store")
    version = int(value[1], 16)
    patterns = (
        [
            re.escape(op)
            for op in [
                "endbr64",
                "push %rbp",
                "mov %rsp,%rbp",
                "sub $0x10,%rsp",
                "mov %rdi,-0x8(%rbp)",
                "mov -0x8(%rbp),%rax",
                f"mov $0x{layout['size']:x},%edx",
                "mov $0x0,%esi",
                "mov %rax,%rdi",
            ]
        ]
        + [r"call [0-9a-f]+ <memset@plt>"]
        + [
            re.escape(op)
            for op in [
                "mov -0x8(%rbp),%rax",
                f"movl $0x{version:x},(%rax)",
                "nop",
                "leave",
                "ret",
            ]
        ]
    )
    _sequence(ops, patterns, "chaos initializer")
    _require(version == header_version == 2, "unsupported chaos initializer policy")
    return version


def _measure(inputs):
    root, path = inputs.build_root, inputs.tuple_dir / "dnethack"
    data = _read(path)
    digest = hashlib.sha256(data).hexdigest()
    _require(digest == inputs.artifact_hashes["dnethack"], "ELF identity hash mismatch")
    image = _ELF(data)
    _require(image.kind == 3, "selected ELF must be supported PIE")
    raw_version = image.symbol_bytes("version_data.0", 32)
    names = MEMBERS["version_info"]
    version = dict(zip(names, struct.unpack("<4Q", raw_version)))
    date = _read(root / "include/date.h", 65536).decode("ascii")
    macros = (
        "VERSION_NUMBER",
        "VERSION_FEATURES",
        "VERSION_SANITY1",
        "VERSION_SANITY2",
    )
    _require(
        version == dict(zip(names, (_macro(date, m) for m in macros))),
        "ELF version bytes disagree with current date header",
    )
    curio_header = _read(root / "include/chaos_curio.h", 65536).decode("ascii")
    curio_version = _macro(curio_header, "CHAOS_CURIO_VERSION")
    policy_header = _read(root / "include/chaos_protocol.h", 65536).decode("ascii")
    policy_version = _macro(policy_header, "CHAOS_STATE_VERSION")
    _require(policy_version in (1, 2), "unsupported chaos state policy")
    source_limit = _macro(curio_header, "CHAOS_CURIO_SOURCE")
    _require(
        curio_version == 1 and source_limit == 4096,
        "unsupported curio source/version profile",
    )
    lines = _tool_lines(
        "/usr/bin/readelf",
        ["--debug-dump=info", "--wide", str(path)],
        limit=512 * 1024 * 1024,
    )
    try:
        dwarf = _dwarf(lines, str(root), cosmetic=policy_version == 2)
    finally:
        close = getattr(lines, "close", None)
        if close:
            close()
    layouts = dwarf["layouts"]
    record, you = layouts["chaos_curio_state"], layouts["you"]
    header, obj = layouts["version_info"], layouts["obj"]
    _require(
        header
        == {
            "size": 32,
            "fields": {n: {"offset": i * 8, "size": 8} for i, n in enumerate(names)},
        },
        "unsupported version header layout",
    )
    _require(
        record["fields"]["name"]["size"] == 49
        and record["fields"]["source"]["size"] == source_limit + 1,
        "unsupported source/name bounds",
    )
    _require(
        you["fields"]["curio"]["size"] == record["size"]
        and you["fields"]["chaos"]["size"] == layouts["chaos_state"]["size"],
        "embedded structure width mismatch",
    )
    _require(
        obj["fields"]
        == {
            "nobj": {"offset": 0, "size": 8},
            "cobj": {"offset": 16, "size": 8},
            "curio_tag": {"offset": 28, "size": 1},
        },
        "unsupported bones member profile",
    )
    compression = []
    files_path = root / "src/files.o"
    files_image = _ELF(_read(files_path))
    _require(files_image.kind == 1, "files.o must be relocatable ELF")
    for target, elf in ((files_path, files_image), (path, image)):
        for symbol in ("compress", "uncompress"):
            text, _ = _disassemble(target, elf, symbol)
            compression.append(
                {
                    "path": str(target),
                    "symbol": symbol,
                    "ops": _compression(text, symbol),
                }
            )
    ops = {
        symbol: _disassemble(path, image, symbol)[1]
        for symbol in (
            "inert_bones_curios",
            "resetobjs",
            "savebones",
            "restobjchn",
            "store_version",
        )
    }
    helper = image.symbols["inert_bones_curios"]
    _require(helper["size"] == 97, "unsupported inert_bones_curios size")
    call = f"call {helper['address']:x} <inert_bones_curios>"
    callers = {}
    for symbol, count in (
        ("inert_bones_curios", 1),
        ("resetobjs", 1),
        ("savebones", 2),
    ):
        references = [op for op in ops[symbol] if "<inert_bones_curios>" in op]
        _require(
            references == [call] * count, f"unsupported bones callee/count: {symbol}"
        )
        if symbol != "inert_bones_curios":
            callers[symbol] = count
    inert = ops["inert_bones_curios"]
    tag_guard = _sequence(
        inert,
        [
            re.escape("movzbl 0x1c(%rax),%eax"),
            re.escape("test %al,%al"),
            r"je [0-9a-f]+ <inert_bones_curios\+0x[0-9a-f]+>",
            re.escape("mov -0x8(%rbp),%rax"),
            re.escape("movb $0x2,0x1c(%rax)"),
        ],
        "bones tag",
    )
    _require(
        "mov 0x10(%rax),%rax" in inert and "mov (%rax),%rax" in inert,
        "missing bones cobj/nobj traversal",
    )
    _sequence(
        inert,
        [re.escape("mov 0x10(%rax),%rax"), re.escape("mov %rax,%rdi"), re.escape(call)],
        "bones recursion",
    )
    restore = _sequence(
        ops["restobjchn"],
        [
            re.escape(f"mov $0x{obj['size']:x},%edx"),
            re.escape("mov %rbx,%rsi"),
            re.escape("mov %r12d,%edi"),
            r"call [0-9a-f]+ <mread>",
            re.escape("cmpb $0x0,-0x44(%rbp)"),
            r"je [0-9a-f]+ <restobjchn\+0x[0-9a-f]+>",
            re.escape("movzbl 0x1c(%rbx),%eax"),
            re.escape("test %al,%al"),
            r"je [0-9a-f]+ <restobjchn\+0x[0-9a-f]+>",
            re.escape("movb $0x2,0x1c(%rbx)"),
        ],
        "restore ghostly/tag",
    )
    _require(restore[5] == restore[8], "restore guard targets differ")
    address = image.symbols["version_data.0"]["address"]
    store = _sequence(
        ops["store_version"],
        [
            re.escape("mov $0x20,%edx"),
            rf"lea 0x[0-9a-f]+\(%rip\),%rcx # {address:x} <version_data\.0>",
            re.escape("mov %rcx,%rsi"),
            re.escape("mov %eax,%edi"),
            r"call [0-9a-f]+ <bwrite>",
        ],
        "store version pointer/length",
    )
    calls = [
        op.split("<", 1)[1][:-1]
        for op in ops["store_version"]
        if op.startswith("call ")
    ]
    _require(
        calls == ["bufoff", "bwrite", "bufon"], "unsupported version buffering calls"
    )
    # The linked ELF normally resolves these too; record/check numeric targets
    # when defined. The bounded bones callee checks above always require symbols.
    for sequence in (restore, ops["store_version"]):
        for op in sequence:
            match = re.fullmatch(r"call ([0-9a-f]+) <(mread|bufoff|bwrite|bufon)>", op)
            if match and match[2] in image.symbols:
                target = image.symbols[match[2]]
                _require(
                    target is not None and int(match[1], 16) == target["address"],
                    "version/restore callee address mismatch",
                )
    spent = layouts["chaos_state"]["fields"]["spent"]
    measured = {
        "byteorder": "little",
        "int_size": dwarf["base_sizes"]["int"],
        "unsigned_size": dwarf["base_sizes"]["unsigned int"],
        # These are this verified source profile's compression settings, not a
        # general proof about all buffer paths or an active preprocessor query.
        "external_compression": False,
        "internal_compression": False,
        "version": curio_version,
        "placed": dwarf["enums"]["chaos_curio_phase"]["CHAOS_CURIO_PLACED"],
        "source_limit": source_limit,
        "record_size": record["size"],
        "record": record["fields"],
        "you_size": you["size"],
        "you": you["fields"],
        "spent_offset": spent["offset"],
        "spent_size": spent["size"],
        "save_header_size": header["size"],
        "save_header": header["fields"],
        "save_header_values": version,
    }
    policy_evidence = {"schema": "legacy-state1"}
    if policy_version == 2:
        chaos = layouts["chaos_state"]
        init_ops = _disassemble(path, image, "chaos_state_init")[1]
        measured.update(
            chaos_state_version=_cosmetic_init(init_ops, chaos, policy_version),
            chaos_size=chaos["size"],
            chaos_fields={k: v for k, v in chaos["fields"].items() if k != "spent"},
        )
        policy_evidence = {"schema": "cosmetic-state2", "initializer": init_ops}
    evidence = {
        "policy": policy_evidence,
        "dwarf": dwarf,
        "compression": compression,
        "version": {
            "address": address,
            "bytes_hex": raw_version.hex(),
            "store_signature": store,
        },
        "bones": {
            "helper": helper,
            "tag_signature": tag_guard,
            "recursive_call": call,
            "caller_counts": callers,
            "restore_signature": restore,
        },
        "profile": inputs.metadata["profile"],
        "revision": inputs.revision,
        "build_root": str(root),
        "receipt_dir": inputs.metadata["receipt_dir"],
    }
    return measured, digest, evidence


def validate_native_profile(inputs, expected_layout):
    """Reverify trusted local inputs before/after read-only native calibration.

    The caller's root/revision must already be independently selected, not
    learned from arbitrary receipts. A typed value alone is not attestation.
    Never call this on expected values learned from the save under test.
    """
    _require(type(inputs) is SourceBuildInputs, "typed SourceBuildInputs required")
    _require(type(inputs.mode) is int and inputs.mode == 1, "unsupported native mode")
    _require(
        type(inputs.metadata) is dict
        and inputs.metadata.get("profile") == "system-gcc13-local",
        "unsupported source profile",
    )
    try:
        fixed = copy.deepcopy(inputs)
        root, revision = fixed.build_root, fixed.revision
        receipts = fixed.metadata["receipt_dir"]
        before = verify_source_build(receipts, root, revision, mode=1)
        _require(
            type(before) is SourceBuildInputs and asdict(before) == asdict(fixed),
            "input identity differs from independent verification",
        )
        measured, digest, evidence = _measure(fixed)
        after = verify_source_build(receipts, root, revision, mode=1)
        _require(
            type(after) is SourceBuildInputs and asdict(after) == asdict(fixed),
            "input identity changed during calibration",
        )
        _require(
            _exact(expected_layout, measured),
            "expected layout/schema differs from measured native profile",
        )
        return NativeProfile(copy.deepcopy(measured), digest, evidence)
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        KeyError,
        struct.error,
        subprocess.SubprocessError,
    ) as exc:
        if isinstance(exc, CalibrationError):
            raise
        raise CalibrationError(f"invalid native calibration inputs: {exc}") from exc
