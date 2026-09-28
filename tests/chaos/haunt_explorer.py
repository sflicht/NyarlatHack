"""Screen-only player for the #165 ordinary haunt test (no hidden state).

Reads the rendered 24x80 terminal (sweep_screen.Screen) as a player would and
chooses movement keys from it alone:

- leave() walks out of the start room and along whatever it can see, never
  standing on the same square twice (so there is no backtracking before it
  is inside a room larger than the one it started in). Ties go to the square
  farther from the start. Dark corridor squares show only next to the
  player, so when nothing unvisited is in sight it tries a step into the
  unseen.
- pace() then walks back and forth along the longest open line through the
  player: the natural backtracking the haunt watches for.
"""

from collections import deque

from sweep_screen import Screen, status

MAP_TOP, MAP_BOTTOM = 1, 21  # rows between the message line and status lines
WALLS = set("─│┌┐└┘├┤┬┴┼")
KEYS = {
    (-1, 0): "h",
    (1, 0): "l",
    (0, -1): "k",
    (0, 1): "j",
    (-1, -1): "y",
    (1, -1): "u",
    (-1, 1): "b",
    (1, 1): "n",
}
DELTA = {key: delta for delta, key in KEYS.items()}


def chebyshev(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


class Player:
    def __init__(self, game):
        self.game = game
        self.screen = Screen()
        self.fed = 0
        self.visited = []
        self.blocked = set()
        self.sync()
        self.origin = self.me()
        self.start_room = self.room(self.origin)

    # --- what the screen shows ---------------------------------------------
    def sync(self):
        raw = bytes(self.game.raw)
        self.screen.feed(raw[self.fed :])
        self.fed = len(raw)

    def cell(self, x, y):
        if not (0 <= x < 80 and MAP_TOP <= y <= MAP_BOTTOM):
            return None
        return self.screen.rows[y][x]

    def find(self, glyph):
        return [
            (x, y)
            for y in range(MAP_TOP, MAP_BOTTOM + 1)
            for x in range(80)
            if self.screen.rows[y][x] == glyph
        ]

    def me(self):
        found = self.find("@")
        if len(found) != 1:
            raise AssertionError("player not on screen:\n" + self.screen.text())
        return found[0]

    def status(self):
        return status(self.screen)

    def walkable(self, x, y):
        c = self.cell(x, y)
        return c is not None and c not in " +" and c not in WALLS

    def doorway(self, x, y):
        """A gap in a wall line; no diagonal moves into or out of it."""
        return (self.cell(x - 1, y) in WALLS and self.cell(x + 1, y) in WALLS) or (
            self.cell(x, y - 1) in WALLS and self.cell(x, y + 1) in WALLS
        )

    def room(self, start):
        """Room squares 4-connected to start (no corridor, no doorway)."""
        seen, todo = {start}, deque([start])
        while todo:
            x, y = todo.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (x + dx, y + dy)
                if n in seen or not self.walkable(*n):
                    continue
                if self.cell(*n) == "#" or self.doorway(*n):
                    continue
                seen.add(n)
                todo.append(n)
        return seen

    def in_larger_room(self):
        pos = self.me()
        if self.doorway(*pos) or self.cell(*pos) == "#" or pos in self.start_room:
            return False
        return len(self.room(pos)) > len(self.start_room)

    # --- moving --------------------------------------------------------------
    def step(self, key):
        before = self.me()
        self.game.more(self.game.send(key))
        self.sync()
        after = self.me()
        if after == before and key in DELTA:
            dx, dy = DELTA[key]
            self.blocked.add((before, (before[0] + dx, before[1] + dy)))
        return before, after

    def moves(self, pos):
        x, y = pos
        for (dx, dy), key in KEYS.items():
            n = (x + dx, y + dy)
            if (pos, n) in self.blocked or not self.walkable(*n):
                continue
            if dx and dy and (self.doorway(*pos) or self.doorway(*n)):
                continue
            yield n, key

    def plan(self):
        """First key towards the nearest unvisited square outside the start
        room, over unvisited squares only; ties prefer squares farther from
        the start, then orthogonal first steps."""
        start = self.me()
        first: dict = {start: ""}
        dist = {start: 0}
        todo = deque([start])
        best = None
        while todo:
            cur = todo.popleft()
            for nxt, key in self.moves(cur):
                if nxt in first or nxt in self.visited:
                    continue
                first[nxt] = first[cur] or key
                dist[nxt] = dist[cur] + 1
                todo.append(nxt)
                if nxt not in self.start_room:
                    rank = (
                        dist[nxt],
                        -chebyshev(nxt, self.origin),
                        first[nxt] not in "hjkl",
                    )
                    if best is None or rank < best[0]:
                        best = (rank, first[nxt])
        if best is not None:
            return best[1]
        # Nothing unvisited in sight: try an unseen orthogonal square.
        x, y = start
        guesses = [
            (-chebyshev((x + dx, y + dy), self.origin), key)
            for (dx, dy), key in KEYS.items()
            if not (dx and dy)
            and self.cell(x + dx, y + dy) == " "
            and (start, (x + dx, y + dy)) not in self.blocked
        ]
        return min(guesses)[1] if guesses else None

    def leave(self, limit=200):
        """Walk, never revisiting a square, until inside a larger room."""
        self.visited.append(self.me())
        for _ in range(limit):
            if self.in_larger_room():
                return self.me()
            key = self.plan()
            if key is None:
                raise AssertionError("nowhere new to go:\n" + self.screen.text())
            _, after = self.step(key)
            if after != self.visited[-1]:
                if after in self.visited:
                    raise AssertionError(f"revisited {after}")
                self.visited.append(after)
        raise AssertionError("no larger room within the step limit")

    def pace_line(self):
        """The longest open horizontal (else vertical) line through '@'."""
        x, y = self.me()
        best = None
        for (dx, dy), (back, forth) in (((1, 0), ("h", "l")), ((0, 1), ("k", "j"))):
            lo = hi = 0
            while self.walkable(x - dx * (lo + 1), y - dy * (lo + 1)):
                lo += 1
            while self.walkable(x + dx * (hi + 1), y + dy * (hi + 1)):
                hi += 1
            if best is None or lo + hi > best[0]:
                best = (lo + hi, lo, hi, back, forth)
        return best

    def pace(self, until, limit=60):
        """Walk back and forth across the room until until() is true."""
        _, lo, hi, back, forth = self.pace_line()
        keys = [back] * lo + ([forth] * (lo + hi) + [back] * (lo + hi)) * 10
        for key in keys[:limit]:
            if until():
                return True
            self.step(key)
        return until()

    def farlook(self, target):
        """The player's own ';' look at a square: the game's description."""
        x, y = self.me()
        dx, dy = target[0] - x, target[1] - y
        keys = ("l" if dx > 0 else "h") * abs(dx) + ("j" if dy > 0 else "k") * abs(dy)
        text = self.game.send(";")
        if b"--More--" in text:  # "Please move the cursor to an unknown object."
            self.game.send(" ")
        for key in keys:
            self.game.send(key)
        text = self.game.send(".")
        answer = text
        for _ in range(30):  # page through the game's description
            if b"--More--" not in text:
                break
            text = self.game.send(" ")
            answer += text
        self.sync()
        return answer.decode("utf-8", "replace")
