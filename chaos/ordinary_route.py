"""Pure public-snapshot ordinary-route decoder. Never imported in R1."""

from typing import Any, Final, Mapping, Sequence

RULES: Final = {
    "R-01-native-start-identity": {
        "condition": "native_start_identity",
        "action": ("STOP",),
        "limit": ("Brd", "Bard", "human", "male", "neutral", "dog"),
    },
    "R-02-options-and-environment": {
        "condition": "fixed_options_environment",
        "action": ("STOP",),
        "limit": (
            "name:ChaosReview,role:Brd,race:human,gender:male,align:neutral,"
            "pettype:dog,windowtype:tty,!news,!legacy,time,!splash_screen,"
            "!perm_invent,!autopickup",
            (24, 80),
            (
                ("PATH", "/usr/bin:/bin"),
                ("TERM", "xterm"),
                ("TZ", "UTC"),
                ("LC_ALL", "C"),
            ),
            (
                "isolated_HOME",
                "isolated_TMPDIR",
                "empty_MAIL",
                "observations_on",
                "echoes_off",
                "empty_mailbox",
                "no_director",
            ),
        ),
    },
    "R-03-initial-random-control": {
        "condition": "initial_random_control",
        "action": ("STOP",),
        "limit": "initial-srandom-zero/pass-through-reseed-v1",
    },
    "R-04-door-open-once": {
        "condition": "ordinary_open_attempts_per_visible_closed_door",
        "action": ("STOP", "ACTION"),
        "limit": 1,
    },
    "R-05-frontier-before-door": {
        "condition": "walkable_frontier_exhausted_before_door",
        "action": ("STOP", "ACTION"),
        "limit": ("k", "l", "j", "h", "u", "n", "b", "y"),
    },
    "R-06-first-fountain-only": {
        "condition": "first_discovered_fountain_frozen",
        "action": ("STOP", "ACTION"),
        "limit": "row,column ascending",
    },
    "R-07-natural-refresh-by-third": {
        "condition": "delivered_natural_water_refreshed_by_drink",
        "action": ("STOP",),
        "limit": 3,
    },
    "R-08-four-drink-total-cap": {
        "condition": "confirmed_affirmative_drinks_prefix_and_continuation",
        "action": ("STOP", "ACTION"),
        "limit": 4,
    },
    "R-09-absolute-move-ceiling": {
        "condition": "absolute_native_moves_before_dispatch",
        "action": ("STOP",),
        "limit": 300,
    },
    "R-10-public-stop-policy": {
        "condition": "all_public_safety_state_known_and_safe",
        "action": ("STOP",),
        "limit": (
            "hp",
            "hunger",
            "status",
            "threat",
            "pet",
            "tool",
            "fountain",
            "level",
            "input",
            "vision",
        ),
    },
    "R-11-no-rescue-or-search": {
        "condition": "single_prefix_no_rescue_or_search",
        "action": ("STOP",),
        "limit": (
            "seed_search",
            "hidden_lookahead",
            "wizard_rescue",
            "restore",
            "route_widening",
            "substitute_tool",
            "substitute_pet",
            "substitute_fountain",
            "forced_outcome",
            "ordinary_singing",
            "favorable_run_replacement",
        ),
    },
    "R-12-continuation-and-matched-replays": {
        "condition": "qualified_frozen_continuation_and_matched_replays",
        "action": ("STOP", "ACTION"),
        "limit": ("on", "passive_off_empty", "exact_on_replay", 3),
    },
}


def decode_public_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if (
        (
            snapshot.get("hp") is None
            or snapshot.get("hunger") is None
            or snapshot.get("status") is None
            or snapshot.get("threat") is None
            or snapshot.get("pet") is None
            or snapshot.get("tool") is None
            or snapshot.get("fountain") is None
            or snapshot.get("level") is None
            or snapshot.get("input") is None
            or snapshot.get("vision") is None
            or snapshot.get("hp") <= 0
        )
        and RULES["R-10-public-stop-policy"]["condition"]
        and RULES["R-10-public-stop-policy"]["limit"]
    ):
        return {"kind": "STOP", "code": "public_stop"}
    return {
        "hp": snapshot.get("hp"),
        "hunger": snapshot.get("hunger"),
        "status": snapshot.get("status"),
        "threat": snapshot.get("threat"),
        "pet": snapshot.get("pet"),
        "tool": snapshot.get("tool"),
        "fountain": snapshot.get("fountain"),
        "level": snapshot.get("level"),
        "input": snapshot.get("input"),
        "vision": snapshot.get("vision"),
        "doors": snapshot.get("doors"),
        "frontier": snapshot.get("frontier"),
        "moves": snapshot.get("moves"),
        "drinks": snapshot.get("drinks"),
        "refresh": snapshot.get("refresh"),
        "first_fountain": snapshot.get("first_fountain"),
        "fountains": snapshot.get("fountains"),
    }


def validate_start_receipt(receipt: Mapping[str, Any]) -> dict[str, str]:
    if (
        receipt.get("role") != RULES["R-01-native-start-identity"]["limit"][0]
        and receipt.get("role") != RULES["R-01-native-start-identity"]["limit"][1]
        or receipt.get("race") != RULES["R-01-native-start-identity"]["limit"][2]
        or receipt.get("gender") != RULES["R-01-native-start-identity"]["limit"][3]
        or receipt.get("align") != RULES["R-01-native-start-identity"]["limit"][4]
        or receipt.get("pet") != RULES["R-01-native-start-identity"]["limit"][5]
    ) and RULES["R-01-native-start-identity"]["condition"]:
        return {"kind": "STOP", "code": "native_start_identity"}
    if (
        receipt.get("options") != RULES["R-02-options-and-environment"]["limit"][0]
        or receipt.get("size") != RULES["R-02-options-and-environment"]["limit"][1]
        or receipt.get("env") != RULES["R-02-options-and-environment"]["limit"][2]
        or receipt.get("isolation") != RULES["R-02-options-and-environment"]["limit"][3]
    ) and RULES["R-02-options-and-environment"]["condition"]:
        return {"kind": "STOP", "code": "fixed_options_environment"}
    if (
        receipt.get("control") != RULES["R-03-initial-random-control"]["limit"]
        and RULES["R-03-initial-random-control"]["condition"]
    ):
        return {"kind": "STOP", "code": "initial_random_control"}
    if (
        receipt.get("rescue") in RULES["R-11-no-rescue-or-search"]["limit"]
        and RULES["R-11-no-rescue-or-search"]["condition"]
    ):
        return {"kind": "STOP", "code": "no_rescue_or_search"}
    return {"kind": "ACTION", "action": "start"}


def next_public_route_action(
    snapshot: Mapping[str, Any], history: Sequence[Any]
) -> dict[str, str]:
    if (
        (
            snapshot.get("hp") is None
            or snapshot.get("hunger") is None
            or snapshot.get("status") is None
            or snapshot.get("threat") is None
            or snapshot.get("pet") is None
            or snapshot.get("tool") is None
            or snapshot.get("fountain") is None
            or snapshot.get("level") is None
            or snapshot.get("input") is None
            or snapshot.get("vision") is None
            or snapshot.get("hp") <= 0
            or snapshot.get("hunger") == "WEAK"
            or snapshot.get("hunger") == "FAINTING"
            or snapshot.get("hunger") == "FAINTED"
            or snapshot.get("hunger") == "STARVED"
            or snapshot.get("threat") != "none"
        )
        and RULES["R-10-public-stop-policy"]["condition"]
        and RULES["R-10-public-stop-policy"]["limit"]
    ):
        return {"kind": "STOP", "code": "public_stop"}
    if (
        snapshot.get("moves") is None
        or snapshot.get("moves") >= RULES["R-09-absolute-move-ceiling"]["limit"]
        and RULES["R-09-absolute-move-ceiling"]["condition"]
    ):
        return {"kind": "STOP", "code": "absolute_native_moves_before_dispatch"}
    if (
        snapshot.get("rescue") in RULES["R-11-no-rescue-or-search"]["limit"]
        and RULES["R-11-no-rescue-or-search"]["condition"]
    ):
        return {"kind": "STOP", "code": "no_rescue_or_search"}
    drinks = 0
    refreshed = 0
    for event in history:
        if event.get("kind") == "drink":
            drinks = drinks + 1
        if event.get("kind") == "refresh":
            refreshed = 1
    if snapshot.get("drinks") is not None:
        drinks = snapshot.get("drinks")
    if snapshot.get("refresh"):
        refreshed = 1
    if (
        drinks >= RULES["R-08-four-drink-total-cap"]["limit"]
        and RULES["R-08-four-drink-total-cap"]["condition"]
        and history is not None
    ):
        return {"kind": "STOP", "code": "four_drink_total_cap"}
    if (
        refreshed == 1
        and drinks <= RULES["R-07-natural-refresh-by-third"]["limit"]
        and RULES["R-07-natural-refresh-by-third"]["condition"]
        and history is not None
    ):
        return {"kind": "STOP", "code": "prefix_complete"}
    if (
        refreshed == 0
        and drinks >= RULES["R-07-natural-refresh-by-third"]["limit"]
        and RULES["R-07-natural-refresh-by-third"]["condition"]
        and history is not None
    ):
        return {"kind": "STOP", "code": "NO_ORIGIN_WITHIN_BUDGET"}
    if (
        snapshot.get("frontier")
        and RULES["R-05-frontier-before-door"]["condition"]
        and RULES["R-05-frontier-before-door"]["limit"]
    ):
        for step in RULES["R-05-frontier-before-door"]["limit"]:
            if snapshot.get("frontier") and step in snapshot.get("frontier"):
                if step == "k":
                    return {"kind": "ACTION", "action": "k"}
                if step == "l":
                    return {"kind": "ACTION", "action": "l"}
                if step == "j":
                    return {"kind": "ACTION", "action": "j"}
                if step == "h":
                    return {"kind": "ACTION", "action": "h"}
                if step == "u":
                    return {"kind": "ACTION", "action": "u"}
                if step == "n":
                    return {"kind": "ACTION", "action": "n"}
                if step == "b":
                    return {"kind": "ACTION", "action": "b"}
                if step == "y":
                    return {"kind": "ACTION", "action": "y"}
    if (
        snapshot.get("fountains")
        and RULES["R-06-first-fountain-only"]["condition"]
        and RULES["R-06-first-fountain-only"]["limit"]
    ):
        chosen = sorted(snapshot.get("fountains"))[0]
        if (
            snapshot.get("fountain") != chosen
            and snapshot.get("first_fountain") != chosen
        ):
            return {"kind": "STOP", "code": "substitute_fountain"}
        if drinks < RULES["R-07-natural-refresh-by-third"]["limit"] and refreshed == 0:
            if (
                snapshot.get("fountain") == chosen
                or snapshot.get("first_fountain") == chosen
            ):
                return {"kind": "ACTION", "action": "drink"}
    if (
        snapshot.get("fountain")
        and snapshot.get("first_fountain")
        and snapshot.get("fountain") == snapshot.get("first_fountain")
        and drinks < RULES["R-07-natural-refresh-by-third"]["limit"]
        and refreshed == 0
        and RULES["R-06-first-fountain-only"]["condition"]
        and RULES["R-06-first-fountain-only"]["limit"]
    ):
        return {"kind": "ACTION", "action": "drink"}
    opens = 0
    for event in history:
        if event.get("kind") == "open" and event.get("door") == snapshot.get("door"):
            opens = opens + 1
    if (
        snapshot.get("door")
        and opens < RULES["R-04-door-open-once"]["limit"]
        and RULES["R-04-door-open-once"]["condition"]
    ):
        return {"kind": "ACTION", "action": "open"}
    return {"kind": "STOP", "code": "STOP_NO_PUBLIC_ROUTE"}


def validate_frozen_continuation(
    snapshot: Mapping[str, Any], history: Sequence[Any]
) -> dict[str, str]:
    if (
        (
            snapshot.get("hp") is None
            or snapshot.get("hunger") is None
            or snapshot.get("status") is None
            or snapshot.get("threat") is None
            or snapshot.get("pet") is None
            or snapshot.get("tool") is None
            or snapshot.get("fountain") is None
            or snapshot.get("level") is None
            or snapshot.get("input") is None
            or snapshot.get("vision") is None
            or snapshot.get("hp") <= 0
        )
        and RULES["R-10-public-stop-policy"]["condition"]
        and RULES["R-10-public-stop-policy"]["limit"]
    ):
        return {"kind": "STOP", "code": "public_stop"}
    if (
        snapshot.get("moves") is None
        or snapshot.get("moves") >= RULES["R-09-absolute-move-ceiling"]["limit"]
        and RULES["R-09-absolute-move-ceiling"]["condition"]
    ):
        return {"kind": "STOP", "code": "absolute_native_moves_before_dispatch"}
    if (
        snapshot.get("drinks") is not None
        and snapshot.get("drinks") >= RULES["R-08-four-drink-total-cap"]["limit"]
        and RULES["R-08-four-drink-total-cap"]["condition"]
    ):
        return {"kind": "STOP", "code": "four_drink_total_cap"}
    if (
        snapshot.get("rescue") in RULES["R-11-no-rescue-or-search"]["limit"]
        and RULES["R-11-no-rescue-or-search"]["condition"]
    ):
        return {"kind": "STOP", "code": "no_rescue_or_search"}
    if (
        snapshot.get("prefix") != "qualified"
        and RULES["R-12-continuation-and-matched-replays"]["condition"]
        and RULES["R-12-continuation-and-matched-replays"]["limit"]
    ):
        return {"kind": "STOP", "code": "unqualified_prefix"}
    if (
        snapshot.get("continuation")
        != RULES["R-12-continuation-and-matched-replays"]["limit"][0]
        and snapshot.get("continuation")
        != RULES["R-12-continuation-and-matched-replays"]["limit"][1]
        and snapshot.get("continuation")
        != RULES["R-12-continuation-and-matched-replays"]["limit"][2]
        and RULES["R-12-continuation-and-matched-replays"]["condition"]
    ):
        return {"kind": "STOP", "code": "unqualified_continuation"}
    if (
        snapshot.get("continuation")
        == RULES["R-12-continuation-and-matched-replays"]["limit"][2]
        and snapshot.get("match") != "exact"
        and RULES["R-12-continuation-and-matched-replays"]["condition"]
    ):
        return {"kind": "STOP", "code": "BLOCKED_REPLAY"}
    if (
        snapshot.get("replays") is not None
        and snapshot.get("replays")
        >= RULES["R-12-continuation-and-matched-replays"]["limit"][3]
        and RULES["R-12-continuation-and-matched-replays"]["condition"]
    ):
        return {"kind": "STOP", "code": "matched_replay_cap"}
    return {"kind": "ACTION", "action": "continue"}


def check_route_receipt(
    snapshot: Mapping[str, Any], history: Sequence[Any]
) -> dict[str, str]:
    drinks = 0
    refreshed = 0
    replays = 0
    for event in history:
        if event.get("kind") == "drink":
            drinks = drinks + 1
        if event.get("kind") == "refresh":
            refreshed = 1
        if event.get("kind") == "replay":
            replays = replays + 1
    if snapshot.get("drinks") is not None:
        drinks = snapshot.get("drinks")
    if snapshot.get("refresh"):
        refreshed = 1
    if snapshot.get("replays") is not None:
        replays = snapshot.get("replays")
    if (
        drinks >= RULES["R-08-four-drink-total-cap"]["limit"]
        and RULES["R-08-four-drink-total-cap"]["condition"]
        and history is not None
    ):
        return {"kind": "STOP", "code": "four_drink_total_cap"}
    if (
        refreshed == 0
        and drinks >= RULES["R-07-natural-refresh-by-third"]["limit"]
        and RULES["R-07-natural-refresh-by-third"]["condition"]
        and history is not None
    ):
        return {"kind": "STOP", "code": "NO_ORIGIN_WITHIN_BUDGET"}
    if (
        snapshot.get("moves") is None
        or snapshot.get("moves") >= RULES["R-09-absolute-move-ceiling"]["limit"]
        and RULES["R-09-absolute-move-ceiling"]["condition"]
    ):
        return {"kind": "STOP", "code": "absolute_native_moves_before_dispatch"}
    if (
        snapshot.get("replay")
        != RULES["R-12-continuation-and-matched-replays"]["limit"][0]
        and snapshot.get("replay")
        != RULES["R-12-continuation-and-matched-replays"]["limit"][1]
        and snapshot.get("replay")
        != RULES["R-12-continuation-and-matched-replays"]["limit"][2]
        and RULES["R-12-continuation-and-matched-replays"]["condition"]
    ):
        return {"kind": "STOP", "code": "unmatched_replay"}
    if (
        snapshot.get("replay")
        == RULES["R-12-continuation-and-matched-replays"]["limit"][2]
        and snapshot.get("match") != "exact"
        and RULES["R-12-continuation-and-matched-replays"]["condition"]
    ):
        return {"kind": "STOP", "code": "BLOCKED_REPLAY"}
    if (
        replays >= RULES["R-12-continuation-and-matched-replays"]["limit"][3]
        and RULES["R-12-continuation-and-matched-replays"]["condition"]
        and history is not None
    ):
        return {"kind": "STOP", "code": "matched_replay_cap"}
    return {"kind": "ACTION", "action": "accept"}
