return {
  name = [[Even Pearl Card]],
  inspect = function(ctx)
    local s = ctx.sanity
    local i = ctx.insight
    local c = ctx.charges
    local t = ctx.state
    if c == 0 then
      return [[The pearl card remains, its compliment already spent. The blank face is the more honest of the two.]]
    elseif t > 0 and c == 1 then
      return [[The pearl card waits with its last compliment already composed. The lettering is perfect, and a fraction late.]]
    elseif t >= 3 then
      return [[Blank on one face, over-finished on the other. The same praise sits there, as if repetition could pass for regard.]]
    elseif i > 500 then
      return [[The card's pearl skin is flawless. Under that finish, the compliment seems addressed to a likeness, not to you.]]
    elseif i > 0 then
      return [[A calling-card of pearl, unused and too smooth. One edge is warmer than the rest, though nothing has held it.]]
    elseif s >= 80 then
      return [[Pearl, cut thin as a compliment. One face is blank. The other flatters you in a hand too even to be kind.]]
    elseif s >= 40 then
      return [[The card is lovely and slightly cold. Its praise fits your posture better than your face, and will not smudge.]]
    else
      return [[The pearl has not dulled. Only the compliment has: still elegant, and no longer willing to meet your eye.]]
    end
  end,
  apply = function(ctx)
    local s = ctx.sanity
    local i = ctx.insight
    local c = ctx.charges
    local t = ctx.state
    local ns = t
    if t < 255 then
      ns = t + 1
    end
    local d = 0
    local text
    if t == 0 and s >= 70 and c > 1 then
      d = 1
      if i > 500 then
        text = [[The card praises a smoother likeness than yours. You accept it. For one breath the finish is almost convincing.]]
      elseif i > 0 then
        text = [[You accept the praise, and notice the pearl is warmer where a thumb would rest. No thumb has rested there.]]
      else
        text = [[You accept the card's praise. For a moment your reflection agrees, which is the cheapest form of mercy.]]
      end
    elseif t == 0 and s >= 70 and c == 1 then
      d = 0
      text = [[The last compliment arrives flawless and unspent. You wear it anyway. Nothing in the room improves.]]
    elseif t == 0 and s >= 70 then
      d = 0
      text = [[The praise is offered with nothing left to spend. You incline your head. The pearl does not warm.]]
    elseif t == 0 and s < 30 then
      d = -1
      text = [[You turn the bright face toward yourself. The compliment is immaculate, and it declines to recognize you.]]
    elseif t == 0 then
      d = 0
      text = [[The praise is exquisite and does not take. The pearl stays bright; you do not feel correspondingly arranged.]]
    elseif s < 25 then
      d = -2
      text = [[The card repeats its kindness. This time the words fit a better version of you, and the gap is not polite.]]
    elseif c == 1 or t >= 4 then
      d = -1
      if i > 0 then
        text = [[Held too long, the compliment cools. It still flatters the pose, and the face that misses it feels the draft.]]
      else
        text = [[You turn the card again. The same perfect line returns late, and leaves a small, fashionable chill.]]
      end
    elseif s < 55 then
      d = -1
      text = [[The flattery is unchanged. What changes is the pause before you believe it, and that pause is not free.]]
    else
      d = 0
      text = [[Another reading, no less polished. The card offers beauty without amendment, and you almost thank it.]]
    end
    return { text = text, state = ns, sanity_delta = d }
  end
}
