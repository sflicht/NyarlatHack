"""Scripted player for the seed sweep (#167). Not an AI, not a human proxy.

The policy reads only the rendered 24x80 screen (what a player sees) and its
own memory of earlier inputs. Every choice comes from a declared parameter
set and a policy RNG seeded from (policy name, start, seed). No wizard mode,
no hidden-state lookahead, no retries and no discarded seeds.

One harness wait is not a policy decision: after an action whose public
event completes a qualifying origin, the driver waits for the offline
director to finish its one-shot next-use decision before the next input.
Without that wait the result would depend on wall-clock scheduling.
"""

import json
import os
from pathlib import Path
import random
import re
import select
import time

from gameplay_support import Game, ROOT
from sweep_screen import COLS, Screen, status

START_OPTIONS = {
    # The ordinary default start (chaos/ordinary_start.py), plus !mail below.
    "bard": None,
    # Madmen start at Sanity 75 (src/u_init.c).
    "madman": (
        "name:ChaosReview,role:Madman,race:human,gender:male,align:neutral,"
        "windowtype:tty,!news,!legacy,time,!splash_screen,!perm_invent,!autopickup"
    ),
    # Same Bard, but a descendant carrying a fixed heirloom artifact.
    "bard-inherited": (
        "name:ChaosReview,role:Brd,race:human,gender:male,align:neutral,"
        "pettype:dog,descendant,inherited:Vampire Killer,windowtype:tty,!news,"
        "!legacy,time,!splash_screen,!perm_invent,!autopickup"
    ),
}

POLICIES = {
    "baseline-v1": {
        "max_turns": 2000,
        "max_dlvl": 5,
        "max_commands": 8000,
        "stall_commands": 200,
        "no_food_retry_turns": 200,
        "p_whistle": 0.03,
        "p_fountain": 0.25,
        "fountain_quaffs_per_level": 2,
        "min_turns_per_level": 300,
        "p_search": 0.05,
        "p_travel_explore": 0.8,
        "prayer_gap_turns": 1000,
        "save_restore_turn": 700,
    }
}

LAUNCHER = ["--ordinary", "--next-use", "--max-runtime", "86400"]
DIRECTOR_SETTLED = (
    b"envelope_published_not_admitted",
    b"abstained",
    b"already_published",
    b"failed",
    b"director stopped",
)
QUALIFYING = {
    "whistling": {
        "sound_high",
        "sound_shrill",
        "sound_normal",
        "sound_strange",
        "sound_humming",
    },
    "fountain_drink": {"water_refreshed"},
}
DIRS = "hjklyubn"
DELTA = dict(
    h=(-1, 0), j=(0, 1), k=(0, -1), l=(1, 0), y=(-1, -1), u=(1, -1), b=(-1, 1), n=(1, 1)
)
MONSTER = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ@&;:'")
FOUNTAIN = "\u00b6"
WALKABLE = set('\u00b7#+\u2592<>%$)[?!/="*(`{I')
NEIGHBOURS_4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
NEIGHBOURS_8 = NEIGHBOURS_4 + ((1, 1), (1, -1), (-1, 1), (-1, -1))


class HarnessError(Exception):
    pass


# The engine's mail daemon stats the host's real mail spool; a message
# arriving mid-sweep changes the game. Every sweep start disables it.
NO_HOST_MAIL = ",!mail"


def _with_options(options):
    """Game reads chaos.ordinary_start.OPTIONS in its forked child."""
    import chaos.ordinary_start as start

    return start, (start.OPTIONS if options is None else options) + NO_HOST_MAIL


class Player:
    def __init__(self, dnethackdir, clock, root, seed, start, policy, asset_pool):
        self.params = POLICIES[policy]
        self.seed, self.start_name, self.policy = seed, start, policy
        self.rng = random.Random(f"{policy}:{start}:{seed}")
        self.game = Game(
            dnethackdir,
            clock,
            observe=True,
            ordinary=True,
            launcher_fresh=True,
            launcher_options=LAUNCHER,
            root=root,
            asset_pool=asset_pool,
        )
        self.screen = Screen()
        self.fed = 0
        self.commands = 0
        self.whistle = None
        self.last_prayer = None
        self.level_since = {}
        self.quaffs = {}
        self.event_offset = 0
        self.log = []
        self.sync_timeouts = 0
        self.no_food_until = -1
        self.not_fountains = set()
        self.frontier_tried = {}
        self.redrawn = {}
        self.visited = {}
        self.last_turn = None
        self.same_turn_commands = 0
        self.saved = False
        self.restore_detail = None
        self.outcome = None

    # ---- terminal plumbing -------------------------------------------------
    def _feed(self):
        raw = bytes(self.game.raw[self.fed :])
        self.fed = len(self.game.raw)
        self.screen.feed(raw)

    def send(self, keys):
        try:
            text = self.game.send(keys)
        except (FileNotFoundError, ProcessLookupError):
            # The game exited between our write and the harness's /proc input
            # check. Treat it as the exit it is, not a harness failure.
            if not self.exited():
                raise
            text = self._drain()
        self._feed()
        return text

    def _drain(self):
        """Collect the exited game's final terminal output until PTY EOF."""
        data = bytearray()
        fd = self.game.fd
        while fd is not None and select.select([fd], [], [], 0.2)[0]:
            try:
                part = os.read(fd, 65536)
            except OSError:
                break
            if not part:
                break
            data.extend(part)
        self.game.raw.extend(data)
        return bytes(data)

    def exited(self):
        if self.game.pid is None:
            return True
        done, status_ = os.waitpid(self.game.pid, os.WNOHANG)
        if done:
            self.game.pid = None
            self.game.exitcode = os.waitstatus_to_exitcode(status_)
            return True
        return False

    def settle(self, text):
        """Dismiss pages, menus and unexpected prompts. Returns 'dead' or None."""
        for _ in range(40):
            if self.exited():
                return "dead"
            if b"possessions identified" in text or b"DYWYPI" in text:
                self.game.finish(text)
                self._feed()
                return "dead"
            if b"--More--" in text:
                text = self.send(" ")
            elif b"Really attack" in text:
                text = self.send("n")
            elif (
                b"[yn" in text
                or b"[yes/no]" in text
                or b"(end)" in text
                or re.search(rb"\(\d+ of \d+\)", text)
                or b"What do you want" in text
                or b"In what direction" in text
                or b"Where do you want" in text
                or b"Call " in text
            ):
                text = self.send("\x1b")
            else:
                return None
        raise HarnessError("prompt loop did not settle")

    def act(self, keys):
        self.commands += 1
        self.log.append(keys)
        text = self.send(keys)
        dead = self.settle(text)
        if not dead:
            self.sync_director()
        return dead

    # ---- director synchronisation (harness, not policy) --------------------
    def sync_director(self):
        run = self.game.run
        path = run / "events.jsonl"
        if not path.exists():
            return
        data = path.read_bytes()
        new, self.event_offset = data[self.event_offset :], len(data)
        ends = []
        for line in new.splitlines():
            e = json.loads(line)
            o = e.get("observation")
            if o and o["stage"] == "completed" and o["operation"] in QUALIFYING:
                ends.append(e["seq"])
        if not ends:
            return
        log = run / "director.log"
        if log.exists() and any(s in log.read_bytes() for s in DIRECTOR_SETTLED[1:]):
            return  # one-shot decision already made
        schedule = run / "next_use-schedule.jsonl"
        rows = (
            [json.loads(s) for s in schedule.read_text().splitlines()]
            if schedule.exists()
            else []
        )
        if not any(r["end_seq"] in ends for r in rows):
            return  # engine declared no schedulable origin; nothing to wait for
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if log.exists() and any(s in log.read_bytes() for s in DIRECTOR_SETTLED):
                return
            time.sleep(0.05)
        self.sync_timeouts += 1

    # ---- public observations -----------------------------------------------
    def hero(self):
        y, x = self.screen.y, self.screen.x
        return (x, y) if 1 <= y <= 21 else None

    def find(self, chars):
        return [
            (x, y)
            for y in range(1, 22)
            for x, ch in enumerate(self.screen.rows[y])
            if ch in chars
        ]

    # ---- actions -----------------------------------------------------------
    def travel(self, target):
        text = self.send("_")
        if b"Where do you want to travel" not in text:
            return self.settle(text)
        cx, cy = self.screen.x, self.screen.y
        dx, dy = target[0] - cx, target[1] - cy
        keys = ""
        for step, big, small in (
            (dx, "L", "l"),
            (-dx, "H", "h"),
            (dy, "J", "j"),
            (-dy, "K", "k"),
        ):
            if step > 0:
                keys += big * (step // 8) + small * (step % 8)
        if keys:
            self.send(keys)
        dead = self.act(".")
        hero = self.hero()
        if dead or not hero or hero == target:
            return dead
        dx, dy = target[0] - hero[0], target[1] - hero[1]
        if max(abs(dx), abs(dy)) == 1:
            # Travel stops beside closed doors and similar; step in (autoopen).
            key = next(k for k, v in DELTA.items() if v == (dx, dy))
            return self.act(key)
        return None

    def learn_inventory(self):
        text = self.send("i")
        page = text
        while b"--More--" in text or re.search(rb"\(\d+ of \d+\)", text):
            text = self.send(" ")
            page += text
        m = re.search(
            rb"([A-Za-z]) - (?:a|an) (?:uncursed |blessed |cursed )?tin whistle", page
        )
        self.whistle = m.group(1).decode() if m else None
        self.settle(self.send("\x1b"))

    def pray(self, turn):
        self.last_prayer = turn
        text = self.send("#pray\n")
        if b"Are you sure you want to pray" in text:
            text = self.send("y")
        self.commands += 1
        dead = self.settle(text)
        if not dead:
            self.sync_director()
        return dead

    def eat(self):
        text = self.send("e")
        for _ in range(3):
            if b"eat it?" in text or b"eat one?" in text:
                text = self.send("n")
                continue
            break
        m = re.search(rb"What do you want to eat\? \[([A-Za-z]+)", text)
        if m:
            text = self.send(m.group(1)[:1])
        elif b"don't have anything to eat" in text:
            s = status(self.screen)
            self.no_food_until = (s["turn"] if s else 0) + self.params[
                "no_food_retry_turns"
            ]
        self.commands += 1
        return self.settle(text)

    def step(self):
        """One policy decision. Returns a stop reason or None."""
        s = status(self.screen)
        if s is None:
            return self.settle(self.send("\x1b")) or None
        p = self.params
        if s["turn"] == self.last_turn:
            self.same_turn_commands += 1
            if self.same_turn_commands >= p["stall_commands"]:
                return "stalled"
        else:
            self.last_turn, self.same_turn_commands = s["turn"], 0
        if s["turn"] >= p["max_turns"]:
            return "turn_limit"
        if s["dlvl"] >= p["max_dlvl"]:
            return "depth_limit"
        if self.commands >= p["max_commands"]:
            return "command_limit"
        if not self.saved and s["turn"] >= p["save_restore_turn"]:
            return "save_restore"
        level = s["dlvl"]
        self.level_since.setdefault(level, s["turn"])
        if self.hero():
            self.visited.setdefault(level, set()).add(self.hero())
        low = s["hp"] < 5 or 7 * s["hp"] < s["hp_max"]
        weak = s["hunger"] in ("Weak", "Fainting", "Fainted")
        if (low or weak) and (
            self.last_prayer is None
            or s["turn"] - self.last_prayer >= p["prayer_gap_turns"]
        ):
            return self.pray(s["turn"])
        if s["hunger"] and s["turn"] >= self.no_food_until:
            return self.eat()
        roll = self.rng.random()
        if self.whistle and roll < p["p_whistle"]:
            return self.act("a" + self.whistle)
        hero = self.hero()
        fountains = [
            f for f in self.find(FOUNTAIN) if (level, f) not in self.not_fountains
        ]
        if (
            hero
            and fountains
            and self.quaffs.get(level, 0) < p["fountain_quaffs_per_level"]
            and self.rng.random() < p["p_fountain"]
        ):
            target = min(
                fountains, key=lambda f: (abs(f[0] - hero[0]) + abs(f[1] - hero[1]), f)
            )
            if target != hero:
                dead = self.travel(target)
                if dead:
                    return dead
            if self.hero() == target:
                self.quaffs[level] = self.quaffs.get(level, 0) + 1
                text = self.send("q")
                if b"Drink from the fountain" in text:
                    text = self.send("y")
                else:  # a forge shares the glyph; decline, remember publicly
                    self.not_fountains.add((level, target))
                self.commands += 1
                dead = self.settle(text)
                if not dead:
                    self.sync_director()
                return dead
            return None
        if hero:
            for d in DIRS:
                x, y = hero[0] + DELTA[d][0], hero[1] + DELTA[d][1]
                if 0 <= x < COLS and 1 <= y <= 21 and self.screen.rows[y][x] in MONSTER:
                    return self.act(d)
        stairs = self.find(">")
        if (
            hero
            and stairs
            and s["turn"] - self.level_since[level] >= p["min_turns_per_level"]
        ):
            target = min(stairs)
            if target != hero:
                dead = self.travel(target)
                if dead:
                    return dead
            if self.hero() == target:
                return self.act(">")
            return None
        if self.rng.random() < p["p_search"]:
            return self.act("10s")
        frontier = self.frontier(level, hero)
        if frontier and self.rng.random() < p["p_travel_explore"]:
            # Nearest untried frontier; policy RNG breaks distance ties.
            best = min(abs(f[0] - hero[0]) + abs(f[1] - hero[1]) for f in frontier)
            near = [
                f for f in frontier if abs(f[0] - hero[0]) + abs(f[1] - hero[1]) == best
            ]
            target = self.rng.choice(near)
            self.frontier_tried.setdefault(level, set()).add(target)
            return self.travel(target)
        if not frontier and hero:
            # Exhausted visible frontier: redraw (the tty port can leave the
            # remembered map undrawn after overlays), forget old targets once,
            # then search for hidden passages.
            if not self.redrawn.get(level):
                self.redrawn[level] = True
                self.frontier_tried[level] = set()
                self.send("\x12")
                return None
            self.redrawn[level] = False
            return self.act("15s")
        return self.act(self.rng.choice(DIRS).upper())

    def frontier(self, level, hero):
        """Public unexplored edges: seen, never-stood-on squares beside an
        unseen blank (8-neighbour for corridors, 4-neighbour elsewhere)."""
        if not hero:
            return []
        tried = self.frontier_tried.get(level, set())
        seen = self.visited.get(level, set())
        rows = self.screen.rows

        def blank(x, y):
            return 0 <= x < COLS and 1 <= y <= 21 and rows[y][x] == " "

        out = []
        for y in range(1, 22):
            for x in range(COLS):
                ch = rows[y][x]
                if (
                    ch not in WALKABLE
                    or (x, y) in tried
                    or (x, y) in seen
                    or (x, y) == hero
                ):
                    continue
                around = NEIGHBOURS_8 if ch == "#" else NEIGHBOURS_4
                if any(blank(x + dx, y + dy) for dx, dy in around):
                    out.append((x, y))
        return out

    def save_restore(self):
        self.saved = True
        code = self.game.save()
        if code != 0:
            raise HarnessError(f"save exit {code}")
        before = len(self.game.events())
        self.game.launcher_fresh = False
        self.screen, self.fed = Screen(), len(self.game.raw)
        self._start()
        sessions = [
            e for e in self.game.events()[before:] if e.get("event") == "session"
        ]
        self.restore_detail = sessions[-1]["detail"] if sessions else None
        self.event_offset = (self.game.run / "events.jsonl").stat().st_size

    def _start(self):
        module, options = _with_options(START_OPTIONS[self.start_name])
        saved = module.OPTIONS
        setattr(module, "OPTIONS", options)
        try:
            text = self.game.start()
        finally:
            setattr(module, "OPTIONS", saved)
        self._feed()
        return self.settle(text)

    def play(self):
        try:
            if self._start():
                self.outcome = "died_at_start"
                return self
            self.learn_inventory()
            while True:
                reason = self.step()
                if reason == "save_restore":
                    self.save_restore()
                    continue
                if reason == "dead":
                    self.outcome = "died"
                    break
                if reason:
                    self.outcome = reason
                    code = self.game.quit()
                    if code != 0:
                        raise HarnessError(f"quit exit {code}")
                    break
        except Exception as exc:  # recorded, never retried or discarded
            self.outcome = "harness_error"
            self.error = f"{type(exc).__name__}: {exc}"[:300]
        finally:
            self.game.close()
        return self


def play(dnethackdir, clock, root, seed, start, policy, asset_pool):
    os.environ["NYARLATHACK_SWEEP_SEED"] = str(seed)
    player = Player(
        dnethackdir, clock, Path(root), seed, start, policy, asset_pool
    ).play()
    s = status(player.screen) or {}
    return {
        "outcome": player.outcome,
        "error": getattr(player, "error", None),
        "commands": player.commands,
        "final_status": s,
        "whistle_in_inventory": player.whistle is not None,
        "save_restore": {
            "attempted": player.saved,
            "session_detail": player.restore_detail,
        },
        "sync_timeouts": player.sync_timeouts,
        "exit_code": player.game.exitcode,
    }


__all__ = ["POLICIES", "START_OPTIONS", "play", "ROOT"]
