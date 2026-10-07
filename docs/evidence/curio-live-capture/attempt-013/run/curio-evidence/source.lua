return {
  name = 'glass reed locket',
  inspect = function(ctx)
    local s = ctx.sanity
    local i = ctx.insight
    local c = ctx.charges
    local t = ctx.state
    if c == 0 then
      return 'The locket is shut. The glass reed shows only a cool hairline, and no tone at all.'
    end
    if t == 0 then
      if i > 500 then
        return 'A cracked locket holds a hair-thin reed. The crack repeats a gap too regular for mere wear.'
      end
      if c == 1 then
        return 'A cracked locket holds a hair-thin glass reed. The cooler edge is faint, nearly gone.'
      end
      if s < 50 then
        return 'A cracked locket holds a hair-thin reed. The cooler edge seems to wait just beside the ear.'
      end
      return 'A cracked locket holds a hair-thin glass reed. One edge is cooler, as if a breath stopped short.'
    end
    if t == 1 then
      return 'The reed keeps a pale warmth. A high note seems to have started, and then simply is not there.'
    end
    if t == 2 then
      if c == 1 then
        return 'The unfinished interval sits in the glass, a little duller, and the cadence still will not close.'
      end
      return 'The same short measure has returned. The missing step is exact, and the locket gives no reason.'
    end
    if s < 50 then
      return 'The short measure comes back thinner. The missing pitch feels nearer than the cracked glass.'
    end
    if i > 100 then
      return 'Crack and missed interval share one shape. Neither finishes, and neither explains the other.'
    end
    return 'The reed is unchanged. The unfinished high interval only sits a little closer to the ear.'
  end,
  apply = function(ctx)
    local s = ctx.sanity
    local i = ctx.insight
    local c = ctx.charges
    local t = ctx.state
    local ns = t + 1
    if ns > 255 then
      ns = 255
    end
    local text
    local delta
    if t == 0 then
      text = 'You breathe across the reed. A high thin tone starts, then stops one step short of closing.'
      delta = -1
    elseif t == 1 then
      text = 'The high tone returns, fragile and exact, and fails in the same unclosed step.'
      delta = -1
    elseif s < 25 then
      text = 'The short measure brushes the ear and frays. What remains is thin, and will not resolve.'
      delta = -2
    elseif s < 50 then
      text = 'Again the tone rises and stops short. The quiet after it feels narrow, almost worn through.'
      delta = -1
    elseif i > 500 then
      text = 'You almost name the interval. The name fails at the same hairline, and the reed stays mute.'
      delta = 0
    elseif c <= 1 then
      text = 'This breath finds only cool glass. The unfinished note does not come.'
      delta = 0
    else
      text = 'Again the tone rises and stops short. The elegance holds; the cadence does not.'
      delta = -1
    end
    return { text = text, state = ns, sanity_delta = delta }
  end
}
