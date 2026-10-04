local function look(ctx)
  local s = ctx.sanity
  local i = ctx.insight
  local c = ctx.charges
  local t = ctx.state
  if c == 0 then
    return "Cold brass, salt-pitted, done. The film inside has stopped answering the thumb."
  end
  if t == 0 then
    if i > 0 then
      return "Thumb-sized brass cup. The inner film sits a hair above the shadow it ought to cast."
    end
    return "A salt-pitted brass cup, no bigger than a thumb. Its film sits higher than the shadow."
  end
  if t == 1 then
    if s < 50 then
      return "The film is torn. Grit in the hollow feels deeper than the brass is wide."
    end
    return "A thumb-smear has lowered the film. The new line is wider than the cup."
  end
  if t < 4 then
    if i == 0 then
      return "The film has settled wrong. You cannot say if the fault is light or measure."
    end
    return "Salt grit holds a false level. The cup stays small. The error does not."
  end
  if s < 40 then
    return "The cup weighs like a wet line. Distance gathers in the palm and will not name itself."
  end
  return "The same wrong tide-line, no wider than before. Smallness does not correct it."
end

local function use(ctx)
  local s = ctx.sanity
  local i = ctx.insight
  local c = ctx.charges
  local t = ctx.state
  local nxt = t
  local delta = 0
  local text
  if t == 0 then
    nxt = 1
    text = "The film breaks under the thumb. Cold grit shifts, as if a longer line paid out."
    if s >= 70 then
      delta = -1
    end
  elseif t == 1 then
    nxt = 2
    if s < 40 then
      text = "The palm reads a depth the room does not have. Brass gives back only salt and cold."
      delta = -1
    else
      text = "You tilt the cup. The film climbs the wrong wall and stops, obedient to nothing here."
      delta = -1
    end
  elseif t == 2 then
    nxt = 3
    if i > 500 then
      text = "The grit finds a level the eye rejects. The cup is only a cup. The level is not."
      delta = -2
    elseif i == 0 then
      text = "Grit sorts into a depth too large for the cup, then stills. You cannot name the error."
      delta = -1
    else
      text = "A thin salt-line settles where no tide reaches. The measure is exact and unwelcome."
      delta = -1
    end
  else
    if t < 255 then
      nxt = t + 1
    end
    if c <= 1 then
      text = "Last warmth leaves the brass. The false tide-line holds, small, and will not explain."
      delta = 0
    elseif s < 25 then
      text = "For a breath the cup is only worn brass. The false depth loosens, then remains."
      delta = 1
    elseif s < 50 then
      text = "Again the hollow answers with more distance than a closed hand can keep."
      delta = -2
    elseif i > 100 then
      text = "The line repeats, no wider. Repetition makes the small wrongness harder to set aside."
      delta = -1
    else
      text = "You turn the cup. The grit keeps its false depth. Nothing else in the hand moves."
      delta = 0
    end
  end
  return { text = text, state = nxt, sanity_delta = delta }
end

return {
  name = "Salted Sounding Cup",
  inspect = look,
  apply = use
}
