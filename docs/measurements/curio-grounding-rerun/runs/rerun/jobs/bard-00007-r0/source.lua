local function miss(ctx)
  if ctx.insight > 500 then
    return "The miss is one fixed hair."
  elseif ctx.insight > 0 then
    return "You can count the miss, not its owner."
  else
    return "Line or eye: you cannot say."
  end
end
local function face(ctx)
  if ctx.state == 0 then
    return " Unturned."
  elseif ctx.state < 4 then
    return " A turn did not join it."
  elseif ctx.state < 255 then
    return " More turns, same miss."
  else
    return " No quarter left."
  end
end
local function tone(ctx)
  if ctx.charges == 0 then
    return " The face is dull."
  elseif ctx.sanity >= 90 then
    return " A perfect frame, one failed join."
  elseif ctx.sanity < 50 then
    return " The gap seems too wide."
  else
    return " Mute where a reed would answer."
  end
end
return {
  name = "Square Mute",
  inspect = function(ctx)
    return "Pale horn, a true square. The line should close. " .. miss(ctx) .. face(ctx) .. tone(ctx)
  end,
  apply = function(ctx)
    local n = ctx.state
    if n < 255 then
      n = n + 1
    end
    local d = 0
    if ctx.sanity >= 80 and ctx.insight == 0 then
      d = -1
    elseif ctx.sanity < 40 then
      d = -1
    elseif ctx.insight > 100 and ctx.sanity >= 50 then
      d = 1
    end
    local t
    if ctx.state >= 255 then
      t = "No new quarter shows. The miss remains where it was."
    elseif n == 1 then
      t = "You turn it once. The miss slides to the next edge."
    elseif n == 2 then
      t = "A second quarter. The gap stays a hair wide."
    elseif n == 3 then
      t = "A third quarter. Your frame still cannot close the line."
    elseif n % 4 == 0 then
      t = "The square meets itself again, and still not your eye."
    else
      t = "The same miss, only shifted along the rule."
    end
    if ctx.charges <= 1 then
      t = t .. " The horn takes the press dully."
    elseif ctx.sanity < 50 then
      t = t .. " The hand wants a note that is not there."
    else
      t = t .. " No sound leaves the plane."
    end
    return { text = t, state = n, sanity_delta = d }
  end
}
