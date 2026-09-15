"""Synthetic unit inputs only; never engine/native acceptance evidence.

Tiny ELF bytes and invented readelf/objdump responses test the real parsers.
No compiler, game, real receipt or held test module is invoked/imported.
"""

import copy
import importlib.util
import io
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from native_build_identity import SourceBuildInputs

PRODUCER = (
    "GNU C17 13.3.0 -mtune=generic -march=x86-64 -g -std=gnu17 "
    "-fasynchronous-unwind-tables -fstack-protector-strong "
    "-fstack-clash-protection -fcf-protection"
)
FIELDS = {
    "chaos_curio_state": (
        4176,
        {
            "version": (0, 4),
            "phase": (4, 4),
            "source_len": (8, 4),
            "owner": (12, 4),
            "charges": (16, 4),
            "state": (20, 4),
            "disabled": (24, 4),
            "name": (28, 49),
            "source": (77, 4097),
        },
    ),
    "chaos_state": (80, {"spent": (4, 4)}),
    "you": (
        5000,
        {
            "chaos": (0, 80),
            "curio": (80, 4176),
            "usanity": (4400, 4),
            "uinsight": (4404, 4),
        },
    ),
    "obj": (256, {"nobj": (0, 8), "cobj": (16, 8), "curio_tag": (28, 1)}),
    "version_info": (
        32,
        {
            "incarnation": (0, 8),
            "feature_set": (8, 8),
            "entity_count": (16, 8),
            "struct_sizes": (24, 8),
        },
    ),
}
ENUMS = {
    "chaos_curio_phase": dict(
        zip(
            [
                "CHAOS_CURIO_" + n
                for n in ("VIRGIN", "REJECTED", "ADMITTED", "PLACED", "EXPIRED")
            ],
            range(5),
        )
    ),
    "chaos_curio_tag": dict(
        zip(
            ["CHAOS_CURIO_" + n for n in ("ORDINARY", "GENERATED", "INERT_REMNANT")],
            range(3),
        )
    ),
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


def dwarf_fixture(root="/synthetic", fields=None, producer=PRODUCER):
    """Invent a small readelf --wide DWARF5 tree, not copied native output."""
    fields = fields or FIELDS
    lines = ["  Compilation Unit @ offset 0:", "   Version: 5", "   Pointer Size: 8"]
    serial = 0

    def die(depth, tag, **attrs):
        nonlocal serial
        serial += 16
        address = serial
        lines.append(f" <{depth}><{address:x}>: Abbrev Number: 1 (DW_TAG_{tag})")
        for key, val in attrs.items():
            if key == "type":
                val = f"(ref4) <0x{val:x}>"
            elif isinstance(val, int):
                val = f"(data2) {val}"
            else:
                val = f"(string) {val}"
            lines.append(f"    <{address + 1:x}> DW_AT_{key} : {val}")
        return address

    die(0, "compile_unit", producer=producer, comp_dir=root)
    sizes = {}
    for name, size in [
        ("int", 4),
        ("unsigned int", 4),
        ("long unsigned int", 8),
        ("char", 1),
    ]:
        sizes[size] = die(1, "base_type", name=name, byte_size=size)
    die(1, "pointer_type", byte_size=8)
    for size in (49, 4097, 80, 4176):
        sizes[size] = die(1, "array_type", type=sizes[1])
        die(2, "subrange_type", upper_bound=size - 1)
    for name, (size, members) in fields.items():
        die(1, "structure_type", name=name, byte_size=size)
        for member, (offset, width) in members.items():
            die(
                2, "member", name=member, type=sizes[width], data_member_location=offset
            )
    for name, members in ENUMS.items():
        die(1, "enumeration_type", name=name, byte_size=4)
        for member, value in members.items():
            die(2, "enumerator", name=member, const_value=value)
    return "\n".join(lines) + "\n"


def elf_fixture(values=(11, 22, 33, 44), elf_type=3):
    """Tiny synthetic ELF64 symbol/section mapping; never executable code."""
    names = [
        "compress",
        "uncompress",
        "inert_bones_curios",
        "resetobjs",
        "savebones",
        "restobjchn",
        "store_version",
        "version_data.0",
    ]
    strings = b"\0" + b"\0".join(n.encode() for n in names) + b"\0"
    snames = b"\0.text\0.rodata\0.symtab\0.strtab\0.shstrtab\0.debug_info\0"
    text = bytes(2048)
    rodata = struct.pack("<4Q", *values)
    symbols = bytes(24)
    for i, name in enumerate(names):
        version = name == "version_data.0"
        symbols += struct.pack(
            "<IBBHQQ",
            strings.index(name.encode()),
            1 if version else 2,
            0,
            2 if version else 1,
            0x3000 if version else 0x1000 + i * 256,
            32 if version else (97 if i == 2 else 64),
        )
    chunks = [b"", text, rodata, symbols, strings, snames, b"synthetic"]
    data = bytearray(64)
    sections = []
    for i, chunk in enumerate(chunks):
        name = [
            b"",
            b".text",
            b".rodata",
            b".symtab",
            b".strtab",
            b".shstrtab",
            b".debug_info",
        ][i]
        sections.append(
            (
                snames.index(name) if name else 0,
                [0, 1, 1, 2, 3, 3, 1][i],
                6 if i == 1 else (2 if i == 2 else 0),
                0x1000 if i == 1 else (0x3000 if i == 2 else 0),
                len(data),
                len(chunk),
                4 if i == 3 else 0,
                0,
                1,
                24 if i == 3 else 0,
            )
        )
        data.extend(chunk)
    shoff = len(data)
    for section in sections:
        data.extend(struct.pack("<IIQQQQIIQQ", *section))
    ident = b"\x7fELF\x02\x01\x01" + bytes(9)
    data[:64] = struct.pack(
        "<16sHHIQQQIHHHHHH",
        ident,
        elf_type,
        62,
        1,
        0,
        0,
        shoff,
        0,
        64,
        0,
        0,
        64,
        len(sections),
        5,
    )
    return bytes(data)


def disassembly(symbol, ops, base=0x1000):
    return (
        f"{base:016x} <{symbol}>:\n"
        + "\n".join(f"  {base + i:x}:\t{op}" for i, op in enumerate(ops))
        + "\n"
    )


class CalibrationAPITests(unittest.TestCase):
    def test_native_calibration_api_exists(self):
        self.assertIsNotNone(importlib.util.find_spec("native_build_calibration"))
        import native_build_calibration as calibration

        self.assertTrue(callable(calibration.validate_native_profile))


class ParserTests(unittest.TestCase):
    def setUp(self):
        import native_build_calibration as calibration

        self.c = calibration

    def test_elf_maps_actual_version_symbol_bytes(self):
        image = self.c._ELF(elf_fixture())
        self.assertEqual(
            image.symbol_bytes("version_data.0", 32), struct.pack("<4Q", 11, 22, 33, 44)
        )
        self.assertEqual(image.symbols["inert_bones_curios"]["size"], 97)

    def test_elf_rejects_unsupported_or_truncated_input(self):
        for data in (
            b"",
            elf_fixture()[:100],
            elf_fixture()[:5] + b"\x02" + elf_fixture()[6:],
            elf_fixture()[:18] + b"\xb7\x00" + elf_fixture()[20:],
        ):
            with self.subTest(data=data[:20]):
                with self.assertRaises(self.c.CalibrationError):
                    self.c._ELF(data)

    def test_dwarf_measures_members_arrays_primitives_and_enums(self):
        result = self.c._dwarf(io.StringIO(dwarf_fixture()), "/synthetic")
        self.assertEqual(
            result["layouts"]["you"],
            {
                "size": 5000,
                "fields": {
                    k: {"offset": o, "size": s}
                    for k, (o, s) in FIELDS["you"][1].items()
                },
            },
        )
        self.assertEqual(
            result["layouts"]["chaos_curio_state"]["fields"]["source"]["size"], 4097
        )
        self.assertEqual(result["enums"], ENUMS)
        self.assertEqual(result["base_sizes"]["int"], 4)
        self.assertEqual(result["producers"], [PRODUCER])

    def test_dwarf_rejects_missing_conflicting_and_unsupported_evidence(self):
        changed = copy.deepcopy(FIELDS)
        changed["you"][1]["curio"] = (88, 4176)
        cases = [
            "",
            dwarf_fixture(producer="GNU C17 12.0"),
            dwarf_fixture(root="/foreign"),
            dwarf_fixture().replace("Version: 5", "Version: 4"),
            dwarf_fixture().replace("Pointer Size: 8", "Pointer Size: 4"),
            dwarf_fixture() + dwarf_fixture(fields=changed),
            dwarf_fixture().replace("DW_AT_data_member_location", "DW_AT_unknown"),
            dwarf_fixture().replace("(data2) 4096", "(exprloc) unknown"),
            dwarf_fixture().replace("CHAOS_CURIO_PLACED", "UNKNOWN_ENUM"),
        ]
        for text in cases:
            with self.subTest(text=text[:90]):
                with self.assertRaises(self.c.CalibrationError):
                    self.c._dwarf(io.StringIO(text), "/synthetic")

    def test_noop_allowlist_preserves_operands_and_all_instructions(self):
        self.assertEqual(
            self.c._compression(disassembly("compress", NOOP), "compress"), NOOP
        )
        for ops in (
            NOOP[1:],
            NOOP + ["call 123 <system>"],
            [op.replace("-0x8", "-0x10") for op in NOOP],
            ["endbr64", "ret"],
        ):
            with self.subTest(ops=ops):
                with self.assertRaises(self.c.CalibrationError):
                    self.c._compression(disassembly("compress", ops), "compress")
        with self.assertRaises(self.c.CalibrationError):
            self.c._compression(disassembly("uncompress", NOOP), "compress")


def schema_fixture():
    def fields(name):
        return {k: {"offset": o, "size": s} for k, (o, s) in FIELDS[name][1].items()}

    return {
        "byteorder": "little",
        "int_size": 4,
        "unsigned_size": 4,
        "external_compression": False,
        "internal_compression": False,
        "version": 1,
        "placed": 3,
        "source_limit": 4096,
        "record_size": 4176,
        "record": fields("chaos_curio_state"),
        "you_size": 5000,
        "you": fields("you"),
        "spent_offset": 4,
        "spent_size": 4,
        "save_header_size": 32,
        "save_header": fields("version_info"),
        "save_header_values": dict(zip(FIELDS["version_info"][1], (11, 22, 33, 44))),
    }


def bones_fixture():
    # Invented minimal bounded signatures, not actual native observations.
    return {
        "inert_bones_curios": [
            "movzbl 0x1c(%rax),%eax",
            "test %al,%al",
            "je 1230 <inert_bones_curios+0x30>",
            "mov -0x8(%rbp),%rax",
            "movb $0x2,0x1c(%rax)",
            "mov 0x10(%rax),%rax",
            "mov %rax,%rdi",
            "call 1200 <inert_bones_curios>",
            "mov (%rax),%rax",
        ],
        "resetobjs": ["call 1200 <inert_bones_curios>"],
        "savebones": ["call 1200 <inert_bones_curios>"] * 2,
        "restobjchn": [
            "mov $0x100,%edx",
            "mov %rbx,%rsi",
            "mov %r12d,%edi",
            "call 4400 <mread>",
            "cmpb $0x0,-0x44(%rbp)",
            "je 1560 <restobjchn+0x60>",
            "movzbl 0x1c(%rbx),%eax",
            "test %al,%al",
            "je 1560 <restobjchn+0x60>",
            "movb $0x2,0x1c(%rbx)",
        ],
    }


class ProfileTests(unittest.TestCase):
    def setUp(self):
        import native_build_calibration as calibration

        self.c = calibration
        temp = tempfile.TemporaryDirectory(prefix="synthetic-calibration-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.receipts = self.root / "receipts"
        for name in ("src", "dnethackdir", "include", "receipts"):
            (self.root / name).mkdir()
        for name in (
            "preflight.json",
            "1-manifest.json",
            "1-commands.json",
            "completion.json",
        ):
            (self.receipts / name).write_text("SYNTHETIC mocked identity verification")
        (self.root / "dnethackdir/dnethack").write_bytes(elf_fixture())
        (self.root / "src/dnethack").write_bytes(elf_fixture())
        for name in ("files.o", "bones.o", "restore.o"):
            (self.root / "src" / name).write_bytes(elf_fixture(elf_type=1))
        (self.root / "include/date.h").write_text(
            "\n".join(
                f"#define {name} 0x{value:x}UL"
                for name, value in zip(
                    (
                        "VERSION_NUMBER",
                        "VERSION_FEATURES",
                        "VERSION_SANITY1",
                        "VERSION_SANITY2",
                    ),
                    (11, 22, 33, 44),
                )
            )
        )
        (self.root / "include/chaos_curio.h").write_text(
            "#define CHAOS_CURIO_VERSION 1\n#define CHAOS_CURIO_SOURCE 4096\n"
        )
        self.inputs = SourceBuildInputs(
            self.root,
            self.root / "dnethackdir",
            1,
            "a" * 40,
            {"dnethack": hashlib.sha256(elf_fixture()).hexdigest()},
            {"receipt_dir": str(self.receipts), "profile": "system-gcc13-local"},
        )
        self.schema = schema_fixture()
        self.dwarf = dwarf_fixture(str(self.root))
        self.ops = bones_fixture()
        self.ops.update(
            compress=NOOP[:],
            uncompress=NOOP[:],
            store_version=[
                "call 4000 <bufoff>",
                "mov $0x20,%edx",
                "lea 0x111(%rip),%rcx # 3000 <version_data.0>",
                "mov %rcx,%rsi",
                "mov %eax,%edi",
                "call 4100 <bwrite>",
                "call 4200 <bufon>",
            ],
        )
        self.calls = []
        self.verify_calls = []
        self.baseline = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.addCleanup(patch.stopall)
        # Identity verifier has separate real unit coverage; this fake accepts
        # only the exact stable synthetic fixture inventory, never real receipts.
        patch.object(
            self.c, "verify_source_build", self.fake_verify, create=True
        ).start()
        patch.object(self.c, "_tool_lines", self.fake_tool, create=True).start()

    def fake_verify(self, receipts, root, revision, *, mode=1):
        self.verify_calls.append((Path(receipts), Path(root), revision, mode))
        for path, contents in self.baseline.items():
            if not path.exists() or path.read_bytes() != contents:
                raise self.c.CalibrationError("synthetic input hash mismatch")
        return copy.deepcopy(self.inputs)

    def fake_tool(self, tool, args, **kwargs):
        self.calls.append((tool, args))
        if args == ["--version"]:
            return iter(["GNU synthetic unit tool 0.0\n"])
        if tool == "/usr/bin/readelf":
            self.assertEqual(
                args,
                [
                    "--debug-dump=info",
                    "--wide",
                    str(self.inputs.tuple_dir / "dnethack"),
                ],
            )
            return iter(self.dwarf.splitlines(True))
        self.assertEqual(tool, "/usr/bin/objdump")
        self.assertEqual(args[:2], ["-d", "--no-show-raw-insn"])
        symbol = args[2].split("=", 1)[1]
        i = [
            "compress",
            "uncompress",
            "inert_bones_curios",
            "resetobjs",
            "savebones",
            "restobjchn",
            "store_version",
        ].index(symbol)
        return iter(
            disassembly(symbol, self.ops[symbol], 0x1000 + 256 * i).splitlines(True)
        )

    def test_profile_binds_observed_elf_layout_version_and_schema(self):
        original = copy.deepcopy(self.schema)
        profile = self.c.validate_native_profile(self.inputs, self.schema)
        self.assertEqual(profile.layout, original)
        self.assertEqual(self.schema, original)
        self.assertEqual(profile.elf_sha256, self.inputs.artifact_hashes["dnethack"])
        self.assertEqual(
            profile.evidence["dwarf"]["layouts"]["obj"]["fields"]["curio_tag"],
            {"offset": 28, "size": 1},
        )
        self.assertEqual(
            profile.evidence["bones"]["caller_counts"], {"resetobjs": 1, "savebones": 2}
        )
        self.assertEqual(len(profile.evidence["compression"]), 4)
        self.assertEqual(len(self.verify_calls), 2)
        self.assertTrue(
            all(
                call == (self.receipts, self.root, "a" * 40, 1)
                for call in self.verify_calls
            )
        )
        self.assertIn("not gameplay acceptance", profile.limits)
        self.assertNotIn("accepted", vars(profile))

    def test_wrong_expected_layout_version_or_semantic_fields_reject(self):
        for key, value in (
            ("you_size", 4999),
            ("version", 2),
            ("placed", 4),
            ("int_size", True),
            ("internal_compression", True),
            ("state", 99),
            ("save_header_values", {}),
        ):
            with self.subTest(key=key):
                bad = copy.deepcopy(self.schema)
                bad[key] = value
                with self.assertRaises(self.c.CalibrationError):
                    self.c.validate_native_profile(self.inputs, bad)

    def test_dictionary_mode_zero_and_wrong_hash_reject_before_tools(self):
        for value in (
            vars(self.inputs),
            SourceBuildInputs(
                self.root,
                self.inputs.tuple_dir,
                0,
                "a" * 40,
                self.inputs.artifact_hashes,
                self.inputs.metadata,
            ),
            SourceBuildInputs(
                self.root,
                self.inputs.tuple_dir,
                1,
                "a" * 40,
                {"dnethack": "0" * 64},
                self.inputs.metadata,
            ),
        ):
            with self.subTest(value=type(value)):
                with self.assertRaises(self.c.CalibrationError):
                    self.c.validate_native_profile(value, self.schema)
        self.assertEqual(self.calls, [])

    def test_actual_elf_version_must_agree_with_current_date_header(self):
        path = self.root / "include/date.h"
        path.write_text(path.read_text().replace("0xbUL", "0xcUL"))
        self.baseline[path] = path.read_bytes()  # Matching hash is not enough.
        with self.assertRaisesRegex(self.c.CalibrationError, "version"):
            self.c.validate_native_profile(self.inputs, self.schema)

    def test_actual_dwarf_missing_or_profile_changed_rejects(self):
        for text in ("", dwarf_fixture(str(self.root), producer="GNU C17 12.0")):
            self.dwarf = text
            with self.assertRaises(self.c.CalibrationError):
                self.c.validate_native_profile(self.inputs, self.schema)

    def test_compression_failure_has_no_alternate_backend(self):
        self.ops["compress"][3] = "mov %rdi,-0x10(%rbp)"
        with self.assertRaisesRegex(self.c.CalibrationError, "compression"):
            self.c.validate_native_profile(self.inputs, self.schema)
        self.assertTrue(
            all(
                tool in ("/usr/bin/readelf", "/usr/bin/objdump")
                for tool, _ in self.calls
            )
        )

    def test_missing_bones_tag_recursion_callers_restore_or_version_pointer_reject(
        self,
    ):
        mutations = [
            ("inert_bones_curios", "movb $0x2,0x1c(%rax)", "nop"),
            (
                "inert_bones_curios",
                "call 1200 <inert_bones_curios>",
                "call 9999 <inert_bones_curios>",
            ),
            ("inert_bones_curios", "mov 0x10(%rax),%rax", "mov 0x18(%rax),%rax"),
            ("inert_bones_curios", "mov (%rax),%rax", "nop"),
            ("resetobjs", "call 1200 <inert_bones_curios>", "nop"),
            (
                "savebones",
                "call 1200 <inert_bones_curios>",
                "call 9999 <inert_bones_curios>",
            ),
            ("restobjchn", "movb $0x2,0x1c(%rbx)", "nop"),
            ("restobjchn", "cmpb $0x0,-0x44(%rbp)", "nop"),
            (
                "store_version",
                "lea 0x111(%rip),%rcx # 3000 <version_data.0>",
                "lea 0x111(%rip),%rcx # 3008 <version_data.0>",
            ),
        ]
        original = copy.deepcopy(self.ops)
        for symbol, old, new in mutations:
            with self.subTest(symbol=symbol, old=old):
                self.ops = copy.deepcopy(original)
                self.ops[symbol] = [new if op == old else op for op in self.ops[symbol]]
                with self.assertRaises(self.c.CalibrationError):
                    self.c.validate_native_profile(self.inputs, self.schema)

    def test_missing_actual_helper_symbol_rejects_even_matching_hash_and_layout(self):
        data = elf_fixture().replace(b"inert_bones_curios", b"older_bones_curios")
        for name in ("src/dnethack", "dnethackdir/dnethack"):
            path = self.root / name
            path.write_bytes(data)
            self.baseline[path] = data
        self.inputs.artifact_hashes["dnethack"] = hashlib.sha256(data).hexdigest()
        with self.assertRaisesRegex(self.c.CalibrationError, "inert_bones_curios"):
            self.c.validate_native_profile(self.inputs, self.schema)

    def test_changed_elf_during_analysis_rejects(self):
        fake = self.fake_tool

        def mutate(tool, args, **kwargs):
            result = fake(tool, args, **kwargs)
            if "--debug-dump=info" in args:
                (self.inputs.tuple_dir / "dnethack").write_bytes(
                    elf_fixture(values=(0, 0, 0, 0))
                )
            return result

        with patch.object(self.c, "_tool_lines", mutate):
            with self.assertRaisesRegex(
                self.c.CalibrationError, "hash|changed|identity"
            ):
                self.c.validate_native_profile(self.inputs, self.schema)

    def test_actual_header_or_object_changed_after_measurement_rejects(self):
        for name in ("src/files.o", "include/chaos_curio.h"):
            with self.subTest(name=name):
                path = self.root / name
                original = path.read_bytes()
                fake = self.fake_tool

                def mutate(tool, args, **kwargs):
                    result = fake(tool, args, **kwargs)
                    if "--debug-dump=info" in args:
                        path.write_bytes(original + b"changed")
                    return result

                try:
                    with patch.object(self.c, "_tool_lines", mutate):
                        with self.assertRaises(self.c.CalibrationError):
                            self.c.validate_native_profile(self.inputs, self.schema)
                finally:
                    path.write_bytes(original)


class ToolBoundTests(unittest.TestCase):
    def test_read_only_tool_output_and_deadline_bounds(self):
        import native_build_calibration as c

        # Actual read-only tool self-description, never the inspected fixture.
        self.assertIn("GNU", "".join(c._tool_lines("/usr/bin/readelf", ["--version"])))
        with self.assertRaisesRegex(c.CalibrationError, "output bound"):
            list(c._tool_lines("/usr/bin/readelf", ["--version"], limit=1))
        with self.assertRaisesRegex(c.CalibrationError, "timeout"):
            list(c._tool_lines("/usr/bin/readelf", ["--version"], timeout=0))


if __name__ == "__main__":
    unittest.main()
