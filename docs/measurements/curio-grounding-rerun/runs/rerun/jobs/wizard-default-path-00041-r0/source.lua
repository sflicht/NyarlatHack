local function inspect(ctx)
  local side = ctx.state % 2
  if ctx.charges == 0 then
    return "No turn remains. FAR and NEAR share the near end, and neither steps aside."
  end
  if ctx.sanity < 50 then
    if side == 0 then
      return "Warm bone, cold ink. The end not held seems to have been counted already."
    end
    return "NEAR is correct, and the warmth disagrees, arriving from the end called FAR."
  end
  if ctx.insight > 0 and ctx.state >= 2 then
    return "A hairline like an undecided latch crosses the second inch. Both ends say FIRST."
  end
  if ctx.insight > 0 then
    if side == 0 then
      return "The marks agree together and disagree with the hand. The mismatch is exact."
    end
    return "Reversed, the rule is consistent. It is consistent about the wrong premise."
  end
  if ctx.state >= 2 and side == 0 then
    return "Both ends read FIRST. The length is the same, and the sameness does not help."
  end
  if ctx.state >= 2 then
    return "FAR is back under the thumb, but FIRST remains on the end now called far."
  end
  if side == 0 then
    return "A dry bone rule, thumb-long. FAR is inked at the near end, and the ink looks wet."
  end
  return "NEAR has come under the thumb. The inches, unasked, still leave from there."
end
local function apply(ctx)
  local s = ctx.state
  local side = s % 2
  local text
  local delta
  local nxt
  if ctx.charges == 0 then
    text = "No turn remains. The labels stay as they are, each slightly too exact."
    delta = 0
    nxt = s
  elseif s == 255 then
    text = "It will not turn again. Both ends keep their claims, each a little too exact."
    delta = 0
    nxt = s
  elseif ctx.sanity < 50 then
    text = "The warmth shifts before the bone does, and the ink stays perfectly calm."
    delta = -1
    nxt = s + 1
  elseif ctx.charges == 1 then
    text = "A stopped tick in the bone arrives before the turn, then pretends it did not."
    delta = -1
    nxt = s + 1
  elseif ctx.insight > 0 and side == 0 then
    text = "You reverse the rule. It becomes exact, which makes the near end less true."
    delta = -1
    nxt = s + 1
  elseif ctx.insight > 0 then
    text = "Turned back, FAR is restored. The exactness has simply changed its loyalty."
    delta = 0
    nxt = s + 1
  elseif side == 0 then
    text = "You turn the rule. NEAR meets the thumb; the inches decline that courtesy."
    delta = -1
    nxt = s + 1
  else
    text = "You turn it back. FAR returns, yet the warmth remains with the end just lost."
    delta = 0
    nxt = s + 1
  end
  return { text = text, state = nxt, sanity_delta = delta }
end
return { name = "The Far-Near Rule", inspect = inspect, apply = apply }
