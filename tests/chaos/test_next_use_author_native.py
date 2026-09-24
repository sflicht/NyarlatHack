"""ENGINE-UNIT: real C author/parser/Lua load, not native effects/admission."""

import ctypes
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from chaos import next_use_author as author
import test_next_use_offline_author as fixtures

ROOT = Path(__file__).resolve().parents[2]


class NativeAuthorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build = tempfile.TemporaryDirectory(prefix="nyarl-author-native-")
        cls.addClassCleanup(build.cleanup)
        library = Path(build.name) / "author.so"
        flags = subprocess.check_output(
            ["/usr/bin/pkg-config", "--cflags", "--libs", "lua5.4"], text=True
        ).split()
        result = subprocess.run(
            [
                "cc",
                "-shared",
                "-fPIC",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-Wno-misleading-indentation",
                "-std=c99",
                "-Wl,-z,defs",
                "-I" + str(ROOT / "include"),
                str(ROOT / "src/chaos_next_use.c"),
                str(ROOT / "src/chaos_lua.c"),
                str(ROOT / "tests/chaos/next_use_author_native.c"),
                *flags,
                "-lm",
                "-o",
                str(library),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode:
            raise RuntimeError(result.stderr)
        cls.validator = author.NativeAuthorValidator(library)
        cls.library = ctypes.CDLL(str(library))
        cls.parse_envelope = cls.library.author_fixture_parse_envelope
        cls.parse_envelope.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
        cls.parse_envelope.restype = ctypes.c_int

    def run_directory(self):
        helper = fixtures.OfflineAuthorTests()
        self.addCleanup(helper.doCleanups)
        return helper.setup_run()

    def test_ctypes_layout_matches_compiled_c(self):
        for name, expected in (
            ("author_fixture_size", ctypes.sizeof(author._Author)),
            ("author_fixture_length_offset", author._Author.source_length.offset),
            ("author_fixture_source_offset", author._Author.source.offset),
        ):
            native = getattr(self.library, name)
            native.argtypes = []
            native.restype = ctypes.c_size_t
            self.assertEqual(native(), expected, name)

    def test_two_exact_sources_reach_real_parser_load_and_envelope_parser(self):
        for source in fixtures.fixture_sources():
            with self.subTest(digest=hashlib.sha256(source).hexdigest()):
                root = self.run_directory()
                response = fixtures.response(source)
                transport = author.FakeAuthorTransport(response)
                receipt = author.author_offline(
                    root, transport=transport, validator=self.validator
                )
                raw = (root / "next_use-envelope.json").read_bytes()
                envelope = json.loads(raw)
                self.assertEqual(self.parse_envelope(raw, len(raw)), 0)
                self.assertEqual(envelope["source"].encode(), source)
                self.assertEqual(
                    receipt["source_sha256"], hashlib.sha256(source).hexdigest()
                )
                self.assertEqual(
                    (root / "next_use-author-response.json").read_bytes(), response
                )
                self.assertEqual(receipt["validation"], "native_parser_and_load")
                self.assertEqual(receipt["native_admission"], "unverified")
                self.assertEqual(len(transport.calls), 1)

    def test_native_rejections_do_not_publish_or_retry(self):
        valid = fixtures.fixture_sources()[0]
        cases = [
            b"```json\n" + fixtures.response(valid) + b"```",
            b'{"next_use_author_v":2,"source":"return {}","cost":0}',
            fixtures.response(b"return {}"),
            fixtures.response(b"while true do end"),
            fixtures.response(b"return {on_action=function(c) return {} end, extra=1}"),
            fixtures.response(b"a" * 4097),
        ]
        for response in cases:
            with self.subTest(response=response[:60]):
                root = self.run_directory()
                transport = author.FakeAuthorTransport(response)
                with self.assertRaises(ValueError):
                    author.author_offline(
                        root, transport=transport, validator=self.validator
                    )
                self.assertFalse((root / "next_use-envelope.json").exists())
                receipt = json.loads(
                    (root / "next_use-author-receipt.json").read_bytes()
                )
                self.assertEqual(receipt["status"], "rejected_not_admitted")
                with self.assertRaises(ValueError):
                    author.author_offline(
                        root, transport=transport, validator=self.validator
                    )
                self.assertEqual(len(transport.calls), 1)

    def test_native_abstention_does_not_publish(self):
        root = self.run_directory()
        transport = author.FakeAuthorTransport(
            b'{"next_use_author_v":2,"abstain":true}'
        )
        receipt = author.author_offline(
            root, transport=transport, validator=self.validator
        )
        self.assertEqual(receipt["status"], "abstained_not_admitted")
        self.assertFalse((root / "next_use-envelope.json").exists())
