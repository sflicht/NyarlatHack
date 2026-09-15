"""Synthetic schema fixtures only: no native receipts or model output."""

import json
import unittest

from chaos.episodes import parse_episode_event
from chaos.protocol import parse_event
from test_director import event


def obs(seq=3, operation="none", stage="enabled", root_seq=0, fact="none"):
    """Construct a synthetic observation, not an authority or delivery claim."""
    return event(
        seq,
        v=2,
        event="observation",
        detail="",
        phase="attempt" if stage == "started" else "result",
        vitals=dict(hp=7, hp_max=20, power=2, power_max=10),
        observation=dict(
            operation=operation, stage=stage, root_seq=root_seq, fact=fact
        ),
    )


class EpisodeParserTests(unittest.TestCase):
    def assert_bad(self, row):
        with self.assertRaises(ValueError):
            parse_episode_event(json.dumps(row))

    def test_all_legal_operation_stage_fact_combinations(self):
        facts = {
            "whistling": (
                "sound_high",
                "sound_shrill",
                "sound_normal",
                "sound_strange",
                "sound_humming",
            ),
            "fountain_drink": (
                "water_refreshed",
                "water_foul",
                "cannot_reach",
                "detection_presented",
            ),
        }
        rows = [obs()]
        for operation, notices in facts.items():
            rows.extend(
                (
                    obs(operation=operation, stage="started"),
                    obs(operation=operation, stage="completed", root_seq=1),
                )
            )
            rows.extend(
                obs(operation=operation, stage="notice", root_seq=1, fact=fact)
                for fact in notices
            )
        rows.append(obs(operation="fountain_drink", stage="blocked", root_seq=1))
        for row in rows:
            with self.subTest(payload=row["observation"]):
                self.assertEqual(parse_episode_event(json.dumps(row)), row)

    def test_exact_keys_at_every_schema_level(self):
        for section in (None, "observation", "vitals"):
            base = obs()
            target = base if section is None else base[section]
            for key in target:
                row = obs()
                del (row if section is None else row[section])[key]
                with self.subTest(section=section, missing=key):
                    self.assert_bad(row)
            for key in (
                "target_id",
                "coordinates",
                "name",
                "otyp",
                "monsters",
                "fate",
                "magic",
            ):
                row = obs()
                (row if section is None else row[section])[key] = "PRIVATE"
                with self.subTest(section=section, extra=key):
                    self.assert_bad(row)

    def test_integer_bounds_and_scalar_types(self):
        numeric = (
            "v",
            "seq",
            "turn",
            "safe",
            "sanity",
            "insight",
            "budget",
            "spent",
            "reserved",
            "last_id",
        )
        for section, keys in (
            (None, numeric),
            ("vitals", ("hp", "hp_max", "power", "power_max")),
            ("observation", ("root_seq",)),
        ):
            for key in keys:
                for bad in (
                    True,
                    False,
                    None,
                    "1",
                    1.0,
                    [],
                    {},
                    2147483648,
                    -2147483648,
                ):
                    row = obs()
                    (row if section is None else row[section])[key] = bad
                    with self.subTest(section=section, key=key, bad=bad):
                        self.assert_bad(row)
                if key != "power":
                    row = obs()
                    (row if section is None else row[section])[key] = -1
                    self.assert_bad(row)
        for key, bad in (
            ("seq", 0),
            ("sanity", 101),
            ("spent", 13),
            ("budget", 13),
            ("reserved", 13),
            ("reserved", 1),
        ):
            self.assert_bad(dict(obs(), **{key: bad}))
        row = obs(seq=2147483647)
        row.update(
            turn=2147483647,
            safe=2147483647,
            insight=2147483647,
            last_id=2147483647,
            sanity=0,
            spent=12,
            reserved=12,
            budget=12,
        )
        row["vitals"] = dict(
            hp=2147483647, hp_max=0, power=-2147483647, power_max=2147483647
        )
        self.assertEqual(parse_episode_event(json.dumps(row)), row)

    def test_wrong_envelope_and_payload_values(self):
        for key in ("event", "phase", "detail", "vitals", "observation"):
            for bad in (None, True, 0, [], {}, "PRIVATE"):
                with self.subTest(key=key, bad=bad):
                    self.assert_bad(dict(obs(), **{key: bad}))
        for version in (0, 3, "2", 2.0):
            self.assert_bad(dict(obs(), v=version))
        for key in ("operation", "stage", "fact"):
            for bad in (None, True, 0, [], {}, "PRIVATE"):
                row = obs()
                row["observation"][key] = bad
                with self.subTest(key=key, bad=bad):
                    self.assert_bad(row)

    def test_illegal_combinations_and_row_local_roots(self):
        operations = ("none", "whistling", "fountain_drink")
        stages = ("enabled", "started", "notice", "completed", "blocked")
        facts = (
            "none",
            "sound_high",
            "sound_shrill",
            "sound_normal",
            "sound_strange",
            "sound_humming",
            "water_refreshed",
            "water_foul",
            "cannot_reach",
            "detection_presented",
        )
        for operation in operations:
            for stage in stages:
                for fact in facts:
                    root = 0 if stage in ("enabled", "started") else 1
                    legal = (
                        (stage == "enabled" and operation == "none" and fact == "none")
                        or (
                            stage in ("started", "completed")
                            and operation != "none"
                            and fact == "none"
                        )
                        or (
                            stage == "blocked"
                            and operation == "fountain_drink"
                            and fact == "none"
                        )
                        or (
                            stage == "notice"
                            and (
                                (operation == "whistling" and fact.startswith("sound_"))
                                or (operation == "fountain_drink" and fact in facts[6:])
                            )
                        )
                    )
                    row = obs(
                        operation=operation, stage=stage, root_seq=root, fact=fact
                    )
                    with self.subTest(operation=operation, stage=stage, fact=fact):
                        if legal:
                            self.assertEqual(parse_episode_event(json.dumps(row)), row)
                            self.assert_bad(
                                dict(
                                    row,
                                    phase="result" if stage == "started" else "attempt",
                                )
                            )
                            for bad_root in (1, 3, 4) if root == 0 else (0, 3, 4):
                                bad = json.loads(json.dumps(row))
                                bad["observation"]["root_seq"] = bad_root
                                self.assert_bad(bad)
                        else:
                            self.assert_bad(row)

    def test_parsing_is_not_linkage_delivery_or_authority_verification(self):
        # No preceding root, session or enabled marker is supplied. Row validation
        # cannot establish same-turn/same-operation linkage or actual delivery.
        row = obs(
            seq=99,
            operation="whistling",
            stage="notice",
            root_seq=42,
            fact="sound_high",
        )
        row["turn"] = 0
        self.assertEqual(parse_episode_event(json.dumps(row)), row)

    def test_json_encoding_duplicates_nonfinite_and_line_bounds(self):
        raw = json.dumps(obs())
        malformed = [
            raw[:-1],
            raw + "{}",
            "[]",
            "null",
            "42",
            b"\xff",
            raw.encode()[:-1] + b"\xff}",
            raw + " " * 4096,
        ]
        for key, value in (("v", "2"), ("hp", "7"), ("stage", '"enabled"')):
            marker = json.dumps(key) + ": " + value
            malformed.append(raw.replace(marker, marker + ", " + marker))
        for literal in ("NaN", "Infinity", "-Infinity", "1e999"):
            malformed.append(raw.replace('"sanity": 100', '"sanity": ' + literal))
        for item in malformed:
            with self.subTest(raw=repr(item)[:100]), self.assertRaises(ValueError):
                parse_episode_event(item)
        for item in (None, 2, [], {}, memoryview(b"{}")):
            with self.subTest(raw=repr(item)), self.assertRaises(ValueError):
                parse_episode_event(item)
        padded = raw + " " * (4096 - len(raw))
        self.assertEqual(parse_episode_event(padded), obs())
        self.assertEqual(parse_episode_event(padded.encode()), obs())
        with self.assertRaises(ValueError):
            parse_episode_event(padded + " ")
        with self.assertRaises(ValueError):
            parse_episode_event(padded.encode("utf-16"))

    def test_malformed_legacy_schema_raises_value_error(self):
        missing_event = event()
        del missing_event["event"]
        for row in (missing_event, event(event=[]), event(seq=True), event(v=1.0)):
            with self.subTest(row=row):
                self.assert_bad(row)

    def test_encoding_and_nested_json_failures(self):
        raw = json.dumps(obs())
        for malformed in (
            raw.replace('"fact": "none"', '"fact": "\\ud800"'),
            raw.replace('"root_seq": 0', '"root_seq": NaN'),
            raw.replace('"power": 2', '"power": -Infinity'),
            raw[:-1] + ', "extra": {"deep": {"x": 1, "x": 2}}}',
            raw[:-1] + ', "extra": {"deep": NaN}}',
            "[" * 2000 + "0" + "]" * 2000,
        ):
            with self.subTest(raw=repr(malformed)[:100]), self.assertRaises(ValueError):
                parse_episode_event(malformed)
        self.assertEqual(parse_episode_event(bytearray(raw.encode())), obs())

    def test_enabled_marker_is_accepted(self):
        row = obs()
        self.assertEqual(parse_episode_event(json.dumps(row).encode()), row)

    def test_v1_delegation_preserves_older_records_and_unknown_fields(self):
        for row in (
            event(),
            event(private={"secret": "é"}),
            event(vitals=obs()["vitals"]),
        ):
            raw = json.dumps(row, ensure_ascii=False)
            self.assertEqual(parse_episode_event(raw), parse_event(raw))
        # Legacy str cap counts characters, not UTF-8 bytes: do not tighten it.
        raw = json.dumps(event(unknown="é" * 2000), ensure_ascii=False)
        self.assertGreater(len(raw.encode()), 4096)
        self.assertEqual(parse_episode_event(raw), parse_event(raw))
