"""Test-only no-whisper wire policies; callers select, never infer policy."""

HISTORICAL = (1, 2)
CURRENT = (3, 4)


def validate_rows(rows, policy):
    """Validate every complete row, including legitimately empty fault prefixes."""
    assert policy in (HISTORICAL, CURRENT), "unsupported policy"
    ordinary, observation = policy
    for row in rows:
        version = row.get("v")
        assert type(version) is int and version in policy, "wire policy/version"
        is_observation = version == observation
        assert (row.get("event") == "observation") == is_observation, "event kind"
        assert ("observation" in row) == is_observation, "observation field"
        if is_observation:
            assert isinstance(row["observation"], dict), "observation object"
        if policy == CURRENT:
            cosmetic = row.get("cosmetic")
            assert isinstance(cosmetic, dict) and set(cosmetic) == {
                "seen",
                "last_turn",
            }, "cosmetic shape"
            assert all(
                type(value) is int and value == 0 for value in cosmetic.values()
            ), "zero cosmetic state"
    return rows


def ordinary_projection(rows, policy, *, renumber_seq=True):
    """Preserve every ordinary field; only permitted sequence renumbering changes."""
    validate_rows(rows, policy)
    result = [dict(row) for row in rows if row["v"] == policy[0]]
    assert result, "missing ordinary rows"
    if renumber_seq:
        for seq, row in enumerate(result, 1):
            row["seq"] = seq
    return result
