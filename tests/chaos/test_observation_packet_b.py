"""Independent CURRENT synthetic contracts, never native evidence."""

import copy
import json
import unittest

from native_observation_contract import CURRENT
import test_episode_fountain as fountain
import test_episode_fountain_matrix as matrix
import test_episode_fountain_fatal_oracle as fatal
import test_episode_whistle as whistle

CONTEXT = dict(
    turn=101,
    safe=1,
    sanity=73,
    insight=19,
    budget=4,
    spent=0,
    reserved=0,
    last_id=0,
    vitals=dict(hp=20, hp_max=20, power=20, power_max=23),
)


def current_rows(
    *,
    enabled=True,
    kind="fountain_drink",
    notice="water_refreshed",
    terminal="completed",
    rootless=False,
    expiry=False,
):
    rows = []

    def add(event, detail="", safe=1, observation=None, phase="result"):
        row = dict(
            copy.deepcopy(CONTEXT),
            v=4 if observation else 3,
            seq=len(rows) + 1,
            event=event,
            detail=detail,
            safe=safe,
            phase=phase,
            cosmetic=dict(seen=0, last_turn=0),
        )
        if observation:
            row["observation"] = observation
        rows.append(row)

    def obs(stage, root=0, fact="none", safe=1):
        add(
            "observation",
            safe=safe,
            phase="attempt" if stage == "started" else "result",
            observation=dict(
                operation="none" if stage == "enabled" else kind,
                stage=stage,
                root_seq=root,
                fact=fact,
            ),
        )

    if enabled:
        obs("enabled", safe=0)
    add("session", "new", safe=0)
    add("level_enter", safe=0)
    add("safe_point", "level_enter")
    if expiry:
        add("curio", "expired")
    if kind == "whistling":
        add("apply", phase="attempt")
    if enabled and not rootless:
        root = len(rows) + 1
        obs("started")
        if notice:
            obs("notice", root, notice)
        obs(terminal, root)
    return rows


def raw(rows):
    return b"\n".join(json.dumps(r).encode() for r in rows) + b"\n"


class CurrentPacketBTests(unittest.TestCase):
    def reject_semantic_changes(self, rows, check):
        check(rows)
        for mutate in (
            lambda r: r[-1].update(phase="attempt"),
            lambda r: r[-1]["observation"].update(root_seq=2),
            lambda r: r[-1].update(turn=102),
            lambda r: r.pop(),
            lambda r: r.pop(-2),
            lambda r: r[0]["cosmetic"].update(seen=False),
            lambda r: r[1]["cosmetic"].update(last_turn=1),
            lambda r: r[1].update(v=1),
        ):
            bad = copy.deepcopy(rows)
            mutate(bad)
            with self.assertRaises((AssertionError, ValueError)):
                check(bad)

    def test_current_fountain_and_semantic_controls(self):
        self.reject_semantic_changes(
            current_rows(),
            lambda r: fountain.validate_history(
                r, CONTEXT, enabled=True, future=True, policy=CURRENT
            ),
        )
        for presented in (False, True):
            rows = current_rows(notice="detection_presented" if presented else None)
            self.reject_semantic_changes(
                rows,
                lambda r: fountain.validate_detection_history(
                    r, CONTEXT, enabled=True, presented=presented, policy=CURRENT
                ),
            )
        for noshow in (False, True):
            rows = current_rows(
                notice=None if noshow else "cannot_reach", terminal="blocked"
            )

            def check(r):
                fountain.validate_reach_history(
                    r, CONTEXT, enabled=True, noshow=noshow, policy=CURRENT
                )

            self.reject_semantic_changes(rows, check)
            bad = copy.deepcopy(rows)
            bad[-1]["observation"]["stage"] = "completed"
            with self.assertRaises(AssertionError):
                check(bad)

    def test_current_fountain_narrow_projection(self):
        off = current_rows(enabled=False)
        on = current_rows()
        fountain.validate_legacy_pair(off, on, policy=CURRENT)
        bad = copy.deepcopy(on)
        bad[2]["seq"] += 1
        with self.assertRaises(AssertionError):
            fountain.validate_legacy_pair(off, bad, policy=CURRENT)
        with self.assertRaises(AssertionError):
            fountain.validate_legacy_pair([], [], policy=CURRENT)

    def test_current_matrix_full_history(self):
        for fate, notice in (
            (1, "water_refreshed"),
            (20, "water_foul"),
            (23, None),
            (26, "detection_presented"),
        ):
            rows = current_rows(notice=notice, expiry=fate == 23)
            self.reject_semantic_changes(
                rows,
                lambda r: matrix.validate_history(
                    raw(r), CONTEXT, CONTEXT, fate, True, policy=CURRENT
                ),
            )
        rows = current_rows(rootless=True, notice=None)
        matrix.validate_history(
            raw(rows), CONTEXT, CONTEXT, 10, True, "no-mouth", policy=CURRENT
        )
        with self.assertRaises((AssertionError, ValueError)):
            matrix.validate_history(
                raw(current_rows(notice=None)),
                CONTEXT,
                CONTEXT,
                10,
                True,
                "no-mouth",
                policy=CURRENT,
            )

    def test_current_fatal_nonempty_pair(self):
        off = dict(
            records=current_rows(enabled=False),
            **{
                k: b"witness"
                for k in ("terminal", "inputs", "xlog", "dump", "native", "before")
            },
        )
        on = dict(off, records=current_rows())
        fatal.compare_pair(off, on, policy=CURRENT)
        for rows in ([], current_rows()):
            bad = copy.deepcopy(on)
            bad["records"] = rows
            if rows:
                bad["records"][1]["spent"] = 1
            with self.assertRaises(AssertionError):
                fatal.compare_pair(off, bad, policy=CURRENT)

    def test_current_fatal_death_contract(self):
        rows = current_rows(notice=None)
        rows.pop()  # death before the selected action returns/completes
        for row in rows:
            row["turn"] = 1
            row["vitals"]["hp"] = 1
        death = copy.deepcopy(rows[1])
        death.update(seq=len(rows) + 1, event="death", detail="died", safe=1)
        death["vitals"]["hp"] = 0
        rows.append(death)
        native = dict(gameover=1, hp=-1, rng_count=3, entered=1, returned=0)
        terminal = b"The water is contaminated!"
        xlog = b"contaminated water"
        from chaos.episodes import project_episodes

        public = project_episodes(raw(rows))
        fatal.validate_fatal(
            rows, native, terminal, xlog, public, enabled=True, policy=CURRENT
        )
        self.assertEqual(
            len(
                fatal.reject_mutated_death_evidence(
                    rows, native, terminal, xlog, public, policy=CURRENT
                )
            ),
            4,
        )
        for mutate in (
            lambda r: r[-2].update(phase="result"),
            lambda r: r[-2]["observation"].update(root_seq=2),
            lambda r: r.pop(-2),
            lambda r: r[1]["cosmetic"].update(seen=True),
        ):
            bad = copy.deepcopy(rows)
            mutate(bad)
            with self.assertRaises(AssertionError):
                fatal.validate_fatal(
                    bad, native, terminal, xlog, public, enabled=True, policy=CURRENT
                )

    def test_current_whistle_semantic_controls(self):
        for suppressed in (False, True):
            rows = current_rows(
                kind="whistling", notice=None if suppressed else "sound_high"
            )
            self.reject_semantic_changes(
                rows,
                lambda r: whistle.validate_observations(
                    r,
                    enabled=True,
                    dispatch=False,
                    suppressed=suppressed,
                    fact="sound_high",
                    policy=CURRENT,
                ),
            )
        rows = current_rows(kind="whistling", rootless=True)
        whistle.validate_observations(
            rows,
            enabled=True,
            dispatch=True,
            suppressed=False,
            fact="sound_high",
            policy=CURRENT,
        )
        bad = copy.deepcopy(rows)
        bad[0]["cosmetic"]["seen"] = True
        with self.assertRaises(AssertionError):
            whistle.validate_observations(
                bad,
                enabled=True,
                dispatch=True,
                suppressed=False,
                fact="sound_high",
                policy=CURRENT,
            )
