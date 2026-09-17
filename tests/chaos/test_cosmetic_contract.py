"""Independent current-policy metadata assertions; no native compilation."""

import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "generator", ROOT / "scripts/generate_protocol_contract.py"
)
assert spec is not None and spec.loader is not None
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class CosmeticContract(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "chaos/protocol_contract.json").read_text())

    def test_current_and_frozen_legacy(self):
        d = self.data
        self.assertEqual(d["versions"], dict(request=1, event=3, state=2))
        self.assertEqual(d["observations"]["wire_version"], 4)
        self.assertEqual(d["cosmetic"], dict(limit=3, spacing=50, mask=7, policy=2))
        self.assertEqual(
            [(r["cost"], r["cosmetic_cost"]) for r in d["mutations"]],
            [(0, 1), (4, 0), (3, 0)],
        )
        self.assertEqual(d["legacy"]["versions"], dict(request=1, event=1, state=1))
        self.assertEqual([r["cost"] for r in d["legacy"]["mutations"]], [1, 4, 3])
        self.assertEqual(len(d["legacy"]["results"]), 10)
        self.assertEqual([r["id"] for r in d["results"][-3:]], [10, 11, 12])
        self.assertFalse(d["results"][9]["ack"])
        self.assertEqual(generator.generate(ROOT, check=True), 0)

    def test_complete_original_metadata(self):
        import subprocess

        baseline = json.loads(
            subprocess.check_output(
                [
                    "git",
                    "show",
                    "c00029de0ef54bf89dc0d283b8e4f0fc365beb11:chaos/protocol_contract.json",
                ],
                cwd=ROOT,
            )
        )
        self.assertEqual(
            self.data["legacy"], {k: baseline[k] for k in self.data["legacy"]}
        )
        for key in (
            "limits",
            "ack_number_bounds",
            "request_fields",
            "vitals",
            "events",
            "phases",
            "ack_statuses",
            "telegraphs",
            "ambient_messages",
            "budget",
            "non_effect_spenders",
            "journal_status",
        ):
            self.assertEqual(self.data[key], baseline[key])

    def test_legacy_metadata_is_not_mutable(self):
        for section, value in (
            ("legacy", None),
            ("legacy", {}),
            ("limits", dict(self.data["limits"], event_input_cap=9999)),
        ):
            d = copy.deepcopy(self.data)
            d[section] = value
            with (
                self.subTest(section=section, value=value),
                self.assertRaises(ValueError),
            ):
                generator.validate(d)

        # Change every leaf independently, including types; no unchecked subtree.
        def leaves(value, path=()):
            if isinstance(value, dict):
                for k, v in value.items():
                    yield from leaves(v, path + (k,))
            elif isinstance(value, list):
                for k, v in enumerate(value):
                    yield from leaves(v, path + (k,))
            else:
                yield path

        for path in leaves(self.data["legacy"]):
            d = copy.deepcopy(self.data)
            node = d["legacy"]
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = "altered" if node[path[-1]] is None else None
            with self.subTest(path=path), self.assertRaises(ValueError):
                generator.validate(d)
        d = copy.deepcopy(self.data)
        d["legacy"]["mutations"][0]["unknown"] = 1
        with self.assertRaises(ValueError):
            generator.validate(d)

    def test_free_fourth_row_rejected(self):
        d = copy.deepcopy(self.data)
        d["mutations"].append(
            dict(
                d["mutations"][0],
                symbol="CHAOS_TEST_ONLY",
                id=3,
                name="test_only",
                value=[1, 1],
            )
        )
        with self.assertRaises(ValueError):
            generator.validate(d)

    def test_only_bounded_ambient_can_be_free(self):
        for index, field, value in [
            (1, "cost", 0),
            (2, "cost", 0),
            (0, "cosmetic_cost", 0),
            (1, "cosmetic_cost", 1),
            (0, "value", [1, 4]),
            (0, "persistent", True),
        ]:
            with self.subTest(index=index, field=field):
                d = copy.deepcopy(self.data)
                d["mutations"][index][field] = value
                with self.assertRaises(ValueError):
                    generator.validate(d)
