return {
  name = "Skew Square",
  inspect = function(ctx)
    local s = ctx.sanity
    local i = ctx.insight
    local c = ctx.charges
    local t = ctx.state
    if c == 0 and t > 0 then
      return "The plate is dull. Grooves remain where a perimeter was traced and did not close."
    elseif t == 0 and i == 0 and s >= 50 then
      return "A palm-sized horn plate, ruled with one square. The four edges look equal until the light shifts."
    elseif s < 40 and i > 100 then
      return "Warm horn, cold lines. You count three sides, then four, and both counts stop at the rim."
    elseif s < 50 then
      return "The horn square is warm. Three edges meet; the fourth stops short, as if the plane ended early."
    elseif i > 100 and t > 0 then
      return "Fine lines cross the square and continue to the rim, then stop. Nothing beyond the rim is marked."
    elseif t > 2 then
      return "The square corner has been counted twice. Both counts fit the marks. Neither explains the gap."
    else
      return "A thin square of pale horn. One corner is sharp; the opposite corner reads as a short blunt line."
    end
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
    if t == 0 then
      return { text = "You trace the rim. Three sides agree. The fourth is shorter by a hair you cannot pinch.", state = ns, sanity_delta = -1 }
    elseif i > 500 and t < 20 then
      return { text = "The lines stay on the plate. Their meeting point slides, still inside the horn, still unfixed.", state = ns, sanity_delta = 0 }
    elseif s < 40 and t < 8 then
      return { text = "The short side lengthens when you look away, then fails again under the thumb.", state = ns, sanity_delta = -2 }
    elseif s >= 70 and t % 2 == 1 then
      return { text = "Held flat, the four sides agree. The ease fades as soon as the plate is tilted.", state = ns, sanity_delta = 1 }
    elseif c <= 1 then
      return { text = "One last pass. The corner you trusted is only a crease. The square does not correct itself.", state = ns, sanity_delta = -1 }
    else
      return { text = "The same four marks. Their order has shifted by one corner, and the gap has moved with them.", state = ns, sanity_delta = -1 }
    end
  end
}