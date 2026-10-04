"""Host check that a curio's prose promises nothing it cannot do (NGPL).

Proposal 3.4: the sandbox keeps a curio's behaviour truthful; this keeps its
prose truthful. A curio can only show text and request a Sanity change of
-2..2. check(texts) applies the rules in prompts/curio/truthfulness.json to
the name and every inspect/apply text the validation grid produced, and
returns the hits. It is a heuristic: it rejects some honest prose (measured in
docs/measurements/) and misses some false prose. It runs before install.
"""

import json
from pathlib import Path
import re

RULES_FILE = Path(__file__).resolve().parent / "prompts" / "curio" / "truthfulness.json"


def load_rules(path=RULES_FILE):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if type(data) is not dict or data.get("version") != 1:
        raise ValueError("unsupported truthfulness rules")
    rules = []
    for rule in data["rules"]:
        if set(rule) != {"id", "category", "pattern"}:
            raise ValueError("invalid truthfulness rule")
        rules.append((rule["id"], rule["category"], re.compile(rule["pattern"], re.I)))
    return tuple(rules)


_RULES = None


def check(texts, rules=None):
    """Return [{rule, category, text, match}] for every hit; [] means pass."""
    global _RULES
    if rules is None:
        if _RULES is None:
            _RULES = load_rules()
        rules = _RULES
    hits = []
    for text in texts:
        if type(text) is not str:
            raise ValueError("texts must be strings")
        for ident, category, pattern in rules:
            found = pattern.search(text)
            if found:
                hits.append(
                    dict(rule=ident, category=category, text=text, match=found.group(0))
                )
    return hits


def curio_texts(validation):
    """Every displayed string a validated curio can produce on the grid."""
    texts = [validation["name"], validation["admission_inspect"]]
    texts.append(validation["admission_apply"]["text"])
    texts += validation["inspect_texts"] + validation["apply_texts"]
    seen, out = set(), []
    for text in texts:
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out
