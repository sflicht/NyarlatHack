"""`chaos chronicle RUN_DIR`: a shareable post-mortem page (#188).

Facts come only from `reveal.json`, which the engine writes into the run
directory at game end (src/chaos_reveal_game.c) and only when something was
admitted. It holds the exact lines of the dumplog section "The Crawling Chaos
remembers.", so this module re-derives nothing: it groups those lines and
formats them. Stock and empty-mailbox games have no reveal.json and no page.

The character's name, role and death reason come from the game's own
xlogfile (the launcher's game root, or --xlogfile): the one line whose turn
count and chaos_admitted/delivered/spent equal the record's. If no single line
matches, the page says so and names nobody rather than guess.

Optional intent (#23) comes from a separate file the caller names with
--intent. It is untrusted editorial text: it is attached only to an admitted
entry, always under the label "Intent, not proof", and never to the refused
count. Nothing here writes into RUN_DIR, calls a model or uses the network.
"""

from __future__ import annotations

import html
import json
import os
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path

RECORD = "reveal.json"
RECORD_VERSION = 1
MAX_BYTES = 1 << 20
MAX_INTENT_BYTES = 256 * 1024
MAX_XLOG_TAIL = 4 << 20
MAX_FIELD = 200
DEFAULT_XLOGFILE = Path(__file__).resolve().parent.parent / "dnethackdir" / "xlogfile"
# (male or neutral, female) role names by xlogfile code, exactly as in
# src/role.c; tests/chaos/test_chronicle.py checks this table against it.
ROLES = {
    "Arc": ("Archeologist", None),
    "Ana": ("Anachrononaut", None),
    "Bar": ("Barbarian", None),
    "Bin": ("Binder", None),
    "Cav": ("Caveman", "Cavewoman"),
    "Con": ("Convict", None),
    "Hea": ("Healer", None),
    "Kni": ("Knight", None),
    "Ken": ("Kensei", None),
    "Mon": ("Monk", None),
    "Mad": ("Madman", "Madwoman"),
    "Nob": ("Nobleman", "Noblewoman"),
    "Pri": ("Priest", "Priestess"),
    "Pir": ("Pirate", None),
    "Rog": ("Rogue", None),
    "Ran": ("Ranger", None),
    "Sam": ("Samurai", None),
    "Tou": ("Tourist", None),
    "Brd": ("Troubadour", None),
    "Hnt": ("Undead Hunter", None),
    "Val": ("Valkyrie", None),
    "Wiz": ("Wizard", None),
}
MAX_INTENT_CHARS = 2000
HEADER = "The Crawling Chaos remembers."
INTENT_LABEL = "Intent, not proof"
INTENT_NOTE = (
    "Author rationale supplied separately. The engine did not check it, and it"
    " is not evidence of what happened."
)


class ChronicleError(Exception):
    """The run directory has no usable engine record."""


@dataclass
class Entry:
    heading: str
    details: list[str] = field(default_factory=list)
    intent: str | None = None


@dataclass
class Character:
    name: str
    role: str
    death: str
    maxlvl: int | None


@dataclass
class Chronicle:
    final_turn: int
    admitted: int
    delivered: int
    spent: int
    rejected: int
    entries: list[Entry]
    notes: list[str]
    tally: list[str]
    character: Character | None = None
    character_note: str | None = None


def _read_private(path: Path, limit: int) -> bytes:
    """Read one regular file without following links, bounded."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ChronicleError(f"{path.name} is not a regular file")
        if st.st_size > limit:
            raise ChronicleError(f"{path.name} is larger than {limit} bytes")
        data = b""
        while len(data) <= limit:
            chunk = os.read(fd, limit + 1 - len(data))
            if not chunk:
                break
            data += chunk
        if len(data) > limit:
            raise ChronicleError(f"{path.name} is larger than {limit} bytes")
        return data
    finally:
        os.close(fd)


def _count(record: dict, key: str) -> int:
    value = record.get(key)
    if type(value) is not int or value < 0:
        raise ChronicleError(f"{RECORD}: {key} must be a non-negative integer")
    return value


def load(run_dir: Path) -> Chronicle:
    """Parse the engine's reveal record from RUN_DIR."""
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise ChronicleError(f"{run_dir} is not a directory")
    path = run_dir / RECORD
    try:
        raw = _read_private(path, MAX_BYTES)
    except FileNotFoundError:
        raise ChronicleError(
            f"{run_dir} has no {RECORD}: nothing was admitted in that game, or it"
            " has not ended yet"
        ) from None
    except OSError as e:
        raise ChronicleError(f"cannot read {RECORD}: {e.strerror}") from None
    try:
        record = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ChronicleError(f"{RECORD} is not valid JSON") from None
    if not isinstance(record, dict) or record.get("reveal_v") != RECORD_VERSION:
        raise ChronicleError(f"{RECORD}: unsupported reveal_v")
    lines = record.get("lines")
    if not isinstance(lines, list) or not all(isinstance(x, str) for x in lines):
        raise ChronicleError(f"{RECORD}: lines must be a list of strings")
    counts = {
        k: _count(record, k)
        for k in ("final_turn", "admitted", "delivered", "spent", "rejected")
    }
    if counts["admitted"] < 1:
        raise ChronicleError(f"{RECORD}: nothing admitted")
    if not lines or lines[0] != HEADER:
        raise ChronicleError(f"{RECORD}: missing section header")

    entries: list[Entry] = []
    notes: list[str] = []
    tally: list[str] = []
    for line in lines[1:]:
        if line == "":
            continue
        if line.startswith("    "):
            if not entries:
                raise ChronicleError(f"{RECORD}: detail line before any entry")
            entries[-1].details.append(line.strip())
        elif line.startswith("  Turn "):
            entries.append(Entry(line.strip()))
        elif line.startswith("  Admitted ") or line.endswith("none took effect."):
            tally.append(line.strip())
        elif line.startswith("  ("):
            notes.append(line.strip())
        else:
            raise ChronicleError(f"{RECORD}: unexpected line {line!r}")
    if not tally or not tally[0].startswith(f"Admitted {counts['admitted']},"):
        raise ChronicleError(f"{RECORD}: tally does not match the counts")
    return Chronicle(entries=entries, notes=notes, tally=tally, **counts)


def _xlog_fields(line: str) -> dict[str, str]:
    fields = {}
    for part in line.split(":"):
        key, sep, value = part.partition("=")
        if sep and key not in fields:
            fields[key] = value
    return fields


def attach_character(chronicle: Chronicle, path: Path) -> None:
    """Name the character from the game's xlogfile, or explain why not.

    Only the end record the game itself wrote is used (no hidden state). A line
    matches when its turns and chaos_admitted/delivered/spent equal the reveal
    record's; exactly one match is required.
    """
    want = {
        "turns": str(chronicle.final_turn),
        "chaos_admitted": str(chronicle.admitted),
        "chaos_delivered": str(chronicle.delivered),
        "chaos_spent": str(chronicle.spent),
    }
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        chronicle.character_note = "The game's xlogfile was not found."
        return
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            chronicle.character_note = "The game's xlogfile is not a regular file."
            return
        os.lseek(fd, max(0, st.st_size - MAX_XLOG_TAIL), os.SEEK_SET)
        data = b""
        while chunk := os.read(fd, 1 << 16):
            data += chunk
            if len(data) > MAX_XLOG_TAIL:
                break
    finally:
        os.close(fd)
    matches = []
    for raw in data.decode("utf-8", "replace").splitlines():
        f = _xlog_fields(raw)
        if all(f.get(k) == v for k, v in want.items()):
            matches.append(f)
    if len(matches) != 1:
        chronicle.character_note = (
            "No end record in the xlogfile matches this game."
            if not matches
            else "Several end records in the xlogfile match this game; none is named."
        )
        return
    f = matches[0]
    name = f.get("name", "").strip()[:MAX_FIELD]
    death = f.get("death", "").strip()[:MAX_FIELD]
    if not name or not death:
        chronicle.character_note = "The matching xlogfile record has no name or death."
        return
    code = f.get("role", "")
    male, female = ROLES.get(code, (code[:MAX_FIELD], None))
    role = female if female and f.get("gender") == "Fem" else male
    maxlvl = f.get("maxlvl", "")
    chronicle.character = Character(
        name=name,
        role=role,
        death=death,
        maxlvl=int(maxlvl) if maxlvl.isdigit() else None,
    )


def _character_line(c: Chronicle) -> str | None:
    ch = c.character
    if ch is None:
        return None
    who = f"{ch.name} the {ch.role}" if ch.role else ch.name
    depth = f", deepest level {ch.maxlvl}" if ch.maxlvl else ""
    return f"{who}: {ch.death}{depth}."


def attach_intent(chronicle: Chronicle, path: Path) -> None:
    """Attach author rationale by entry number (1-based, admitted entries only).

    PROVISIONAL FORMAT, pending #23 (which will define the rationale record;
    expect this to change): a JSON object mapping
    "1", "2", ... to a string. Numbers that name no admitted entry are an
    error, so rationale can never be shown for something that did not happen.
    """
    try:
        data = json.loads(_read_private(Path(path), MAX_INTENT_BYTES).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ChronicleError(f"cannot read intent file: {e}") from None
    if not isinstance(data, dict):
        raise ChronicleError("intent file must be a JSON object")
    for key, text in data.items():
        if not (isinstance(key, str) and key.isdigit()):
            raise ChronicleError(f"intent key {key!r} is not an entry number")
        n = int(key)
        if not 1 <= n <= len(chronicle.entries):
            raise ChronicleError(f"intent names entry {n}, which was not admitted")
        if not isinstance(text, str) or not text.strip():
            raise ChronicleError(f"intent for entry {n} must be non-empty text")
        chronicle.entries[n - 1].intent = text.strip()[:MAX_INTENT_CHARS]


def _md_text(s: str) -> str:
    """Markdown-inert text: escape HTML and Markdown control characters."""
    s = html.escape(s, quote=True)
    out = []
    for ch in s:
        out.append("\\" + ch if ch in "\\`*_{}[]()#+-.!|~>" else ch)
    return "".join(out)


def render_markdown(c: Chronicle) -> str:
    out = [
        "# What watched you",
        "",
        f"_{_md_text(HEADER)}_ The game ended on turn {c.final_turn}.",
        "",
    ]
    who = _character_line(c)
    if who is not None:
        out += [f"**{_md_text(who)}**", ""]
    elif c.character_note:
        out += [f"_{_md_text(c.character_note)}_", ""]
    for i, e in enumerate(c.entries, 1):
        out.append(f"## {i}. {_md_text(e.heading)}")
        out.append("")
        out.extend(f"- {_md_text(d)}" for d in e.details)
        if e.intent is not None:
            out += ["", f"> **{INTENT_LABEL}.** {_md_text(INTENT_NOTE)}", ">"]
            out += [f"> {_md_text(line)}" for line in e.intent.splitlines() or [""]]
        out.append("")
    for n in c.notes:
        out += [_md_text(n), ""]
    out.append("## Tally")
    out.append("")
    out.extend(f"- {_md_text(t)}" for t in c.tally)
    out += [
        "",
        "_Facts come from the engine's own records (`reveal.json`, the same"
        " lines as the game's dumplog, and the game's xlogfile end record)."
        " Refused candidates are counted, never described._",
        "",
    ]
    return "\n".join(out)


CSS = """
body{font:16px/1.5 Georgia,serif;max-width:44rem;margin:2rem auto;padding:0 1rem;
color:#e8e2d0;background:#15130f}
h1{font-weight:normal;letter-spacing:.04em}h2{font-size:1.05rem;margin:1.6rem 0 .3rem}
ul{margin:.2rem 0 .6rem;padding-left:1.2rem}.meta,.foot{color:#a49a82;font-size:.9rem}
.intent{border-left:3px solid #7a5c2e;margin:.4rem 0 .8rem;padding:.2rem .8rem;
background:#201b13}.intent .label{font-weight:bold;color:#d6a857}
.who{font-size:1.1rem}.intent .note{color:#a49a82;font-size:.85rem}.tally{border-top:1px solid #3a342a;
margin-top:1.6rem;padding-top:.6rem}
"""


def render_html(c: Chronicle) -> str:
    e_ = html.escape
    body = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\';'
        " style-src 'unsafe-inline'\">",
        "<title>What watched you</title>",
        f"<style>{CSS}</style></head><body>",
        "<h1>What watched you</h1>",
        f'<p class="meta"><em>{e_(HEADER)}</em> The game ended on turn {c.final_turn}.</p>',
    ]
    who = _character_line(c)
    if who is not None:
        body.append(f'<p class="who">{e_(who)}</p>')
    elif c.character_note:
        body.append(f'<p class="meta">{e_(c.character_note)}</p>')
    for i, e in enumerate(c.entries, 1):
        body.append(f'<section class="entry"><h2>{i}. {e_(e.heading)}</h2><ul>')
        body.extend(f"<li>{e_(d)}</li>" for d in e.details)
        body.append("</ul>")
        if e.intent is not None:
            text = "<br>".join(e_(line) for line in e.intent.splitlines())
            body.append(
                f'<aside class="intent"><div class="label">{e_(INTENT_LABEL)}</div>'
                f'<div class="note">{e_(INTENT_NOTE)}</div><p>{text}</p></aside>'
            )
        body.append("</section>")
    body.extend(f"<p>{e_(n)}</p>" for n in c.notes)
    body.append('<div class="tally"><ul>')
    body.extend(f"<li>{e_(t)}</li>" for t in c.tally)
    body.append("</ul></div>")
    body.append(
        '<p class="foot">Facts come from the engine\'s own records (reveal.json,'
        " the same lines as the game's dumplog, and the game's xlogfile end"
        " record). Refused candidates are counted, never described.</p>"
        "</body></html>\n"
    )
    return "\n".join(body)


def add_parser(sub) -> None:
    p = sub.add_parser(
        "chronicle",
        help="render a finished game's post-mortem as a shareable page",
        description="Render RUN_DIR/reveal.json as a self-contained Markdown or"
        " HTML page. Read-only; offline; no model.",
    )
    p.add_argument("run_dir", type=Path, metavar="RUN_DIR")
    p.add_argument("--format", choices=("html", "md"), default="html")
    p.add_argument("--out", type=Path, help="output file (default: stdout)")
    p.add_argument(
        "--intent",
        type=Path,
        help='optional JSON {"1": "rationale", ...}; shown as intent, not proof.'
        " PROVISIONAL format pending #23",
    )
    p.add_argument(
        "--xlogfile",
        type=Path,
        default=DEFAULT_XLOGFILE,
        help="the game's xlogfile, for the character's name and death"
        " (default: the launcher's game root)",
    )


def run(args) -> int:
    try:
        c = load(args.run_dir)
        attach_character(c, getattr(args, "xlogfile", DEFAULT_XLOGFILE))
        if args.intent is not None:
            attach_intent(c, args.intent)
        if args.out is not None:
            run_real = Path(args.run_dir).resolve()
            out_real = args.out.resolve()
            if out_real == run_real or run_real in out_real.parents:
                raise ChronicleError("--out must not be inside RUN_DIR (read-only)")
    except ChronicleError as e:
        print(f"chronicle: {e}", file=sys.stderr)
        return 1
    text = render_html(c) if args.format == "html" else render_markdown(c)
    if args.out is None:
        sys.stdout.write(text)
    else:
        args.out.write_text(text, encoding="utf-8")
    return 0
