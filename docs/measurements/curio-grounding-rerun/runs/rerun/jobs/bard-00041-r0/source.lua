return {
  name = "Pale Silk Reed",
  inspect = function(ctx)
    local s = ctx.sanity
    local i = ctx.insight
    local c = ctx.charges
    local st = ctx.state
    if st == 0 then
      if s >= 80 then
        return "A lacquered reed, bound in pale silk. The silk is warmer than the grain, by a degree you cannot place."
      elseif s >= 40 then
        return "The reed's crack does not follow the grain. Pale silk covers it, and the silk seems to listen."
      else
        return "The silk is too smooth. Under it the crack holds a silence shaped like a note you did not sound."
      end
    elseif st == 1 then
      if i == 0 then
        return "The silk has shifted a thread's width. No name fits the half-tone that almost arrived."
      elseif i <= 500 then
        return "A pattern almost coheres in the loosened silk: three pauses, then a gap where a cadence should close."
      else
        return "The loosened silk repeats a measure you cannot finish. Completing it would be a kind of lie."
      end
    elseif c >= 2 then
      if st % 2 == 0 then
        return "The same crack, the same silk. Only the warmth has moved, as if the reed learned a hesitation."
      else
        return "The warmth has withdrawn. The crack waits in the fold it refused, elegant and unfinished."
      end
    elseif c == 1 then
      return "One thread remains taut. The rest hang pale and precise, holding a quiet that will not close."
    else
      return "The silk lies slack. The crack is ordinary again, except that ordinary no longer convinces."
    end
  end,
  apply = function(ctx)
    local s = ctx.sanity
    local i = ctx.insight
    local c = ctx.charges
    local st = ctx.state
    local text = "The pale silk does not answer."
    local ns = st
    local delta = 0
    if st == 0 then
      ns = 1
      if s >= 70 then
        text = "You turn the reed. The silk slips one thread. A high, absent tone brushes the air and fails."
        delta = 0
      elseif s >= 40 then
        text = "The silk gives. For a moment the crack answers in a pitch too clean to have come from wood."
        delta = -1
      else
        text = "Your fingers find the crack already warm. The almost-note finishes itself, then pretends it did not."
        delta = -2
      end
    elseif st == 1 then
      ns = 2
      if i == 0 then
        text = "Again the silk shifts, the same width. The missing close of the phrase stays missing."
        delta = 0
      elseif i <= 500 then
        text = "You almost hear the third pause land. It does not. The reed is only lacquer and thread."
        delta = -1
      else
        text = "The measure repeats too exactly. You stop before the gap, and the stopping feels rehearsed."
        delta = -1
      end
    else
      if st < 255 then
        ns = st + 1
      end
      if c <= 1 then
        text = "The last taut thread loosens without sound. What remains is a polite, unfinished quiet."
        delta = 0
      elseif s < 50 then
        if st % 2 == 0 then
          text = "The recurrence is smaller, and nearer. You set the reed down before the cadence agrees."
        else
          text = "Nearer still, then not. The silk reverses its fold, as if declining to finish the phrase."
        end
        delta = -1
      elseif i > 500 then
        text = "Pale silk resettles. You could name the missing close, and the naming would make it false."
        delta = -1
      elseif st % 2 == 0 then
        text = "Pale silk resettles. The crack offers the same unfinished cadence, elegant and not quite yours."
        delta = 0
      else
        text = "The fold reverses. The cadence withdraws what it nearly gave, precise as a courtesy."
        delta = 0
      end
    end
    return { text = text, state = ns, sanity_delta = delta }
  end
}
