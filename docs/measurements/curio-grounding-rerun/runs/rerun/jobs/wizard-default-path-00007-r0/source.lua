local function corner_name(state)
  local r = state % 4
  if r == 0 then
    return "lower-left"
  elseif r == 1 then
    return "lower-right"
  elseif r == 2 then
    return "upper-right"
  else
    return "upper-left"
  end
end

local function inspect(ctx)
  local gap = corner_name(ctx.state)
  local line = "A bone square. The " .. gap .. " corner stops a hair short. "
  if ctx.insight == 0 then
    line = line .. "From this side the want is only bone. "
  elseif ctx.insight < 1000 then
    line = line .. "From the next side that hair is not the same. "
  else
    line = line .. "Each start fits itself and misses the last. "
  end
  if ctx.sanity < 50 then
    line = line .. "The lines press. "
  else
    line = line .. "The face is cool. "
  end
  if ctx.state >= 4 then
    if ctx.charges == 0 then
      line = line .. "Ruled, and still open."
    elseif ctx.charges == 1 then
      line = line .. "Open, one groove left."
    elseif ctx.charges == 2 then
      line = line .. "Open, two grooves left."
    else
      line = line .. "Open, three grooves left."
    end
  elseif ctx.charges == 0 then
    line = line .. "No groove is left."
  elseif ctx.charges == 1 then
    line = line .. "One groove is left."
  elseif ctx.charges == 2 then
    line = line .. "Two grooves are left."
  else
    line = line .. "Three grooves are left."
  end
  if #line > 160 or #line < 1 then
    return "A bone square keeps one corner short."
  end
  return line
end

local function apply(ctx)
  if ctx.charges == 0 then
    return {
      text = "The square is already ruled. The same corner remains a hair short.",
      state = ctx.state,
      sanity_delta = 0
    }
  end
  local next_state = ctx.state
  if ctx.state < 255 then
    next_state = ctx.state + 1
  end
  local gap = corner_name(next_state)
  local delta = 0
  local text
  if ctx.state >= 255 then
    text = "Pressure repeats the same short count. The gap does not travel."
    delta = 0
  elseif ctx.insight == 0 and ctx.sanity < 40 then
    text = "A hard stop at the " .. gap .. " corner settles the thumb. Nothing past the bone answers."
    delta = 1
  elseif ctx.insight == 0 and ctx.sanity >= 80 then
    text = "You lay the short side down. It misses. The lack now sits at the " .. gap .. " corner, only bone."
    delta = 0
  elseif ctx.insight == 0 then
    text = "You press the gap flat. It refuses, then shows at the " .. gap .. " corner, one hair shy."
    delta = -1
  elseif ctx.insight >= 1000 and ctx.sanity >= 50 then
    text = "From this start the " .. gap .. " corner fails on its own measure. No start mends another."
    delta = -2
  elseif ctx.sanity < 25 then
    text = "The " .. gap .. " corner is short again. The edge is definite, and that is all."
    delta = 0
  else
    text = "Starting over, the " .. gap .. " corner is short by another hair. The square will not close."
    delta = -1
  end
  if ctx.state >= 4 and ctx.state < 255 then
    text = "The count has circled. " .. text
  end
  if ctx.charges == 1 then
    text = text .. " This groove is the last."
  elseif ctx.charges == 2 then
    text = text .. " The mark stays pale."
  else
    text = text .. " The face stays smooth."
  end
  if #text > 160 or #text < 1 then
    text = "The lack moves one corner on. The square will not close."
  end
  return {
    text = text,
    state = next_state,
    sanity_delta = delta
  }
end

return {
  name = "Unclosed Square",
  inspect = inspect,
  apply = apply
}
