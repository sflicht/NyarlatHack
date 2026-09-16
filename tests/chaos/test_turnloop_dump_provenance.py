"""Synthetic unit fixtures only: no native/model evidence or gameplay."""

import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ProvenanceDumpTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(
            importlib.util.find_spec("turnloop_dump_provenance"),
            "separately labelled provenance comparator is missing",
        )
        self.api = importlib.import_module("turnloop_dump_provenance")
        self.left = self.fixture("off", "1", 0)
        self.right = self.fixture("on", "2", 1)

    def fixture(self, name, digit, mode):
        revision = digit * 40
        header = (
            f"Playing dNetHack v3.26.0 (dNAO git v3.21.3.1-1-g{revision[:9]}), "
            f"last build 2026-09-16 18:51:3{digit}."
        ).encode()
        source = b'#define VERSION_ID \\\n "' + header[len(b"Playing ") :] + b'"\n'
        artifacts = {
            key: (name + key).encode() for key in ("dnethack", "nhdat", "license")
        }
        manifest = json.dumps(
            {
                "build_name": name,
                "revision": revision,
                "mode": mode,
                "date_h_sha256": sha(source),
                "tuple_sha256": {key: sha(value) for key, value in artifacts.items()},
            },
            sort_keys=True,
        ).encode()
        kwargs = dict(
            build_name=name,
            expected_header=header,
            date_h=source,
            manifest=manifest,
            trusted_manifest_sha256=sha(manifest),
            artifacts=artifacts,
        )
        return kwargs

    def build(self, fixture):
        return self.api.validate_build(**fixture)

    def dump(self, fixture):
        return (
            b"Synthetic player\n"
            + fixture["expected_header"]
            + b"\n\nmap\x00\ntrailer\n"
        )

    def compare(self, left=None, right=None, left_build=None, right_build=None):
        return self.api.compare_provenance_dumps(
            {"1700000000": self.dump(self.left)} if left is None else left,
            {"1700000000": self.dump(self.right)} if right is None else right,
            reference_build=self.build(self.left) if left_build is None else left_build,
            candidate_build=self.build(self.right)
            if right_build is None
            else right_build,
        )

    def test_separately_labelled_result(self):
        result = self.compare()
        self.assertEqual(result["comparison"], "provenance-validated-dump-v1")
        self.assertTrue(result["equal"])
        self.assertEqual(
            result["builds"]["off"]["expected_header_hex"],
            self.left["expected_header"].hex(),
        )
        self.assertEqual(
            result["builds"]["on"]["date_h_sha256"], sha(self.right["date_h"])
        )

    def test_header_structure_and_every_other_byte(self):
        raw = self.dump(self.right)
        header = self.right["expected_header"]
        mutations = {
            "date": raw.replace(b"18:51:32", b"18:51:33"),
            "revision": raw.replace(b"g222222222", b"g333333333"),
            "absent": raw.replace(header + b"\n", b""),
            "duplicate": raw + header + b"\n",
            "extra foreign header": raw + self.left["expected_header"] + b"\n",
            "wrong position": header + b"\n" + raw.replace(header + b"\n", b""),
            "body byte": raw.replace(b"map", b"Map"),
            "line one": raw.replace(b"player", b"Player"),
            "header whitespace": raw.replace(header, header + b" "),
            "body whitespace": raw.replace(b"map", b"map "),
            "header CRLF": raw.replace(header + b"\n", header + b"\r\n"),
            "all CRLF": raw.replace(b"\n", b"\r\n"),
            "trailing newline": raw[:-1],
            "trailing data": raw + b"extra",
        }
        for name, value in mutations.items():
            with self.subTest(mutation=name), self.assertRaises(ValueError):
                self.compare(right={"1700000000": value})

    def test_file_sets_and_types(self):
        raw = self.dump(self.right)
        for files in (
            {},
            {"other": raw},
            {"1700000000": raw, "extra": raw},
            {"1700000000": raw.hex()},
            {"../1700000000": raw},
        ):
            with self.subTest(files=list(files)), self.assertRaises(ValueError):
                self.compare(right=files)
        with self.assertRaises(ValueError):
            self.compare(left={}, right={})

    def test_provenance_mutations_fail_closed(self):
        for field in ("dnethack", "nhdat", "license"):
            changed = dict(self.right, artifacts=dict(self.right["artifacts"]))
            changed["artifacts"][field] += b"!"
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.build(changed)
        for field, value in (
            ("build_name", "off"),
            ("expected_header", self.left["expected_header"]),
            ("date_h", self.right["date_h"] + b" "),
            ("trusted_manifest_sha256", "0" * 64),
            ("manifest", self.right["manifest"] + b" "),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.build(dict(self.right, **{field: value}))
        with self.assertRaises(ValueError):
            self.compare(right_build={"validated": True})
        with self.assertRaises(ValueError):
            self.compare(right_build=self.build(self.left))

    def test_manifest_source_structure_even_with_matching_hash(self):
        for field, value in (
            ("revision", "3" * 40),
            ("mode", True),
            ("tuple_sha256", {}),
            ("extra", 1),
        ):
            record = json.loads(self.right["manifest"])
            record[field] = value
            raw = json.dumps(record).encode()
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.build(
                    dict(self.right, manifest=raw, trusted_manifest_sha256=sha(raw))
                )
        for source in (b"", self.right["date_h"] * 2):
            record = json.loads(self.right["manifest"])
            record["date_h_sha256"] = sha(source)
            raw = json.dumps(record).encode()
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.build(
                    dict(
                        self.right,
                        date_h=source,
                        manifest=raw,
                        trusted_manifest_sha256=sha(raw),
                    )
                )

    def test_same_build_exact_and_strict_compatibility(self):
        from test_episode_turnloop_oracle import compare_runs

        raw = self.dump(self.left)
        self.compare(right={"1700000000": raw}, right_build=self.build(self.left))
        run = dict(
            inputs=["synthetic"],
            terminal=b"synthetic",
            xlog=b"synthetic",
            dumps={"1700000000": raw.hex()},
        )
        compare_runs(run, run)
        if sys.flags.optimize:
            return  # Old assert-based API is deliberately unchanged.
        with self.assertRaisesRegex(AssertionError, "dumps parity"):
            compare_runs(
                run, dict(run, dumps={"1700000000": self.dump(self.right).hex()})
            )

    def test_optimized_subprocess_runs_all_mutations(self):
        if os.environ.get("PROVENANCE_OPTIMIZED_CHILD") == "1":
            return
        env = dict(
            os.environ, PROVENANCE_OPTIMIZED_CHILD="1", PYTHONDONTWRITEBYTECODE="1"
        )
        for flag in ("-O", "-OO"):
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    flag,
                    "-m",
                    "unittest",
                    "test_turnloop_dump_provenance",
                    "-v",
                ],
                env=env,
                cwd=Path(__file__).resolve().parents[2],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
