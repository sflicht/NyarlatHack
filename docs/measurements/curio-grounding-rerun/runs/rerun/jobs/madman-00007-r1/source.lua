return {
  name = "Unclosed Card",
  inspect = function(ctx)
    local s = ctx.sanity
    local i = ctx.insight
    local c = ctx.charges
    local st = ctx.state
    if c == 0 then
      if st == 0 then
        return "Unused, yet already thin: an ivory card whose border fails to meet."
      end
      return "Spent thin. The unclosed border keeps a gap and nothing else."
    end
    if i == 0 then
      if st == 0 then
        return "Ivory card, blank. A hairline border almost closes, then does not."
      end
      if st == 1 then
        return "Still blank. The gap has moved a finger's width, with no smudge."
      end
      if s < 50 then
        return "The stock is warmer than paper. You cannot find where you touched it."
      end
      return "Blank again. Only the unfinished corner insists it was always so."
    end
    if i < 50 then
      if st < 2 then
        return "A faint pressure of type, stopped short. No word quite arrives."
      end
      return "The pressure returns in the same place, one stroke less certain."
    end
    if s >= 70 then
      if st == 0 then
        return "Fine stock. You nearly read a monogram, then only the open border."
      end
      return "You could swear the monogram changed. The card offers no ink."
    end
    if st >= 3 then
      return "The omission repeats cleanly. Elegance, and nothing you can name."
    end
    return "Almost a letter, never a name. The border declines to finish it."
  end,
  apply = function(ctx)
    local s = ctx.sanity
    local i = ctx.insight
    local c = ctx.charges
    local st = ctx.state
    if c == 0 then
      return {
        text = "The card does not take the touch. The border stays unclosed.",
        state = st,
        sanity_delta = 0
      }
    end
    local ns = st + 1
    if ns > 255 then
      ns = 255
    end
    local d = -1
    local text = "You turn the card. The border's gap meets your nail and slips."
    if i >= 200 and s >= 40 then
      d = -2
      text = "Almost a name. The missed stroke leaves the calm a little cracked."
    elseif i >= 50 then
      d = -1
      if st == 0 then
        text = "Your thumb finds the open corner. A letter fails, politely."
      else
        text = "The same failure, one place over. Nothing is written."
      end
    elseif s < 40 then
      d = 1
      if st == 0 then
        text = "A small clearness arrives, paper-thin, and does not feel like mercy."
      else
        text = "The clearness returns, thinner. The blank has not grown kinder."
      end
    elseif st == 0 then
      d = -1
      text = "You turn the card. The border's gap meets your nail and slips."
    elseif st >= 4 then
      d = -1
      text = "Turned again. The omission recurs, elegant and unanswered."
    elseif c == 1 then
      d = -1
      text = "Last touch. The ivory cools. The corner remains unfinished."
    else
      d = 0
      text = "You turn it once more. The gap has moved. No ink answers."
    end
    return { text = text, state = ns, sanity_delta = d }
  end
}
