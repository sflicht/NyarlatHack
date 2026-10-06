"""Separately named public-screen curio capture player; not a sweep gate."""

from collections import deque
import hashlib
import json
import os
import random
import re
import shutil
import time

from gameplay_support import ANSI, Game
from sweep_player import DELTA, DIRS, START_OPTIONS, WALKABLE, Player, _with_options


class CaptureGame(Game):
    def finish(self, text):
        assert self.pid is not None and self.fd is not None
        deadline, prompts = time.monotonic() + 8.0, 0
        while True:
            done, status = os.waitpid(self.pid, os.WNOHANG)
            if done:
                self.pid = None
                self.exitcode = os.waitstatus_to_exitcode(status)
                os.close(self.fd)
                self.fd = None
                self.save_artifacts()
                return self.exitcode
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            plain = ANSI.sub(b"", text)
            markers = list(
                re.finditer(rb"--More--|\(end\)|\(\d+ of \d+\)|\[ynq\]", plain)
            )
            response = None
            if markers:
                last = markers[-1]
                if last.group() == b"[ynq]":
                    question = b" ".join(plain[: last.start()].split())
                    response = (
                        "y"
                        if question.endswith(b"Do you want to know what watched you?")
                        else "n"
                    )
                else:
                    response = " "
            if response is not None:
                if prompts >= 40:
                    break
                prompts += 1
                text = self.send(response, deadline=deadline)
            else:
                text = self.read(min(0.2, remaining))
            if not text:
                time.sleep(min(0.01, max(0, deadline - time.monotonic())))
        raise AssertionError("capture endgame did not exit: " + repr(text[-500:]))

    def save(self):
        # The saving process's pid is the save's hackpid; replay comparison
        # must exclude it, so record it before the session ends.
        reader_pid = getattr(self, "_reader_pid", None)
        code = super().save()
        if code:
            return code
        source = self.game / "save"
        files = sorted(source.iterdir())
        if not files or any(p.is_symlink() or not p.is_file() for p in files):
            raise RuntimeError("capture needs regular native save files")
        snapshots = self.root / "save-snapshots"
        snapshots.mkdir(exist_ok=True)
        dest = snapshots / f"{len(list(snapshots.iterdir())) + 1:04d}"
        dest.mkdir()  # Never silently overwrite retained evidence.
        manifest = {"reader_pid": reader_pid}
        for path in files:
            target = dest / path.name
            shutil.copy2(path, target)
            manifest[path.name] = {
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "bytes": target.stat().st_size,
            }
        (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        return code


class CapturePlayer(Player):
    def __init__(self, dnethackdir, clock, root, seed, start, policy, asset_pool):
        if policy != "curio-capture-v1":
            raise ValueError("CapturePlayer only implements curio-capture-v1")
        super().__init__(
            dnethackdir,
            clock,
            root,
            seed,
            start,
            "baseline-v2",
            asset_pool,
            game_type=CaptureGame,
        )
        self.policy = policy
        self.params = dict(self.params, whistle_only_visible_pet=True)
        self.rng = random.Random(f"{policy}:{start}:{seed}")

    def _start(self):
        module, options = _with_options(
            START_OPTIONS[self.start_name], "pet-visible-v1"
        )
        saved = module.OPTIONS
        module.OPTIONS = options
        try:
            text = self.game.start()
        finally:
            module.OPTIONS = saved
        self._feed()
        return self.settle(text)

    def seek_whistle(self, level, hero):
        # Exploration handles every public tool glyph, not just named whistles.
        return False, None

    def _inventory(self, letter=None):
        text, items = self.send("i"), {}
        for _ in range(20):
            page = dict(
                re.findall(r"(?m)^\s*([a-zA-Z]) [-+] (.+?)\s*$", self.screen.text())
            )
            items.update(page)
            if letter in page:
                return items, self.send(letter)
            plain = ANSI.sub(b"", text)
            if b"(end)" in plain or not re.search(rb"\(\d+ of \d+\)|--More--", plain):
                self.send("\x1b")
                return items, None
            text = self.send(" ")
        raise AssertionError("capture inventory pagination exceeded 20 pages")

    def inspect_and_apply(self, letter):
        _, menu = self._inventory(letter)
        if menu is None:
            return None
        plain = ANSI.sub(b"", menu)
        if b"I - Describe this item" not in plain:
            self.send("\x1b")
            return None
        can_apply = b"a - Apply" in plain
        result = self.settle(self.send("I"))
        if result:
            return result
        return self.act("a" + letter) if can_apply else None

    def settle(self, text):
        if getattr(self, "_pickup_menu_pending", False):
            for _ in range(20):
                if b"--More--" not in text:
                    break
                text = self.send(" ")
            else:
                raise AssertionError("capture pickup messages exceeded 20 pages")
        plain = ANSI.sub(b"", text)
        if (
            getattr(self, "_pickup_menu_pending", False)
            and b"Pick up what?" in plain
            and re.search(rb"\(end\)|\(\d+ of \d+\)", plain)
        ):
            # Native query_objlist exposes '(' as the Tools group selector,
            # including off-page entries. Only use it inside our pickup action.
            self._pickup_menu_pending = False
            text = self.send("(\n")
        return super().settle(text)

    def pickup_tool(self):
        self.pickup_succeeded = False
        before, _ = self._inventory()
        self._pickup_menu_pending = True
        try:
            result = self.act(",")
        finally:
            self._pickup_menu_pending = False
        if result:
            return result
        after, _ = self._inventory()
        for letter, description in after.items():
            if before.get(letter) != description:
                self.pickup_succeeded = True
                result = self.inspect_and_apply(letter)
                if result:
                    return result
        return None

    def explore(self, s, level, hero):
        if hero is None:
            return self.act("s")
        failed = self.__dict__.setdefault("failed_steps", {}).setdefault(level, {})
        previous = self.__dict__.pop("previous_step", None)
        if previous is not None and previous[0] == level:
            _, old, nxt = previous
            if old == hero:
                failed[old, nxt] = failed.get((old, nxt), 0) + 1
        near = set(self.adjacent(hero, self.monsters(hero)))
        for key in DIRS:
            dx, dy = DELTA[key]
            if (hero[0] + dx, hero[1] + dy) in near:
                return self.act(key)
        # Sparse public memory: blanks do not erase terrain seen earlier.
        maps = self.__dict__.setdefault("map_memory", {})
        terrain = maps.setdefault(level, {})
        for y in range(1, 22):
            for x, glyph in enumerate(self.screen.rows[y]):
                if glyph in WALKABLE or glyph in "─│┌┐└┘├┤┬┴┼":
                    terrain[x, y] = glyph
                elif self.screen.backgrounds[y][x] == 4:
                    terrain.setdefault((x, y), "·")
        terrain.setdefault(hero, "·")
        visited = self.visited.setdefault(level, set())
        visited.add(hero)
        tried = self.__dict__.setdefault("pickup_tried", set())
        attempts = self.__dict__.setdefault("pickup_attempts", {})
        spot = level, hero
        if terrain.get(hero) == "(" and spot not in tried and attempts.get(spot, 0) < 3:
            attempts[spot] = attempts.get(spot, 0) + 1
            self.pickup_succeeded = False
            result = self.pickup_tool()
            if self.pickup_succeeded:
                tried.add(spot)
            return result
        # Honour the inherited baseline-v2 dwell (public turn counter only):
        # without it the player dives past DL1-2 before the curio trigger's
        # public 150-turn history exists, and native expiry closes the chance.
        since = self.level_since.get(level, s["turn"])
        dwell = s["turn"] - since < self.params["min_turns_per_level"]
        if terrain.get(hero) == ">" and not dwell:
            return self.act(">")
        # Cardinal steps avoid illegal diagonals through doorways. Never plan
        # through unseen stone or peek at the engine's level data.
        queue: deque[tuple[tuple[int, int], str | None]] = deque([(hero, None)])
        seen = {hero}
        routes = {}
        while queue:
            point, first = queue.popleft()
            for key in "hjkl":
                dx, dy = DELTA[key]
                nxt = point[0] + dx, point[1] + dy
                if (
                    nxt not in seen
                    and terrain.get(nxt) in WALKABLE
                    and failed.get((point, nxt), 0) < 3
                ):
                    seen.add(nxt)
                    routes[nxt] = first or key
                    queue.append((nxt, first or key))
        tools = [p for p in routes if terrain[p] == "(" and p not in visited]
        stairs = [] if dwell else [p for p in routes if terrain[p] == ">"]
        unvisited = [p for p in routes if p not in visited]
        target = next(iter(tools or stairs or unvisited), None)
        if target is None:
            searches = self.__dict__.setdefault("edge_searches", {}).setdefault(
                level, {}
            )
            edges = [
                point
                for point in [hero, *routes]
                if any(
                    terrain.get((point[0] + DELTA[key][0], point[1] + DELTA[key][1]))
                    not in WALKABLE
                    for key in "hjkl"
                )
            ]
            target = min(edges, key=lambda point: searches.get(point, 0), default=hero)
            if target == hero:
                searches[hero] = searches.get(hero, 0) + 1
                return self.act("10s")
        key = routes[target]
        dx, dy = DELTA[key]
        nxt = hero[0] + dx, hero[1] + dy
        self.previous_step = level, hero, nxt
        opened = self.__dict__.setdefault("opened_doors", set())
        if terrain[nxt] == "▒" and (level, nxt) not in opened:
            result = self.act("o" + key)
            message = self.screen.line(0)
            if "The door opens." in message or "This door is already open." in message:
                opened.add((level, nxt))
            return result
        return self.act(key)

    def monsters(self, hero):
        return [
            (x, y)
            for x, y in super().monsters(hero)
            if self.screen.backgrounds[y][x] != 4
        ]
