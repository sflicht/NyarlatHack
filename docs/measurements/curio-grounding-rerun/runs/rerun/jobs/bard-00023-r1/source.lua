local function inspect(ctx)
  local s = ctx.sanity
  local i = ctx.insight
  local c = ctx.charges
  local st = ctx.state
  if c == 0 then
    return "With no press left, the bone square is dull. Its fourth edge still falls short."
  end
  if st >= 4 then
    return "Turned often, the plate shows three sure sides and one measured absence."
  end
  if st == 2 or st == 3 then
    return "The shortage has changed sides. Whichever edge you trust is not the short one."
  end
  if st == 1 then
    return "A faint crease marks where you pressed. The square is no closer to closing."
  end
  if s < 40 then
    return "The square's corners refuse one plane. Each angle is true, and none agree."
  end
  if i >= 500 then
    return "The plate is flat. What fails is not the edge but the frame that calls it closed."
  end
  if s >= 80 and i < 50 then
    return "A thin bone square. Three edges meet cleanly. The fourth stops short by a breath."
  end
  if c == 1 then
    return "One pressing left. The unfinished side is quieter than the three that meet."
  end
  return "Held level, the square is almost true. Tilt it, and one side withdraws."
end

local function apply(ctx)
  local s = ctx.sanity
  local i = ctx.insight
  local c = ctx.charges
  local st = ctx.state
  local nst = 3
  local delta = 0
  local text = "At the last mark the turn stops. The absence stays one edge beyond the hand."
  if st == 0 then
    nst = 1
    delta = -1
    text = "You press the open corner shut. It closes on the page and opens in the hand."
    if i == 0 then
      text = "No depth, and no pitch. Only a square exact except where it fails to finish."
    end
    if s >= 90 and i < 10 then
      text = "Steady hands, empty measure. The square is perfect, save the side that ends early."
      delta = 0
    end
  elseif st == 1 then
    nst = 2
    delta = 0
    text = "The shortage has moved. A different side is now the one that will not arrive."
  elseif st == 2 then
    nst = 3
    delta = -1
    text = "Three sides answer your measure. The fourth is present only as a pause."
  elseif st < 255 then
    nst = st + 1
    if nst > 6 then
      nst = 3
    end
    delta = 0
    text = "You turn the plate. The missing length follows, always just outside the turn."
  end
  if s < 40 then
    text = "The corners will not share a plane. Pressing one true angle falsifies the next."
    if delta > -2 then
      delta = delta - 1
    end
  end
  if c == 1 then
    if st == 0 then
      text = "One press left. The open corner yields on the page and returns in the hand."
    elseif st == 1 then
      text = "One press left. The short side has already fled to an edge you are not holding."
    else
      text = "One press left. Flatness holds, and the missing length does not come back."
    end
    if delta < -1 then
      delta = -1
    end
  end
  return { text = text, state = nst, sanity_delta = delta }
end

return {
  name = "Unclosed Bone Square",
  inspect = inspect,
  apply = apply
}
