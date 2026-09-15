"""Synthetic schema fixtures only: no native receipts or model output."""

import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from unittest.mock import patch

from chaos import episodes
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


def wire(*rows):
    return b"".join(json.dumps(row).encode() + b"\n" for row in rows)


def session(seq=1, detail="new", **kw):
    return event(seq, **dict(dict(event="session", detail=detail, safe=0), **kw))


def enabled(seq=1):
    return dict(obs(seq), safe=0)


def action(rows, operation="whistling", fact="sound_high", terminal="completed"):
    """Append one synthetic action and return its exact expected evidence."""
    root = len(rows) + 1
    rows.append(obs(root, operation, "started"))
    notice = None
    if fact is not None:
        notice = len(rows) + 1
        rows.append(obs(notice, operation, "notice", root, fact))
    end = None
    if terminal is not None:
        end = len(rows) + 1
        rows.append(obs(end, operation, terminal, root))
    return dict(root_seq=root, notice_seq=notice, end_seq=end, fact=fact)


class EpisodeSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run_dir = Path(self.temp.name)
        self.log = self.run_dir / "events.jsonl"
        rows = [enabled(), session(2, private="SECRET")]
        action(rows)
        self.raw = wire(*rows)
        self.log.write_bytes(self.raw)
        self.log.chmod(0o600)

    def snapshot(self, path=None, **kw):
        self.assertTrue(callable(getattr(episodes, "snapshot_episodes", None)))
        return episodes.snapshot_episodes(self.run_dir if path is None else path, **kw)

    def test_checkpoint_append_projects_only_prefix(self):
        original = self.snapshot()
        checkpoint = copy.deepcopy(original[1])
        for suffix in (wire(event(6)), b'{"partial":', b"{}\n"):
            self.log.write_bytes(self.raw)
            with self.log.open("ab") as stream:
                stream.write(suffix)
            result = self.snapshot(checkpoint=checkpoint)
            self.assertEqual(result, original)
            self.assertEqual(checkpoint, original[1])
            self.assertIsNot(result[1], checkpoint)
            self.assertIsNot(result[1]["directory"], checkpoint["directory"])
            self.assertIsNot(result[1]["event"], checkpoint["event"])
            self.assertIsNot(
                result[1]["event"]["identity"], checkpoint["event"]["identity"]
            )
            if suffix != wire(event(6)):
                with self.assertRaises(ValueError):
                    self.snapshot()

    def test_checkpoint_rejects_changed_source(self):
        proof = self.snapshot()[1]
        for raw in (self.raw.replace(b"SECRET", b"PUBLIC"), self.raw[:-1]):
            self.log.write_bytes(raw)
            with self.assertRaises(ValueError):
                self.snapshot(checkpoint=proof)
        self.log.write_bytes(self.raw)
        saved = self.run_dir / "old"
        self.log.rename(saved)
        self.log.write_bytes(self.raw)
        self.log.chmod(0o600)
        with self.assertRaises(ValueError):
            self.snapshot(checkpoint=proof)
        with tempfile.TemporaryDirectory() as other:
            target = Path(other) / "events.jsonl"
            target.write_bytes(self.raw)
            target.chmod(0o600)
            with self.assertRaises(ValueError):
                self.snapshot(other, checkpoint=proof)

    def test_checkpoint_schema_validated_before_io(self):
        good = self.snapshot()[1]
        malformed = [False, True, [], 1, "proof", {}]
        for section in (None, "event"):
            target = good if section is None else good[section]
            for key in (*target, "extra"):
                bad = copy.deepcopy(good)
                obj = bad if section is None else bad[section]
                if key == "extra":
                    obj[key] = 1
                else:
                    del obj[key]
                malformed.append(bad)
        for key, values in (
            (
                "length",
                [True, False, 0, -1, 1.0, "1", None, episodes.DEFAULT_BYTES + 1],
            ),
            ("sha256", [None, 1, "a" * 63, "A" * 64, "g" * 64, "a" * 64 + "\n"]),
            (
                "identity",
                [
                    None,
                    {},
                    (),
                    [1],
                    [1, 2, 3],
                    [True, 2],
                    [1, False],
                    [-1, 2],
                    [1, 2.0],
                ],
            ),
        ):
            for value in values:
                bad = copy.deepcopy(good)
                bad["event"][key] = value
                malformed.append(bad)
                if key == "identity":
                    bad = copy.deepcopy(good)
                    bad["directory"] = value
                    malformed.append(bad)
        for value in (None, [], True):
            malformed.append(dict(good, event=value))
        for bad in malformed:
            with (
                self.subTest(checkpoint=bad),
                patch.object(
                    episodes.store, "_directory", wraps=episodes.store._directory
                ) as opening,
            ):
                with self.assertRaises(ValueError):
                    self.snapshot(checkpoint=bad)
                opening.assert_not_called()
        # Host identity integers have no game MAX_INT ceiling; mismatches get
        # as far as actual source verification, not schema rejection.
        large = copy.deepcopy(good)
        large["directory"] = [2**70, 2**71]
        with patch.object(
            episodes.store, "_directory", wraps=episodes.store._directory
        ) as opening:
            with self.assertRaises(ValueError):
                self.snapshot(checkpoint=large)
            opening.assert_called()

    def test_rechecks_actual_resources_after_projection(self):
        project = episodes.project_episodes
        for mutation in (
            "directory",
            "file",
            "rewrite",
            "truncate",
            "file_mode",
            "directory_mode",
            "hardlink",
        ):
            for checkpointed in (False, True):
                with (
                    self.subTest(mutation=mutation, checkpointed=checkpointed),
                    tempfile.TemporaryDirectory() as root,
                ):
                    run = Path(root) / "run"
                    run.mkdir(mode=0o700)
                    log = run / "events.jsonl"
                    log.write_bytes(self.raw)
                    log.chmod(0o600)
                    proof = self.snapshot(run)[1] if checkpointed else None

                    def changed(raw):
                        if mutation == "directory":
                            run.rename(Path(root) / "old")
                            run.mkdir(mode=0o700)
                            log.write_bytes(self.raw)
                            log.chmod(0o600)
                        elif mutation == "file":
                            log.rename(run / "old")
                            log.write_bytes(self.raw)
                            log.chmod(0o600)
                        elif mutation == "rewrite":
                            log.write_bytes(self.raw.replace(b"SECRET", b"PUBLIC"))
                        elif mutation == "truncate":
                            log.write_bytes(self.raw[:-1])
                        elif mutation == "file_mode":
                            log.chmod(0o640)
                        elif mutation == "directory_mode":
                            run.chmod(0o750)
                        else:
                            os.link(log, run / "link")
                        return project(raw)

                    with patch.object(
                        episodes, "project_episodes", side_effect=changed
                    ):
                        with self.assertRaises((ValueError, OSError)):
                            self.snapshot(run, checkpoint=proof)

    def test_append_during_projection_keeps_consumed_prefix(self):
        expected = self.snapshot()
        project = episodes.project_episodes

        def appended(raw):
            with self.log.open("ab") as stream:
                stream.write(b'{"partial":')
            return project(raw)

        with patch.object(episodes, "project_episodes", side_effect=appended):
            self.assertEqual(self.snapshot(), expected)

    def test_private_resource_guards(self):
        for target, mode in ((self.log, 0o644), (self.run_dir, 0o755)):
            original = target.stat().st_mode & 0o777
            target.chmod(mode)
            try:
                with self.assertRaises((ValueError, OSError)):
                    self.snapshot()
            finally:
                target.chmod(original)
        with tempfile.TemporaryDirectory() as root:
            link = Path(root) / "alias"
            link.symlink_to(self.run_dir, target_is_directory=True)
            with self.assertRaises((ValueError, OSError)):
                self.snapshot(link)
            child = self.run_dir / "child"
            child.mkdir(mode=0o700)
            with self.assertRaises((ValueError, OSError)):
                self.snapshot(link / "child")
        saved = self.run_dir / "saved"
        self.log.rename(saved)
        self.log.symlink_to(saved)
        with self.assertRaises((ValueError, OSError)):
            self.snapshot()
        self.log.unlink()
        os.link(saved, self.log)
        with self.assertRaises(ValueError):
            self.snapshot()
        self.log.unlink()
        self.log.mkdir(mode=0o700)
        with self.assertRaises((ValueError, OSError)):
            self.snapshot()
        self.log.rmdir()
        os.mkfifo(self.log, 0o600)
        with self.assertRaises(ValueError):
            self.snapshot()

    def test_foreign_ownership(self):
        for target in (self.run_dir, self.log):
            try:
                os.chown(target, os.getuid() + 1, -1)
            except PermissionError:
                self.skipTest("foreign ownership requires chown privilege")
            try:
                with self.assertRaises((ValueError, OSError)):
                    self.snapshot()
            finally:
                os.chown(target, os.getuid(), -1)

    def test_missing_resources_not_created_and_failures_do_not_leak(self):
        self.log.unlink()
        before = len(os.listdir("/proc/self/fd"))
        for _ in range(20):
            with self.assertRaises(FileNotFoundError):
                self.snapshot()
        self.assertEqual(len(os.listdir("/proc/self/fd")), before)
        self.assertEqual(list(self.run_dir.iterdir()), [])
        missing = self.run_dir / "missing"
        with self.assertRaises(FileNotFoundError):
            self.snapshot(missing)
        self.assertFalse(missing.exists())

    def test_director_caps_apply_to_full_file_and_consumed_events(self):
        proof = self.snapshot()[1]
        # Sparse overcap file: bounded disk/memory, including short checkpoints.
        with self.log.open("r+b") as stream:
            stream.truncate(episodes.DEFAULT_BYTES + 1)
        for checkpoint in (None, proof):
            with self.assertRaises(ValueError):
                self.snapshot(checkpoint=checkpoint)
        self.log.write_bytes(b"{}\n" * (episodes.DEFAULT_EVENTS + 1))
        with self.assertRaisesRegex(ValueError, "history cap"):
            self.snapshot()
        # Above continuity's unrelated event/byte ceilings, below director caps.
        raw = wire(session()) + b"".join(wire(event(i)) for i in range(2, 6002))
        self.assertGreater(len(raw), episodes.continuity.MAX_EVENT_BYTES)
        self.log.write_bytes(raw)
        self.assertEqual(self.snapshot()[0], episodes.project_episodes(raw))

    def test_fresh_exact_proof_and_public_redaction(self):
        before = self.log.stat()
        result = self.snapshot()
        self.assertIs(type(result), tuple)
        public, proof = result
        directory = self.run_dir.stat()
        self.assertEqual(public, episodes.project_episodes(self.raw))
        self.assertEqual(
            proof,
            {
                "directory": [directory.st_dev, directory.st_ino],
                "event": {
                    "identity": [before.st_dev, before.st_ino],
                    "length": len(self.raw),
                    "sha256": hashlib.sha256(self.raw).hexdigest(),
                },
            },
        )
        self.assertIs(type(proof["event"]["length"]), int)
        for identity in (proof["directory"], proof["event"]["identity"]):
            self.assertIs(type(identity), list)
            self.assertTrue(all(type(v) is int for v in identity))
        for secret in ("SECRET", str(self.run_dir), "directory", "identity", "sha256"):
            self.assertNotIn(secret, json.dumps(public))
        self.assertEqual(self.log.read_bytes(), self.raw)
        self.assertEqual(self.log.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(list(self.run_dir.iterdir()), [self.log])


class EpisodeProjectionTests(unittest.TestCase):
    def project(self, *rows):
        self.assertTrue(callable(getattr(episodes, "project_episodes", None)))
        return episodes.project_episodes(wire(*rows))

    def test_complete_history_chronology(self):
        valid = (session(), event(2), event(3, event="session", detail="restore"))
        self.project(*valid)
        self.project(enabled(), session(2), enabled(3), session(4, "restore"))
        bad_histories = [
            (),
            (event(),),
            (session(detail="restore"),),
            (session(phase="attempt"),),
            (session(2),),
            (session(), session(2)),
            (session(), event(3)),
            (session(), event(2), event(2)),
            (session(), event(3), event(2)),
            (enabled(),),
            (enabled(), event(2)),
            (enabled(), enabled(2), session(3)),
            (session(), event(2, event="death"), event(3)),
            (session(), event(2, event="death"), enabled(3)),
            (session(), obs(2, "whistling", "started")),
            (
                enabled(),
                session(2),
                session(3, "restore"),
                obs(4, "whistling", "started"),
            ),
        ]
        for key in ("safe", "spent", "reserved", "last_id"):
            bad_histories.append((session(**{key: 1}),))
            bad_histories.append((dict(enabled(), **{key: 1}), session(2)))
        for key in ("safe", "turn", "spent", "last_id"):
            bad_histories.append((session(), event(2, **{key: 11}), event(3)))
        for rows in bad_histories:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.project(*rows)

    def test_raw_caps_and_malformed_history(self):
        from chaos.director import DEFAULT_BYTES, DEFAULT_EVENTS

        for raw in (
            b"",
            b"\n",
            wire(session())[:-1],
            b"\xff\n",
            b"{}\n",
            wire(session()) + b"{}",
            b" " * DEFAULT_BYTES + b"\n",
            b"{}\n" * (DEFAULT_EVENTS + 1),
            "{}\n",
            None,
            wire(session(v=3)),
            wire(session()) + b"\n",
        ):
            with self.subTest(raw=repr(raw)[:50]), self.assertRaises(ValueError):
                episodes.project_episodes(raw)

    def test_caps_before_parse_and_valid_event_ceiling(self):
        from chaos.director import DEFAULT_BYTES, DEFAULT_EVENTS

        for raw in (b" " * DEFAULT_BYTES + b"\n", b"{}\n" * (DEFAULT_EVENTS + 1)):
            with patch.object(episodes, "parse_episode_event") as parser:
                with self.assertRaisesRegex(ValueError, "history cap"):
                    episodes.project_episodes(raw)
                parser.assert_not_called()
        raw = wire(session()) + b"".join(
            wire(event(i)) for i in range(2, DEFAULT_EVENTS + 1)
        )
        self.assertEqual(episodes.project_episodes(raw)["episodes"], [])
        with self.assertRaises(ValueError):
            episodes.project_episodes(raw + wire(event(DEFAULT_EVENTS + 1)))

    def test_full_validation_survives_window_eviction_and_restore(self):
        rows = [enabled(), session(2)]
        for _ in range(36):
            action(rows)
        rows.extend(
            [
                dict(enabled(len(rows) + 1), safe=1),
                session(len(rows) + 2, "restore", safe=1),
            ]
        )
        self.assertEqual(self.project(*rows)["episodes"], [])
        rows[3] = obs(4, "whistling", "notice", 2, "sound_high")
        with self.assertRaises(ValueError):
            self.project(*rows)

    def test_all_delivered_facts_project_without_identity_claims(self):
        for operation, facts in (
            (
                "whistling",
                (
                    "sound_high",
                    "sound_shrill",
                    "sound_normal",
                    "sound_strange",
                    "sound_humming",
                ),
            ),
            (
                "fountain_drink",
                ("water_refreshed", "water_foul", "detection_presented"),
            ),
        ):
            for fact in facts:
                rows = [enabled(), session(2)]
                evidence = action(rows, operation, fact)
                self.assertEqual(
                    self.project(*rows)["episodes"],
                    [
                        dict(
                            operation=operation,
                            count=1,
                            saturated=False,
                            evidence=[evidence],
                        )
                    ],
                )

    def test_active_root_linkage(self):
        root = obs(3, "whistling", "started")
        notice = obs(4, "whistling", "notice", 3, "sound_high")
        end = obs(5, "whistling", "completed", 3)
        self.project(enabled(), session(2), root, notice, end)
        self.project(enabled(), session(2), root)  # unfinished is legal
        bad = [
            [notice],
            [root, dict(notice, turn=11)],
            [root, obs(4, "fountain_drink", "notice", 3, "water_foul")],
            [root, notice, dict(notice, seq=5)],
            [root, obs(4, "whistling", "completed", 3), dict(notice, seq=5)],
            [root, notice, end, dict(end, seq=6)],
            [
                root,
                obs(4, "whistling", "started"),
                dict(end, observation=dict(end["observation"], root_seq=3)),
            ],
            [root, obs(4, "whistling", "notice", 2, "sound_high")],
            [root, obs(4, "whistling", "notice", 5, "sound_high")],
        ]
        for boundary in ("level_enter", "level_leave", "death"):
            bad.append([root, event(4, event=boundary), end])
        bad.append(
            [
                root,
                dict(enabled(4), safe=1),
                session(5, "restore", safe=1),
                dict(end, seq=6),
            ]
        )
        bad.append(
            [
                obs(3, "fountain_drink", "started"),
                obs(4, "fountain_drink", "notice", 3, "cannot_reach"),
                obs(5, "fountain_drink", "completed", 3),
            ]
        )
        for rows in bad:
            # Keep chronology valid for the orphan case so linkage is tested.
            rows = [dict(r, seq=i) for i, r in enumerate(rows, 3)]
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.project(enabled(), session(2), *rows)

    def test_completed_evidence_and_incomplete_boundaries(self):
        root = obs(3, "whistling", "started")
        notice = obs(4, "whistling", "notice", 3, "sound_high")
        end = obs(6, "whistling", "completed", 3)
        result = self.project(
            enabled(),
            session(2),
            root,
            notice,
            event(5, private={"target_id": "SECRET"}),
            end,
        )
        self.assertEqual(
            result["episodes"],
            [
                dict(
                    operation="whistling",
                    count=1,
                    saturated=False,
                    evidence=[
                        dict(root_seq=3, notice_seq=4, end_seq=6, fact="sound_high")
                    ],
                )
            ],
        )
        self.assertNotIn("SECRET", json.dumps(result))
        for suffix in (
            [],
            [notice],
            [notice, event(5, event="level_enter")],
            [notice, event(5, event="level_leave")],
            [notice, event(5, event="death")],
            [notice, obs(5, "whistling", "started")],
        ):
            output = self.project(enabled(), session(2), root, *suffix)
            self.assertEqual(output["episodes"], [])
            expected = (
                2
                if suffix
                and suffix[-1]["v"] == 2
                and suffix[-1]["observation"]["stage"] == "started"
                else 1
            )
            self.assertEqual(
                output["coverage"]["incomplete"], dict(count=expected, saturated=False)
            )

    def test_blocked_and_completed_without_notice(self):
        for notice in (False, True):
            rows = [enabled(), session(2), obs(3, "fountain_drink", "started")]
            if notice:
                rows.append(obs(4, "fountain_drink", "notice", 3, "cannot_reach"))
            rows.append(obs(len(rows) + 1, "fountain_drink", "blocked", 3))
            result = self.project(*rows)
            self.assertEqual(result["episodes"], [])
            self.assertEqual(
                result["coverage"]["blocked"], dict(count=1, saturated=False)
            )
            self.assertEqual(result["coverage"]["incomplete"]["count"], 0)
        result = self.project(
            enabled(),
            session(2),
            obs(3, "whistling", "started"),
            obs(4, "whistling", "completed", 3),
        )
        self.assertEqual(result["episodes"], [])
        self.assertEqual(
            result["coverage"]["completed_without_notice"],
            dict(count=1, saturated=False),
        )

    def test_saturation_and_first_two_latest(self):
        for count in (1, 2, 3, 4, 8):
            rows = [enabled(), session(2)]
            expected = [
                action(rows, fact="sound_high" if i % 2 else "sound_shrill")
                for i in range(count)
            ]
            result = self.project(*rows)["episodes"][0]
            self.assertEqual(result["count"], min(3, count))
            self.assertEqual(result["saturated"], count > 3)
            self.assertEqual(
                result["evidence"],
                expected if count <= 3 else expected[:2] + expected[-1:],
            )
        for terminal, key in (
            (None, "incomplete"),
            ("blocked", "blocked"),
            ("completed", "completed_without_notice"),
        ):
            for count in (3, 4):
                rows = [enabled(), session(2)]
                for _ in range(count):
                    action(rows, "fountain_drink", None, terminal)
                self.assertEqual(
                    self.project(*rows)["coverage"][key],
                    dict(count=3, saturated=count > 3),
                )

    def test_window_eviction_and_restore_reset(self):
        for count in (32, 33, 35, 36):
            rows = [enabled(), session(2)]
            first = action(rows, fact=None, terminal=None)
            evidence = [action(rows) for _ in range(count - 1)]
            result = self.project(*rows)
            self.assertEqual(
                result["coverage"]["omitted_roots"],
                dict(count=min(3, count - 32), saturated=count > 35),
            )
            self.assertEqual(
                result["coverage"]["incomplete"]["count"], int(count == 32)
            )
            retained = evidence[max(0, count - 33) :]
            self.assertEqual(
                result["episodes"][0]["evidence"], retained[:2] + retained[-1:]
            )
            self.assertNotIn(first, result["episodes"][0]["evidence"])
            for opted in (False, True):
                restored = list(rows)
                if opted:
                    restored.append(dict(enabled(len(restored) + 1), safe=1))
                restored.append(session(len(restored) + 1, "restore", safe=1))
                output = self.project(*restored)
                self.assertEqual(output["episodes"], [])
                self.assertTrue(
                    all(
                        v == dict(count=0, saturated=False)
                        for v in output["coverage"].values()
                    )
                )
                if opted:
                    new = action(restored, "fountain_drink", "water_foul")
                    self.assertEqual(
                        self.project(*restored)["episodes"][0]["evidence"], [new]
                    )
        # A legacy process can restore with observations enabled, no invented save row.
        rows = [session(), dict(enabled(2), safe=0), session(3, "restore")]
        new = action(rows)
        self.assertEqual(self.project(*rows)["episodes"][0]["evidence"], [new])

    def test_canonical_bound_determinism_and_overflow_guard(self):
        # A conservative schema bound uses MAX_INT references, larger than the
        # 50,000-row history can actually produce; no contract cap is relaxed.
        from chaos.protocol import MAX_INT

        upper = self.project(session())
        upper["episodes"] = [
            dict(
                operation=operation,
                count=3,
                saturated=False,
                evidence=[
                    dict(
                        root_seq=MAX_INT, notice_seq=MAX_INT, end_seq=MAX_INT, fact=fact
                    )
                    for _ in range(3)
                ],
            )
            for operation, fact in (
                ("fountain_drink", "detection_presented"),
                ("whistling", "sound_strange"),
            )
        ]
        for value in upper["coverage"].values():
            value.update(count=3, saturated=False)

        def encode(value):
            return json.dumps(
                value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            ).encode("ascii")

        self.assertLessEqual(len(encode(upper)), 4096)
        rows = [enabled(), session(2)]
        for _ in range(4):
            action(rows)
            action(rows, "fountain_drink", "detection_presented")
        first = self.project(*rows)
        self.assertEqual(
            [g["operation"] for g in first["episodes"]], ["fountain_drink", "whistling"]
        )
        self.assertEqual(encode(first), encode(self.project(*rows)))
        raw = wire(*rows)
        # Valid input cannot exceed the proven bound; inject a serializer result
        # only to exercise fail-closed defense against future schema expansion.
        with patch("json.dumps", return_value="x" * 4097):
            with self.assertRaisesRegex(ValueError, "summary.*cap"):
                episodes.project_episodes(raw)

    def test_legacy_empty_projection_and_redaction(self):
        expected = dict(
            episode_context_v=1,
            scope="selected_whistle_fountain",
            lookback_roots=32,
            episodes=[],
            coverage={
                key: dict(count=0, saturated=False)
                for key in (
                    "incomplete",
                    "blocked",
                    "completed_without_notice",
                    "omitted_roots",
                )
            },
        )
        for row in (
            session(),
            session(private={"target_id": "SECRET"}),
            session(vitals=obs()["vitals"]),
        ):
            self.assertEqual(self.project(row), expected)
        self.assertEqual(
            self.project(
                session(),
                event(2, event="apply", phase="attempt"),
                event(3, event="pray", detail="cancelled"),
            ),
            expected,
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
