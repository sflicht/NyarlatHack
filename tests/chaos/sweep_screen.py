"""Minimal 24x80 terminal model for the seed-sweep player.

Handles only the control sequences the tty port emits (cursor moves, erase,
background colour retained). The player reads what a human would see: this screen.
"""

import codecs
import re

ROWS, COLS = 24, 80
_CSI = re.compile(r"\x1b\[([0-9;?]*)([ -/]*)([@-~])")
_OTHER_ESC = re.compile(r"\x1b[()][0-9A-Za-z]|\x1b[=>78DEHMc]")


class Screen:
    def __init__(self):
        self.rows = [[" "] * COLS for _ in range(ROWS)]
        self.backgrounds = [[None] * COLS for _ in range(ROWS)]
        self._background = None
        self.y = self.x = 0
        self._pending = ""
        self._utf8 = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def feed(self, data):
        # Incremental decode: a character split across PTY reads stays whole.
        text = self._pending + self._utf8.decode(data)
        self._pending = ""
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == "\x1b":
                m = _CSI.match(text, i)
                if m:
                    self._csi(m.group(1), m.group(3))
                    i = m.end()
                    continue
                m = _OTHER_ESC.match(text, i)
                if m:
                    i = m.end()
                    continue
                if len(text) - i < 16:  # split sequence: keep for next feed
                    self._pending = text[i:]
                    return
                i += 1
                continue
            if ch == "\r":
                self.x = 0
            elif ch == "\n":
                self.y = min(ROWS - 1, self.y + 1)
            elif ch == "\b":
                self.x = max(0, self.x - 1)
            elif ch >= " ":
                if self.x >= COLS:
                    self.x = 0
                    self.y = min(ROWS - 1, self.y + 1)
                self.rows[self.y][self.x] = ch
                self.backgrounds[self.y][self.x] = self._background
                self.x += 1
            i += 1

    def _csi(self, params, final):
        private = params.startswith("?")
        nums = (
            [int(p) if p else 0 for p in params.lstrip("?").split(";")]
            if params
            else []
        )
        n = nums[0] if nums and nums[0] else 1
        if private:
            return
        if final == "m":
            self._sgr(nums or [0])
        elif final == "H" or final == "f":
            row = nums[0] if nums and nums[0] else 1
            col = nums[1] if len(nums) > 1 and nums[1] else 1
            self.y, self.x = min(ROWS, row) - 1, min(COLS, col) - 1
        elif final == "A":
            self.y = max(0, self.y - n)
        elif final == "B":
            self.y = min(ROWS - 1, self.y + n)
        elif final == "C":
            self.x = min(COLS - 1, self.x + n)
        elif final == "D":
            self.x = max(0, self.x - n)
        elif final == "J":
            mode = nums[0] if nums else 0
            if mode == 2:
                self.rows = [[" "] * COLS for _ in range(ROWS)]
                self.backgrounds = [[None] * COLS for _ in range(ROWS)]
            elif mode == 0:
                self.rows[self.y][self.x :] = [" "] * (COLS - self.x)
                self.backgrounds[self.y][self.x :] = [None] * (COLS - self.x)
                for r in range(self.y + 1, ROWS):
                    self.rows[r] = [" "] * COLS
                    self.backgrounds[r] = [None] * COLS
            elif mode == 1:
                for r in range(self.y):
                    self.rows[r] = [" "] * COLS
                    self.backgrounds[r] = [None] * COLS
                self.rows[self.y][: self.x + 1] = [" "] * (self.x + 1)
                self.backgrounds[self.y][: self.x + 1] = [None] * (self.x + 1)
        elif final == "K":
            mode = nums[0] if nums else 0
            if mode == 0:
                self.rows[self.y][self.x :] = [" "] * (COLS - self.x)
                self.backgrounds[self.y][self.x :] = [None] * (COLS - self.x)
            elif mode == 1:
                self.rows[self.y][: self.x + 1] = [" "] * (self.x + 1)
                self.backgrounds[self.y][: self.x + 1] = [None] * (self.x + 1)
            else:
                self.rows[self.y] = [" "] * COLS
                self.backgrounds[self.y] = [None] * COLS

    def _sgr(self, values):
        i = 0
        while i < len(values):
            value = values[i]
            if value in (0, 49):
                self._background = None
            elif 40 <= value <= 47:
                self._background = value - 40
            elif 100 <= value <= 107:
                self._background = value - 100 + 8
            elif value in (38, 48):
                # Skip extended foreground channels too: a channel value 44
                # is not a blue background escape.
                tail = values[i + 1 :]
                if len(tail) >= 2 and tail[0] == 5:
                    if value == 48:
                        self._background = tail[1]
                    i += 2
                elif len(tail) >= 4 and tail[0] == 2:
                    if value == 48:
                        self._background = tuple(tail[1:4])
                    i += 4
                else:
                    if value == 48:
                        self._background = None
                    break
            i += 1

    def line(self, y):
        return "".join(self.rows[y])

    def text(self):
        return "\n".join(self.line(y) for y in range(ROWS))


_STATUS = re.compile(
    r"Dlvl:(?P<dlvl>\d+).*?HP:(?P<hp>-?\d+)\((?P<hpmax>\d+)\).*?T:(?P<turn>\d+)"
)


def status(screen):
    """Public bottom-line status, or None while it is not drawn."""
    bottom = screen.line(ROWS - 1)
    m = _STATUS.search(bottom)
    if not m:
        return None
    hunger = next(
        (h for h in ("Fainting", "Fainted", "Weak", "Hungry") if h in bottom), None
    )
    return {
        "dlvl": int(m["dlvl"]),
        "hp": int(m["hp"]),
        "hp_max": int(m["hpmax"]),
        "turn": int(m["turn"]),
        "hunger": hunger,
    }
